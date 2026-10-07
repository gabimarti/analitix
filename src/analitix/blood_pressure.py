# ---------------------------------------------------------------------------
# Script: blood_pressure.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-10-07
# ---------------------------------------------------------------------------
"""Registro de tensión arterial: validación de cada medición (entrada manual
e importación) y lectura de ficheros CSV, sin interfaz ni base de datos
(eso está en `gui.py` y `repository.py`).

Los límites de `validate_reading` son de **plausibilidad**: sirven para
cazar errores de tecleo o columnas cambiadas, no son umbrales clínicos.

El CSV admite la plantilla propia (`CSV_TEMPLATE`) y las cabeceras de las
exportaciones de tensiómetros habituales (Omron Connect, Withings), con
separador `;`, `,` o tabulador y varios formatos de fecha.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import unicodedata
from pathlib import Path
from typing import Any, Optional

from analitix.textutils import strip_accents

# Límites de plausibilidad (mmHg / latidos por minuto) para cazar errores
# al teclear o columnas equivocadas; no son valores normales ni umbrales
# clínicos. La persona los ajusta en Configuración → Entrada manual (ajuste
# `bp_limits`), siempre dentro de ABSOLUTE_LIMITS; por defecto, los más
# restrictivos de DEFAULT_LIMITS.
ABSOLUTE_LIMITS = {"systolic": (50, 300), "diastolic": (20, 200), "pulse": (20, 250)}
DEFAULT_LIMITS = {"systolic": (80, 250), "diastolic": (45, 140), "pulse": (45, 225)}
LIMIT_NAMES = {"systolic": "sistólica", "diastolic": "diastólica", "pulse": "pulso"}
PLACES = ("casa", "consulta")
DEFAULT_PLACE = "casa"
NOTE_MAX_CHARS = 200

CSV_TEMPLATE = (
    "fecha_hora;sistolica;diastolica;pulso;lugar;notas\n"
    "2026-01-15 08:10;128;82;64;casa;antes del desayuno\n"
    "2026-01-15 21:30;121;78;70;casa;\n"
    "2026-02-02 10:45;134;86;;consulta;revisión anual\n"
)

# Cabecera normalizada (minúsculas, sin acentos ni unidades entre
# paréntesis) -> campo. Incluye las de Omron Connect ("Date", "Time",
# "Systolic (mmHg)", "Pulse (bpm)", "Notes") y Withings ("Date" con hora,
# "Heart rate", "Comments").
HEADER_ALIASES = {
    "fecha_hora": "fecha_hora", "fecha y hora": "fecha_hora", "datetime": "fecha_hora",
    "date time": "fecha_hora", "fecha": "fecha", "date": "fecha",
    "hora": "hora", "time": "hora",
    # "SYS/DIA/PUL" (abreviaturas de los propios tensiómetros): "dia" es la
    # diastólica, no el día.
    "sistolica": "sistolica", "systolic": "sistolica", "sys": "sistolica", "systole": "sistolica",
    "pas": "sistolica", "alta": "sistolica", "tension alta": "sistolica",
    "diastolica": "diastolica", "diastolic": "diastolica", "dia": "diastolica", "diastole": "diastolica",
    "pad": "diastolica", "baja": "diastolica", "tension baja": "diastolica",
    "pulso": "pulso", "pulse": "pulso", "pul": "pulso", "heart rate": "pulso", "frecuencia cardiaca": "pulso",
    "fc": "pulso", "bpm": "pulso", "ppm": "pulso",
    "lugar": "lugar", "place": "lugar", "location": "lugar",
    "notas": "notas", "nota": "notas", "notes": "notas", "comments": "notas", "comentarios": "notas",
}
_MONTHS_EN = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S",
)
_VACIO = ("", "-", "--")


def parse_datetime(text: str, now: Optional[dt.datetime] = None) -> str:
    """"AAAA-MM-DD HH:MM" a partir de los formatos admitidos (también el de
    Omron, "Jan 12 2025 08:15", con el mes en inglés sin depender del idioma
    del sistema). Rechaza fechas futuras y anteriores a 1900."""
    text = " ".join((text or "").split())
    valor = None
    for formato in _DATE_FORMATS:
        try:
            valor = dt.datetime.strptime(text, formato)
            break
        except ValueError:
            continue
    if valor is None:
        m = re.fullmatch(r"([A-Za-z]{3})[a-z]*\.? (\d{1,2}),? (\d{4}) (\d{1,2}):(\d{2})(?::\d{2})?", text)
        if m and m.group(1).lower() in _MONTHS_EN:
            try:
                valor = dt.datetime(int(m.group(3)), _MONTHS_EN[m.group(1).lower()], int(m.group(2)),
                                    int(m.group(4)), int(m.group(5)))
            except ValueError:
                valor = None
    if valor is None:
        raise ValueError(f"fecha y hora no válidas: «{text}» (usa AAAA-MM-DD HH:MM)")
    if valor.year < 1900:
        raise ValueError(f"fecha demasiado antigua: «{text}»")
    if valor > (now or dt.datetime.now()) + dt.timedelta(minutes=5):
        raise ValueError(f"la fecha es futura: «{text}»")
    return valor.strftime("%Y-%m-%d %H:%M")


def check_limits(limits: dict[str, Any]) -> dict[str, tuple[int, int]]:
    """Límites normalizados a enteros, o `ValueError` si alguno falta, no es
    un número, tiene el mínimo ≥ máximo o se sale de `ABSOLUTE_LIMITS`."""
    resultado = {}
    for clave, (tope_min, tope_max) in ABSOLUTE_LIMITS.items():
        try:
            minimo, maximo = (int(v) for v in limits[clave])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"límites de la {LIMIT_NAMES[clave]} no válidos") from None
        if not tope_min <= minimo < maximo <= tope_max:
            raise ValueError(f"los límites de la {LIMIT_NAMES[clave]} deben cumplir "
                             f"{tope_min} ≤ mínimo < máximo ≤ {tope_max}")
        resultado[clave] = (minimo, maximo)
    return resultado


def _parse_int(text: Any, nombre: str, rango: tuple[int, int], obligatorio: bool = True) -> Optional[int]:
    texto = str(text if text is not None else "").strip()
    if texto in _VACIO:
        if obligatorio:
            raise ValueError(f"falta la {nombre}")
        return None
    if not re.fullmatch(r"\d{1,3}(?:[.,]0+)?", texto):
        raise ValueError(f"{nombre} no válida: «{texto}» (solo números enteros)")
    valor = int(re.split(r"[.,]", texto)[0])
    if not rango[0] <= valor <= rango[1]:
        raise ValueError(f"{nombre} fuera de los límites admitidos: {valor} (entre {rango[0]} y {rango[1]}; "
                         "se ajustan en Configuración → Entrada manual)")
    return valor


def clean_note(text: Optional[str]) -> Optional[str]:
    """Nota sin caracteres de control y con longitud limitada (`None` si
    queda vacía)."""
    # Cada carácter de control (tabulador, salto de línea, nulo...) pasa a
    # ser un espacio, para no juntar palabras.
    limpio = "".join(" " if unicodedata.category(c)[0] == "C" else c for c in (text or ""))
    limpio = " ".join(limpio.split())[:NOTE_MAX_CHARS]
    return limpio or None


def validate_reading(fecha_hora: str, sistolica: Any, diastolica: Any, pulso: Any = None,
                     lugar: Optional[str] = None, notas: Optional[str] = None,
                     now: Optional[dt.datetime] = None,
                     limits: Optional[dict[str, tuple[int, int]]] = None) -> dict[str, Any]:
    """Medición validada y normalizada, o `ValueError` con el motivo en
    lenguaje llano. `limits`: los de Configuración (por defecto,
    `DEFAULT_LIMITS`)."""
    limites = limits or DEFAULT_LIMITS
    medida = parse_datetime(fecha_hora, now)
    sis = _parse_int(sistolica, "tensión sistólica (alta)", limites["systolic"])
    dia = _parse_int(diastolica, "tensión diastólica (baja)", limites["diastolic"])
    if sis <= dia:
        raise ValueError(f"la sistólica ({sis}) debe ser mayor que la diastólica ({dia})")
    pul = _parse_int(pulso, "frecuencia de pulso", limites["pulse"], obligatorio=False)
    lugar_norm = strip_accents((lugar or "").strip().lower()) or DEFAULT_PLACE
    if lugar_norm not in PLACES:
        raise ValueError(f"lugar no válido: «{lugar}» (casa o consulta)")
    return {"measured_at": medida, "systolic": sis, "diastolic": dia, "pulse": pul,
            "place": lugar_norm, "note": clean_note(notas)}


def _norm_header(header: str) -> str:
    texto = re.sub(r"\(.*?\)", "", strip_accents(header or "").lower().replace("﻿", ""))
    return " ".join(texto.replace("_", " ").split()).replace("fecha hora", "fecha_hora")


def read_csv(path: Path, now: Optional[dt.datetime] = None,
             limits: Optional[dict[str, tuple[int, int]]] = None) -> tuple[list[dict[str, Any]], list[str]]:
    """(mediciones válidas, errores "Línea N: motivo") de un CSV. Error
    general (sin mediciones) si faltan las columnas imprescindibles:
    fecha y hora (juntas o separadas), sistólica y diastólica."""
    crudo = Path(path).read_bytes()
    try:
        texto = crudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = crudo.decode("cp1252")
    try:
        delimitador = csv.Sniffer().sniff(texto[:4096], delimiters=";,\t").delimiter
    except csv.Error:
        delimitador = ";"
    filas = list(csv.reader(io.StringIO(texto), delimiter=delimitador))
    if not filas:
        return [], ["El fichero está vacío."]
    columnas: dict[str, int] = {}
    for i, cabecera in enumerate(filas[0]):
        campo = HEADER_ALIASES.get(_norm_header(cabecera))
        if campo and campo not in columnas:
            columnas[campo] = i
    tiene_fecha = "fecha_hora" in columnas or "fecha" in columnas
    faltan = [n for n, ok in (("fecha y hora", tiene_fecha), ("sistolica", "sistolica" in columnas),
                              ("diastolica", "diastolica" in columnas)) if not ok]
    if faltan:
        return [], [f"Faltan columnas: {', '.join(faltan)}. Cabecera esperada: "
                    f"{CSV_TEMPLATE.splitlines()[0]}"]

    def celda(fila: list[str], campo: str) -> str:
        i = columnas.get(campo)
        return fila[i].strip() if i is not None and i < len(fila) else ""

    lecturas, errores = [], []
    for n, fila in enumerate(filas[1:], start=2):
        if not any(c.strip() for c in fila):
            continue
        fecha_hora = celda(fila, "fecha_hora") or f"{celda(fila, 'fecha')} {celda(fila, 'hora')}".strip()
        try:
            lecturas.append(validate_reading(fecha_hora, celda(fila, "sistolica"), celda(fila, "diastolica"),
                                             celda(fila, "pulso"), celda(fila, "lugar"), celda(fila, "notas"), now,
                                             limits))
        except ValueError as exc:
            errores.append(f"Línea {n}: {exc}")
    return lecturas, errores
