# ---------------------------------------------------------------------------
# Script: ingest.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-09-25
# ---------------------------------------------------------------------------
"""Escaneo de la carpeta de informes e ingesta incremental en la base de datos.

En cada ejecución se comparan todos los PDF de `informes_analiticas` (sin
importar su fecha) contra la tabla `processed_files`; solo se parsean los
ficheros nuevos o cuyo contenido haya cambiado desde la última vez.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from analitix.catalog import canonical_id_for
from analitix.config import REPORTS_DIR
from analitix.pdf_parser import apply_age_bands, compute_flag, parse_report
from analitix.repository import (
    already_processed,
    clear_previous_import,
    clear_report_results,
    get_or_create_patient,
    get_patient_birth_date,
    insert_result,
    prune_missing_processed_files,
    record_processed_file,
    upsert_report,
)

logger = logging.getLogger("analitix.ingest")


def file_hash(path: Path) -> str:
    """Firma MD5 del contenido del PDF, para saber si es el mismo fichero
    aunque cambie de nombre o de carpeta. Solo identifica el fichero, no
    protege nada (por eso `usedforsecurity=False`)."""
    h = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def known_pdf_filenames(reports_dir: Path) -> set[str]:
    """Nombres de fichero de todos los PDF "conocidos", para decidir si un
    informe ya importado sigue teniendo su PDF de origen en algún sitio.

    Se busca recursivamente tanto bajo `reports_dir` (la carpeta actual
    seleccionada en la app) como bajo `REPORTS_DIR` (`informes_analiticas`):
    el usuario puede organizar los PDF en subcarpetas (una por persona, p.
    ej. `informes_analiticas/gmf`, `informes_analiticas/afg`) y cambiar de
    "carpeta actual" para importar cada una por separado. Si se comparase
    solo contra la carpeta activa en ese momento, cualquier informe
    importado desde otra subcarpeta parecería "sin PDF" en cuanto se cambia
    de carpeta, aunque su PDF siga ahí.
    """
    return {p.name for p in reports_dir.rglob("*.pdf")} | {p.name for p in REPORTS_DIR.rglob("*.pdf")}


@dataclass
class IngestResult:
    # (nombre_fichero, nombre_perfil) — el perfil detectado se muestra junto
    # al fichero en la interfaz para que se vea qué parser reconoció cada
    # PDF, sin tener que ir a mirar `processed_files` en Configuración.
    processed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    review: list[tuple[str, str]] = field(default_factory=list)


def ingest_folder(
    con,
    reports_dir: Path = REPORTS_DIR,
    force: bool = False,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
    recursive: bool = False,
) -> IngestResult:
    """Escanea `reports_dir` e ingiere los PDF nuevos o pendientes.

    Un fichero se salta solo si su hash no ha cambiado y la vez anterior
    quedó `status="ok"`; uno marcado "review"/"error" se reintenta siempre,
    sin necesidad de `force`. Con `force=True` se reprocesan también los
    ficheros ya correctos (por ejemplo, tras mejorar el parser).

    Si se pasa `on_progress`, se llama antes de procesar cada fichero como
    `on_progress(indice, total, nombre_fichero)` (índice empezando en 1),
    para que la interfaz pueda mostrar una barra de progreso e ir refrescando
    la pantalla en vez de quedarse aparentemente congelada.

    Con `recursive=True` busca también en las subcarpetas (casilla "Incluir
    subcarpetas" de la pestaña Importar).
    """
    pdf_paths = sorted(reports_dir.rglob("*.pdf") if recursive else reports_dir.glob("*.pdf"))
    total = len(pdf_paths)
    # Si algún PDF se ha renombrado o eliminado desde la última importación,
    # su marca de seguimiento antigua ya no sirve para nada (el informe
    # sigue accesible bajo el nombre vigente vía `upsert_report`); se
    # elimina para que el registro interno no acumule nombres de fichero
    # que ya no existen. Se comprueba contra `known_pdf_filenames` (no solo
    # los de esta carpeta) para no confundir "está en otra subcarpeta" con
    # "se ha eliminado" cuando el usuario importa varias subcarpetas por
    # separado cambiando de "carpeta actual".
    pruned = prune_missing_processed_files(con, known_pdf_filenames(reports_dir))
    if pruned:
        logger.info("Eliminadas %d marcas de importación de ficheros que ya no existen", pruned)
    logger.info("Iniciando importación de %d PDF en %s (force=%s)", total, reports_dir, force)
    result = IngestResult()
    for i, pdf_path in enumerate(pdf_paths, start=1):
        if on_progress:
            on_progress(i, total, pdf_path.name)
        digest = file_hash(pdf_path)
        if not force and already_processed(con, pdf_path.name, digest):
            result.skipped.append(pdf_path.name)
            continue
        try:
            reasons, format_name = _ingest_one(con, pdf_path, digest)
            result.processed.append((pdf_path.name, format_name))
            if reasons:
                # En el log (texto plano, sin cifrar) va la huella del
                # fichero y no su nombre: los PDF reales suelen llamarse con
                # el nombre del paciente. Coincide con el inicio de la
                # columna "MD5" de la ficha del paciente.
                logger.warning("PDF md5=%s marcado para revisar: %s", digest[:12], reasons)
                result.review.append((pdf_path.name, reasons))
        except Exception as exc:  # noqa: BLE001 - se registra y se continúa con el resto
            logger.exception("Error importando PDF md5=%s", digest[:12])
            con.rollback()
            record_processed_file(con, pdf_path.name, digest, status="error", error_message=str(exc))
            con.commit()
            result.errors.append((pdf_path.name, str(exc)))
    logger.info(
        "Importación terminada: %d procesados, %d omitidos, %d para revisar, %d con error",
        len(result.processed), len(result.skipped), len(result.review), len(result.errors),
    )
    return result


def _ingest_one(con, pdf_path: Path, digest: str) -> tuple[str, str]:
    """Procesa un PDF. Devuelve `(motivo, nombre_perfil)`: `motivo` es una
    cadena no vacía si el resultado necesita revisión manual (posible PDF de
    un formato/plantilla que la app no reconoce bien), o "" si todo parece
    correcto; `nombre_perfil` es el perfil detectado (`format_name` de
    `parse_report`, p. ej. "Formato no reconocido" si ninguno coincidió)."""
    # Por si es un reintento (fichero marcado "review"/"error", o `force=True`
    # sobre uno ya "ok"): borra el informe/resultados de la vez anterior para
    # no duplicar filas ni dejar datos huérfanos de un intento previo.
    previous_patient_id = clear_previous_import(con, pdf_path.name)

    parsed = parse_report(pdf_path)
    header = parsed["header"]

    if parsed.get("manual_review_only"):
        # Perfil detectado sin motor de parseo todavía (o ningún perfil
        # conocido): no hay ningún dato fiable que guardar (ni nombre, ni
        # resultados), así que no se crea paciente ni informe — solo se dice
        # explícitamente el motivo, en vez de importar de todos modos con un
        # paciente "de repuesto" a partir del nombre del fichero.
        reason_text = (
            f"formato de informe no reconocido ({parsed['format_name']}); "
            f"parser no implementado, revisar manualmente"
        )
        record_processed_file(con, pdf_path.name, digest, status="review", error_message=reason_text)
        con.commit()
        return reason_text, parsed["format_name"]

    # Se pasa `full_name=None` (en vez de ya sustituirlo aquí por el nombre
    # del fichero) para que `get_or_create_patient` pueda intentar primero
    # emparejar por DNI/NHC con un paciente ya existente; el nombre del
    # fichero queda como último recurso (`fallback_name`) solo si tampoco hay
    # coincidencia por identificador.
    patient_id, matched_by = get_or_create_patient(
        con,
        full_name=header.get("full_name"),
        birth_date=header.get("birth_date"),
        dni=header.get("dni") or None,
        nhc=header.get("nhc") or None,
        fallback_name=pdf_path.stem,
        sex=header.get("sex"),
        cip=header.get("cip"),
        previous_patient_id=previous_patient_id,
    )

    reasons = []
    if not header.get("full_name"):
        if matched_by in ("dni", "cip", "nhc", "previous"):
            reasons.append(
                f"no se reconoció el nombre del paciente (plantilla no soportada), pero se "
                f"vinculó automáticamente al paciente ya existente por {matched_by.upper()}"
            )
        else:
            reasons.append("no se reconoció el nombre del paciente")
    elif matched_by == "new" and not header.get("birth_date"):
        # Esta plantilla no trae fecha de nacimiento (p. ej. HUGTIP, que solo
        # trae la edad en años) y el emparejamiento por nombre+fecha de
        # nacimiento exige que ambos coincidan; si esta persona ya tenía
        # paciente en la BD por otra plantilla que sí trae fecha de
        # nacimiento, aquí no se habrá encontrado y se acaba de crear un
        # paciente nuevo con el mismo nombre — posible duplicado a fusionar
        # a mano (Pacientes → Fusionar) en vez de una persona distinta.
        reasons.append(
            "paciente vinculado sin fecha de nacimiento en este formato; "
            "revisar posible duplicado con un paciente ya existente"
        )
    if not parsed["results"]:
        reasons.append("no se extrajo ningún resultado")
    reason_text = "; ".join(reasons)
    report_id = upsert_report(
        con,
        patient_id=patient_id,
        report_number=header.get("report_number"),
        request_date=header.get("request_date"),
        validation_date=header.get("validation_date"),
        source_file=pdf_path.name,
        file_md5=digest,
        assistance_number=header.get("assistance_number"),
        lab=parsed.get("format_short_name"),
    )
    # Por si `upsert_report` ha emparejado con un informe ya existente (p.
    # ej. su PDF de origen se renombró y `clear_previous_import`, que busca
    # por nombre de fichero, no lo detectó): sin este borrado, los
    # resultados se duplicarían. Inofensivo si el informe es nuevo.
    clear_report_results(con, report_id)
    # Rangos por edad que el PDF no pudo resolver por no traer fecha de
    # nacimiento: se usa la del paciente ya emparejado.
    apply_age_bands(parsed["results"], get_patient_birth_date(con, patient_id), header.get("request_date"))
    for res in parsed["results"]:
        res.pop("age_bands", None)
        canonical_id = canonical_id_for(res["raw_name"])
        flag_calc = compute_flag(res["value_num"], res["ref_low"], res["ref_high"])
        insert_result(con, report_id, {**res, "canonical_id": canonical_id, "flag_calc": flag_calc})

    status = "review" if reason_text else "ok"
    record_processed_file(con, pdf_path.name, digest, status=status, report_id=report_id, error_message=reason_text or None)
    con.commit()
    return reason_text, parsed["format_name"]
