# ---------------------------------------------------------------------------
# Script: pdf_worker.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-11-24
# ---------------------------------------------------------------------------
"""Lectura de los PDF en un proceso aparte, vigilado.

Un PDF es una entrada no fiable: uno dañado o manipulado puede hacer que la
librería de lectura (pdfminer/pdfplumber) se quede en un bucle, consuma toda
la memoria o, en el peor caso, aproveche un fallo de la librería. Y una
plantilla de laboratorio del usuario puede traer una expresión regular que
tarde muchísimo en alguna línea. Para que nada de eso cuelgue la aplicación,
el PDF se abre y se parsea en un **proceso hijo**:

- Antes de abrirlo: tamaño máximo (`MAX_PDF_BYTES`) y, ya abierto, nº
  máximo de páginas (`MAX_PDF_PAGES`).
- El hijo avisa al terminar cada página; si pasa `STALL_TIMEOUT_S` sin
  noticias, o el PDF supera `TOTAL_TIMEOUT_S`, se para el hijo y el PDF
  queda con error, sin afectar a los demás. Mientras tanto se informa del
  progreso (página, segundos, «sin respuesta desde…») para que la interfaz
  lo muestre.
- En Windows, el hijo va en un *Job Object* con memoria máxima
  (`MEMORY_LIMIT_BYTES`) que además lo cierra si se cierra la aplicación.
- El hijo solo devuelve datos simples (diccionarios, listas, texto y
  números): nada del PDF se ejecuta en el proceso de la aplicación.
- Al log solo van tiempos y nº de páginas, nunca el nombre ni el contenido.

Un mismo hijo sirve para todos los PDF de una importación (`PdfWorker` como
gestor de contexto); arrancarlo cuesta lo que importar pdfplumber.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analitix import config

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 100
# Lo que puede tardar en arrancar el hijo (importar pdfplumber; la primera vez
# en el ejecutable instalado, con el antivirus revisándolo, es lo más lento).
STARTUP_TIMEOUT_S = 60
# Sin ningún aviso del hijo durante este tiempo: se da por colgado.
STALL_TIMEOUT_S = 45
# Tiempo máximo por PDF, avance o no.
TOTAL_TIMEOUT_S = 180
# A partir de aquí sin avisos, la interfaz dice «sin respuesta desde…».
STALL_WARNING_S = 10
MEMORY_LIMIT_BYTES = 1536 * 1024 * 1024
POLL_S = 0.2
# Un PDF que tarda más que esto queda anotado en el log (sin su nombre).
SLOW_PDF_S = 20


class PdfWorkerError(RuntimeError):
    """No se pudo leer el PDF en el proceso aparte (el mensaje lo explica)."""


class PdfTimeoutError(PdfWorkerError):
    """El PDF tardó demasiado o el proceso dejó de responder."""


class PdfRejectedError(PdfWorkerError):
    """PDF fuera de límites (tamaño o páginas): no se procesa."""


@dataclass
class Progress:
    """Estado de la lectura de un PDF, para la interfaz."""

    page: int | None
    pages: int | None
    elapsed: float
    silent: float  # segundos desde el último aviso del hijo

    @property
    def stalled(self) -> bool:
        return self.silent >= STALL_WARNING_S

    def text(self) -> str:
        partes = []
        if self.page and self.pages:
            partes.append(f"página {self.page} de {self.pages}")
        partes.append(f"{self.elapsed:.0f} s")
        if self.stalled:
            partes.append(f"sin respuesta desde hace {self.silent:.0f} s")
        return " · ".join(partes)


# -- Proceso hijo -------------------------------------------------------------


def _child_main(requests, responses, user_dir: str, app_config: str) -> None:
    """Bucle del proceso hijo: recibe rutas, devuelve el parseo."""
    from analitix import config as child_config

    # Mismas plantillas que el proceso padre (que puede haberlas cambiado).
    child_config.USER_PARSER_PROFILES_DIR = Path(user_dir)
    child_config.APP_CONFIG_PATH = Path(app_config)
    from analitix import parser_profiles

    parser_profiles.load_profiles.cache_clear()
    from analitix.pdf_parser import PdfLimitError, parse_report

    responses.put(("ready",))
    while True:
        job = requests.get()
        if job is None:
            return
        path, want_trace, max_pages = job
        trace: list | None = [] if want_trace else None
        try:
            parsed = parse_report(
                Path(path),
                trace=trace,
                on_page=lambda n, total: responses.put(("page", n, total)),
                max_pages=max_pages,
            )
        except PdfLimitError as exc:
            responses.put(("rejected", str(exc)))
            continue
        except Exception as exc:  # noqa: BLE001 - se informa al padre y se sigue
            responses.put(("error", type(exc).__name__))
            continue
        if trace is not None:
            parsed["trace"] = trace
        responses.put(("done", parsed))


def _never_ready_for_tests(requests, responses, user_dir: str, app_config: str) -> None:
    """Hijo que termina sin decir que está listo: solo para los tests."""


def _hang_for_tests(requests, responses, user_dir: str, app_config: str) -> None:
    """Hijo que arranca y nunca contesta: solo para probar la vigilancia."""
    responses.put(("ready",))
    requests.get()
    time.sleep(3600)


# -- Límite de memoria en Windows (Job Object) ------------------------------


def _limit_memory(pid: int, limit: int) -> Any:
    """Mete el proceso `pid` en un Job Object con memoria máxima y que se
    cierra con la aplicación. Devuelve el handle (hay que conservarlo: al
    cerrarlo se cierra el hijo) o None fuera de Windows o si falla."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [
            (n, ctypes.c_ulonglong)
            for n in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimit),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    job_object_limit_process_memory = 0x00000100
    job_object_limit_kill_on_job_close = 0x00002000
    job_object_extended_limit_information = 9
    process_set_quota, process_terminate = 0x0100, 0x0001

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = ExtendedLimit()
    info.BasicLimitInformation.LimitFlags = (
        job_object_limit_process_memory | job_object_limit_kill_on_job_close
    )
    info.ProcessMemoryLimit = limit
    process = kernel32.OpenProcess(process_set_quota | process_terminate, False, pid)
    ok = (
        process
        and kernel32.SetInformationJobObject(
            job, job_object_extended_limit_information, ctypes.byref(info), ctypes.sizeof(info)
        )
        and kernel32.AssignProcessToJobObject(job, process)
    )
    if process:
        kernel32.CloseHandle(process)
    if not ok:
        kernel32.CloseHandle(job)
        return None
    return job


def _close_handle(handle: Any) -> None:
    if handle and sys.platform == "win32":
        import ctypes

        ctypes.WinDLL("kernel32").CloseHandle(handle)


# -- Proceso padre ------------------------------------------------------------


class PdfWorker:
    """Proceso hijo reutilizable para leer PDF. Úsese con `with`:

    with PdfWorker() as worker:
        parsed = worker.parse(ruta, on_progress=mostrar)
    """

    def __init__(
        self,
        stall_timeout: float = STALL_TIMEOUT_S,
        total_timeout: float = TOTAL_TIMEOUT_S,
        _target: Callable = _child_main,
    ) -> None:
        self.stall_timeout = stall_timeout
        self.total_timeout = total_timeout
        self._target = _target
        self._ctx = mp.get_context("spawn")
        self._proc = None
        self._job = None
        # Si el hijo no llega a arrancar, no se reintenta con cada PDF (cada
        # intento espera `STARTUP_TIMEOUT_S`): el resto falla enseguida.
        self._start_failed = False

    def __enter__(self) -> PdfWorker:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _start(self) -> None:
        self._requests = self._ctx.Queue()
        self._responses = self._ctx.Queue()
        self._proc = self._ctx.Process(
            target=self._target,
            args=(
                self._requests,
                self._responses,
                str(config.USER_PARSER_PROFILES_DIR),
                str(config.APP_CONFIG_PATH),
            ),
            daemon=True,
        )
        self._proc.start()
        try:
            self._job = _limit_memory(self._proc.pid, MEMORY_LIMIT_BYTES)
        except Exception:  # noqa: BLE001 - sin límite de memoria, pero funciona
            logger.warning("No se pudo limitar la memoria del proceso de lectura de PDF")
            self._job = None
        try:
            message = self._responses.get(timeout=STARTUP_TIMEOUT_S)
        except queue.Empty:
            message = None
        if not message or message[0] != "ready":
            self._kill()
            self._start_failed = True
            logger.error("No arranca el proceso de lectura de PDF")
            raise PdfWorkerError("no arranca el proceso de lectura de PDF")

    def _kill(self) -> None:
        if self._proc is not None:
            self._proc.kill()
            self._proc.join(5)
        _close_handle(self._job)
        self._proc, self._job = None, None

    def close(self) -> None:
        """Termina el hijo (con buenas maneras y, si no, a la fuerza)."""
        if self._proc is None:
            return
        if self._proc.is_alive():
            try:
                self._requests.put(None)
            except (OSError, ValueError):
                pass
            self._proc.join(5)
        self._kill()

    def parse(
        self,
        pdf_path: Path,
        on_progress: Callable[[Progress], None] | None = None,
        trace: bool = False,
    ) -> dict[str, Any]:
        """Parsea `pdf_path` en el hijo y devuelve lo mismo que
        `pdf_parser.parse_report` (con `trace` si se pide). Lanza
        `PdfRejectedError` (fuera de límites), `PdfTimeoutError` (colgado o
        demasiado lento) o `PdfWorkerError` (no se pudo leer)."""
        size = Path(pdf_path).stat().st_size
        if size > MAX_PDF_BYTES:
            raise PdfRejectedError(
                f"el PDF ocupa {size / 1024 / 1024:.0f} MB "
                f"(máximo {MAX_PDF_BYTES // 1024 // 1024} MB)"
            )
        if self._start_failed:
            raise PdfWorkerError("no arranca el proceso de lectura de PDF")
        if self._proc is None or not self._proc.is_alive():
            self._start()
        self._requests.put((str(pdf_path), trace, MAX_PDF_PAGES))
        start = last = time.monotonic()
        page = pages = None
        while True:
            try:
                message = self._responses.get(timeout=POLL_S)
            except queue.Empty:
                now = time.monotonic()
                if not self._proc.is_alive():
                    self._kill()
                    raise PdfWorkerError(
                        "el proceso de lectura del PDF se cerró de forma inesperada "
                        "(¿demasiada memoria?)"
                    ) from None
                if now - last > self.stall_timeout or now - start > self.total_timeout:
                    self._kill()
                    logger.warning(
                        "PDF abandonado tras %.0f s (%s páginas leídas): no responde",
                        now - start,
                        page or 0,
                    )
                    raise PdfTimeoutError(
                        f"el PDF dejó de responder tras {now - start:.0f} s y se ha "
                        "abandonado (puede estar dañado)"
                    ) from None
                if on_progress:
                    on_progress(Progress(page, pages, now - start, now - last))
                continue
            last = time.monotonic()
            kind = message[0]
            if kind == "page":
                page, pages = message[1], message[2]
                if on_progress:
                    on_progress(Progress(page, pages, last - start, 0.0))
                continue
            elapsed = last - start
            if kind == "done":
                if elapsed > SLOW_PDF_S:
                    logger.warning("PDF lento: %.1f s, %s páginas", elapsed, pages)
                else:
                    logger.debug("PDF leído en %.1f s, %s páginas", elapsed, pages)
                return message[1]
            if kind == "rejected":
                raise PdfRejectedError(message[1])
            raise PdfWorkerError(f"no se pudo leer el PDF ({message[1]})")


def parse_report_isolated(
    pdf_path: Path,
    on_progress: Callable[[Progress], None] | None = None,
    trace: bool = False,
) -> dict[str, Any]:
    """Un PDF suelto (p. ej. la cabecera de un informe que no encaja) en un
    hijo propio que se cierra al terminar."""
    with PdfWorker() as worker:
        return worker.parse(pdf_path, on_progress=on_progress, trace=trace)
