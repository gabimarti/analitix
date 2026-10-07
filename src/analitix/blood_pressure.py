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


# -- Análisis (fase 2) ---------------------------------------------------
# Categorías de la guía ESC 2024 (McEvoy JW et al., "2024 ESC Guidelines
# for the management of elevated blood pressure and hypertension", Eur
# Heart J 2024;45(38):3912-4018, doi:10.1093/eurheartj/ehae178, tabla 5):
# no elevada < 120/70; elevada 120/70 a < 135/85 en casa (< 140/90 en la
# consulta); hipertensión ≥ 135/85 en casa (≥ 140/90 en la consulta). Manda
# la peor de las dos cifras. Solo se aplican a una MEDIA de automedida
# según protocolo, nunca a una lectura suelta.
BP_THRESHOLDS = {
    "casa": {"elevada": (120, 70), "hipertension": (135, 85)},
    "consulta": {"elevada": (120, 70), "hipertension": (140, 90)},
}
BP_CATEGORY_LABELS = {"no_elevada": "PA no elevada", "elevada": "PA elevada", "hipertension": "hipertensión"}
# Protocolo de automedida en casa (Stergiou GS et al., "2021 European
# Society of Hypertension practice guidelines for office and out-of-office
# blood pressure measurement", J Hypertens 2021;39(7):1293-1302,
# doi:10.1097/HJH.0000000000002843, recuadros 6 y 7): 7 días (al menos 3),
# mañana y noche; "Assess HBPM of 7 days (at least 3 days with at least 12
# readings). Discard the first day and calculate the average of all the
# other readings. Individual readings have little diagnostic accuracy."
HBPM_DAYS = 7
HBPM_MIN_DAYS = 3
HBPM_MIN_READINGS = 12


def bp_category(systolic: float, diastolic: float, place: str = "casa") -> str:
    """Categoría ESC 2024 ("no_elevada", "elevada" o "hipertension") de una
    media; manda la peor de las dos cifras."""
    umbrales = BP_THRESHOLDS[place]
    if systolic >= umbrales["hipertension"][0] or diastolic >= umbrales["hipertension"][1]:
        return "hipertension"
    if systolic >= umbrales["elevada"][0] or diastolic >= umbrales["elevada"][1]:
        return "elevada"
    return "no_elevada"


def _media(valores: list[float]) -> Optional[float]:
    return sum(valores) / len(valores) if valores else None


def home_week_summary(readings: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Media de la última semana de automedida en casa según el protocolo
    ESH 2021: las lecturas "casa" de los `HBPM_DAYS` días que acaban en la
    última, sin el primer día con lecturas. `valida` solo si quedan al menos
    `HBPM_MIN_DAYS` días y `HBPM_MIN_READINGS` lecturas; solo entonces lleva
    `categoria` (ESC 2024, umbrales de casa). `None` sin lecturas en casa."""
    casa = [r for r in readings if r.get("place", "casa") == "casa"]
    if not casa:
        return None
    dia = lambda r: dt.date.fromisoformat(r["measured_at"][:10])  # noqa: E731
    fin = max(dia(r) for r in casa)
    inicio = fin - dt.timedelta(days=HBPM_DAYS - 1)
    semana = [r for r in casa if dia(r) >= inicio]
    primer_dia = min(dia(r) for r in semana)
    usadas = [r for r in semana if dia(r) != primer_dia]
    dias = len({dia(r) for r in usadas})
    sis = _media([r["systolic"] for r in usadas])
    dias_ = _media([r["diastolic"] for r in usadas])
    valida = dias >= HBPM_MIN_DAYS and len(usadas) >= HBPM_MIN_READINGS
    return {
        "inicio": inicio.isoformat(), "fin": fin.isoformat(), "primer_dia": primer_dia.isoformat(),
        "dias": dias, "n": len(usadas), "systolic": sis, "diastolic": dias_,
        "pulse": _media([r["pulse"] for r in usadas if r.get("pulse")]),
        "pulse_pressure": None if sis is None else sis - dias_,
        "valida": valida, "categoria": bp_category(sis, dias_) if valida else None,
    }


def bp_summary_text(readings: list[dict[str, Any]]) -> str:
    """Resumen en lenguaje llano para el panel y el PDF."""
    if not readings:
        return "Sin mediciones de tensión arterial para este paciente (Entrada manual → Tensión arterial...)."
    lineas = []
    semana = home_week_summary(readings)
    if semana is None:
        lineas.append("No hay mediciones tomadas en casa: la media de automedida solo usa las de casa.")
    else:
        periodo = f"del {semana['inicio']} al {semana['fin']}, sin el primer día ({semana['primer_dia']})"
        if semana["n"]:
            media = f"{semana['systolic']:.0f}/{semana['diastolic']:.0f} mmHg"
            extra = f" · presión de pulso {semana['pulse_pressure']:.0f} mmHg"
            if semana["pulse"]:
                extra += f" · pulso medio {semana['pulse']:.0f} lpm"
            lineas.append(f"Última semana de automedida en casa ({periodo}): {semana['n']} lecturas en "
                          f"{semana['dias']} días. Media {media}{extra}.")
        else:
            lineas.append(f"Última semana de automedida en casa ({periodo}): sin lecturas después del primer día.")
        if semana["valida"]:
            casa = BP_THRESHOLDS["casa"]
            lineas.append(
                f"Categoría informativa según la guía ESC 2024 para medidas en casa: "
                f"{BP_CATEGORY_LABELS[semana['categoria']]} (no elevada < {casa['elevada'][0]}/{casa['elevada'][1]}; "
                f"elevada hasta < {casa['hipertension'][0]}/{casa['hipertension'][1]}; hipertensión ≥ "
                f"{casa['hipertension'][0]}/{casa['hipertension'][1]} mmHg). Es una ayuda para hablarlo con tu "
                "médico, no un diagnóstico.")
        else:
            lineas.append(
                f"No cumple el protocolo de automedida de la guía ESH 2021 (hacen falta al menos "
                f"{HBPM_MIN_DAYS} días y {HBPM_MIN_READINGS} lecturas sin contar el primer día, idealmente "
                f"{HBPM_DAYS} días con dos tomas por la mañana y dos por la noche): la media no se clasifica.")
    consulta = [r for r in readings if r.get("place") == "consulta"]
    if consulta:
        ultima = consulta[-1]
        lineas.append(f"Última toma en la consulta: {ultima['systolic']}/{ultima['diastolic']} mmHg "
                      f"({ultima['measured_at'][:10]}); en la consulta los umbrales son otros (hipertensión ≥ 140/90).")
    lineas.append("Las lecturas sueltas no se clasifican: tienen poca precisión diagnóstica (ESH 2021).")
    return "\n".join(lineas)


def period_stats(readings: list[dict[str, Any]], desde: Optional[str] = None,
                 hasta: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Medias descriptivas de las mediciones EN CASA entre `desde` y
    `hasta` ("AAAA-MM-DD", ambos incluidos; `None` = sin límite): nº de
    mediciones y de días, y media de sistólica, diastólica y pulso de todas
    las mediciones. No se clasifican (la guía solo clasifica una semana de
    automedida según protocolo, ver `home_week_summary`). `None` si no hay
    ninguna en el periodo."""
    casa = [r for r in readings if r.get("place", "casa") == "casa"
            and (desde is None or r["measured_at"][:10] >= desde)
            and (hasta is None or r["measured_at"][:10] <= hasta)]
    if not casa:
        return None
    return {
        "desde": casa[0]["measured_at"][:10], "hasta": casa[-1]["measured_at"][:10], "n": len(casa),
        "dias": len({r["measured_at"][:10] for r in casa}),
        "systolic": _media([r["systolic"] for r in casa]), "diastolic": _media([r["diastolic"] for r in casa]),
        "pulse": _media([r["pulse"] for r in casa if r.get("pulse")]),
    }


# Guía para medir la tensión en casa: recuadros 4 (procedimiento) y 6
# (pauta) de la guía ESH 2021 (Stergiou GS et al., J Hypertens
# 2021;39(7):1293-1302, doi:10.1097/HJH.0000000000002843), cotejados con su
# texto. Se muestra en la pantalla de entrada y en el manual.
MEASUREMENT_GUIDE = """Según la guía europea de medición de la tensión arterial (ESH 2021,
recuadros 4 y 6), para que la media sirva para valorar tu tensión:

CUÁNTAS VECES
• 7 días seguidos (como mínimo 3), mejor justo antes de una visita médica.
• Cada día, por la mañana y por la noche.
• Cada vez, 2 mediciones con 1 minuto entre ellas (anota las dos).
• Por la mañana, antes de tomar la medicación (si tomas) y antes de
  desayunar; por la noche, antes de cenar.
• Para el seguimiento a largo plazo con tratamiento: 2 mediciones una o dos
  veces por semana (como mínimo, una vez al mes).

CONDICIONES
• Habitación tranquila y con temperatura agradable.
• Nada de tabaco, cafeína, comida ni ejercicio en los 30 minutos previos.
• Sentado y relajado 3-5 minutos antes de medir; sin hablar durante ni
  entre las mediciones.

POSTURA
• Sentado con la espalda apoyada en el respaldo.
• Piernas sin cruzar y pies apoyados en el suelo.
• Brazo desnudo, apoyado en la mesa, con la mitad del brazo a la altura
  del corazón.

APARATO
• Tensiómetro electrónico de brazo validado clínicamente, con el manguito
  de la talla de tu brazo.

CÓMO LO USA ANALITIX
• Para la media de la semana de automedida descarta el primer día y
  necesita al menos 3 días y 12 mediciones (si sigues la pauta, tendrás
  unas 24). Una medición suelta no se clasifica.
• Marca «casa» como lugar: los umbrales de casa no son los de la consulta.

Apoyo informativo, nunca un diagnóstico: coméntalo con tu médico."""
