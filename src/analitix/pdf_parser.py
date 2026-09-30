# ---------------------------------------------------------------------------
# Script: pdf_parser.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-09-28
# ---------------------------------------------------------------------------
"""Extracción y parseo de los informes de laboratorio en PDF.

Las etiquetas de cabecera, secciones y demás datos que varían de un centro/
laboratorio a otro viven en perfiles externos (`parser_profiles.py`, ficheros
`.toml` en `data/parser_profiles/`), no en este módulo. Lo que sí vive aquí es
el motor de parseo en sí: la gramática de línea compartida por los perfiles
que la usan (marcador de nota `"(n)"` delante de una fila de resultado, rango
de referencia entre paréntesis o al final de línea sin paréntesis, flechas
↑/↓ de fuera de rango, separación nombre/LOINC/valor/unidad...), que hoy
cubre las 4 variantes de plantilla observadas del laboratorio Consorci
Sanitari del Maresme a lo largo de los años, cada vez con menos marcado
explícito según se retrocede en el tiempo: la más reciente con código LOINC y
flechas de fuera de rango, una intermedia sin LOINC pero con marcador "(n)" y
rango sin paréntesis al final de línea, y una más antigua (2023-2024) sin
ningún marcador "(n)", con el rango entre paréntesis y sin ninguna etiqueta
"Pacient:" (el nombre aparece suelto justo debajo de un título "Informe"). El
análisis se hace línea a línea sobre el texto plano extraído con pdfplumber.

Un perfil marcado `manual_review_only` (formato de un centro detectado pero
sin motor de parseo todavía, o ninguno reconocido) no pasa por este motor: se
devuelve sin cabecera ni resultados para que `ingest.py` lo mande a revisión
manual en vez de arriesgarse a guardar datos mal interpretados.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import pdfplumber

from analitix.parser_profiles import ParserProfile, detect_profile
from analitix.textutils import normalize_test_name, strip_accents

ARROW_UP = "↑"
ARROW_DOWN = "↓"

RESULT_LINE_RE = re.compile(r"^\(\d+\)\s*(.+)$")
SECTION_LINE_RE = re.compile(r"^Secci[oó]\s*/\s*Secci[oó]n\s+(.+)$", re.IGNORECASE)
# El signo "-" es opcional en cada extremo del rango (no solo como separador
# entre ambos): el HUGTIP usa rangos con límite inferior negativo, p. ej.
# "Excés de base -0.8 mmol/L -2.0 - 2.0". "Inf. N" (p. ej. Quirón: "(Inf.
# 30)") es un rango de un único límite superior en forma de texto en vez de
# "< N" — "inferior a N" equivale al mismo caso que un "<".
_RANGE_ALTS = (
    r"(?:Inf\.?\s*-?[\d.,]+)"
    r"|(?:[<>]=?\s*-?[\d.,]+)"
    r"|(?:-?[\d.,]+\s*-\s*-?[\d.,]+)"
)
RANGE_RE = re.compile(rf"(?P<range>{_RANGE_ALTS})\s*$")
# Plantillas más antiguas escriben el rango entre paréntesis al final de la
# línea, p.ej. "Glucosa sèrum 108 mg/dL ( 74 - 106 )", en vez de sin paréntesis.
PAREN_RANGE_RE = re.compile(rf"\(\s*(?P<range>{_RANGE_ALTS})\s*\)\s*$")
# Otras plantillas (p. ej. Synlab) usan corchetes en vez de paréntesis:
# "Hematíes 3,89 x106/mm³ [ 3,9 - 5,2 ]".
BRACKET_RANGE_RE = re.compile(rf"\[\s*(?P<range>{_RANGE_ALTS})\s*\]\s*$")
# Igual que PAREN_RANGE_RE pero sin anclar al final de línea: usada solo
# para la línea de valor de un resultado "interfaced" (ver
# `interfaced_result_prefix`), donde alguna fila añade una coletilla en
# prosa después del rango ("(Inf. 200) <150 para pacientes con riesgo CV")
# que no forma parte de él.
# Rango entre paréntesis sin límite superior, cortado tras el guion ("Folat
# <2 ng/ml ( 2.9 -", "Filtrat glomerular estimat 66 ml/mi/1.73m2 ( 90 -"):
# solo tiene mínimo.
OPEN_PAREN_RANGE_RE = re.compile(r"\(\s*(?P<low>-?[\d.,]+)\s*-\s*$")
PAREN_RANGE_ANY_RE = re.compile(rf"\(\s*(?P<range>{_RANGE_ALTS})\s*\)")
# Rango en una línea posterior a su resultado (ver `following_range_labels`
# en `parser_profiles.py`): rango suelto al inicio de línea ("<200 ( 5.2
# mmol/L )") o franja por edad ("<1 año (0.75-1.49 ng/dL)", "1-3 años
# (...)", ">19 años (...)").
LEADING_RANGE_RE = re.compile(rf"^(?P<range>{_RANGE_ALTS})(?:\s|$)")
AGE_BAND_RE = re.compile(
    rf"^(?:<\s*(?P<under>\d+)|>\s*(?P<over>\d+)|(?P<lo>\d+)\s*-\s*(?P<hi>\d+))\s*años?"
    rf"\s*\(\s*(?P<range>{_RANGE_ALTS})[^)]*\)$",
    re.IGNORECASE,
)
LOINC_NAME_RE = re.compile(r"^(?P<name>.+?)\s*\((?P<loinc>\d+-\d+)\)\s*(?P<rest>.*)$")
NUMERIC_TOKEN_RE = re.compile(r"[-+]?[\d.,]+")
# Valor fuera del límite de detección, con el comparador pegado al número
# ("<8 U/ml", ">90 mL/min"): es un valor, no parte del nombre. Se guarda como
# texto ("<5", sin `value_num`) para no dibujarlo en las gráficas como si
# fuera exactamente 5.
CENSORED_VALUE_RE = re.compile(r"[<>≤≥]=?[\d.,]+")
# Echevarne separa nombre de resultado del resto con puntos de relleno hasta
# una columna fija ("SEROALBÚMINA..................... 39,0 g/L
# (36,0-54,0)"), no con marcador "(n)" ni rango pegado al final de línea sin
# más — ver `dot_leader_result` en `parser_profiles.py`.
DOT_LEADER_RE = re.compile(r"^(?P<name>.+?)\.{2,}\s(?P<rest>.*)$")
# Cuando el valor de una fila con puntos de relleno queda fuera de rango,
# Echevarne reparte la fila en 3 líneas físicas: nombre+puntos+valor (sin
# unidad ni rango), un marcador de flecha que la fuente subseteada no pudo
# mapear a un carácter real (sale como su código interno de fuente en vez de
# texto), y unidad+rango en una tercera línea — ver `_merge_dot_leader_splits`.
_CID_MARKER_LINE_RE = re.compile(r"^\(cid:\d+\)$")

# Colesterol HDL: única determinación conocida en este laboratorio cuyo
# rango de referencia es un mínimo ("> 40"), no un máximo — ver el
# comentario junto a su uso en `parse_result_line`. "No HDL"/"non-HDL" usa
# la convención normal (máximo), así que se excluye explícitamente.
_HDL_RE = re.compile(r"\bhdl\b", re.IGNORECASE)
_NON_HDL_RE = re.compile(r"\bno\b\s*hdl|non-?hdl", re.IGNORECASE)

# Líneas que llevan el marcador de nota "(n)" pero no son una determinación
# (metadatos del laboratorio/facultativo responsable de la sección).
NON_RESULT_PREFIX_RE = re.compile(
    r"^(Laboratori|Servei\s+Respons|Facultatiu\s+Respons|Categoria\s+profess|Data\s+validaci|Validat|Respons)",
    re.IGNORECASE,
)

# Título que precede al nombre del paciente en la plantilla 2023-2024 (ver
# `expect_name_next`): "Informe" en la emisión normal, "Reedició Informe" en
# una reedición del mismo informe (comprobado en un PDF real de 2023). Se
# admite cualquier palabra corta delante en vez de enumerar cada variante de
# reedición/anulación una a una.
INFORME_TITLE_RE = re.compile(r"^(?:[A-Za-zÀ-ÿ·]+\s+){0,2}informe$", re.IGNORECASE)


def _drop_overlapping_spaces(page: Any) -> Any:
    """Quita los caracteres espacio que se solapan con un glifo real de la
    misma línea. La plantilla antigua de Maresme rellena la columna del
    valor con espacios literales que caen encima de los dígitos; al
    ordenar por posición, pdfplumber los intercala entre ellos ("sèrum 2
    7" en vez de "27") y parte el valor en dos. Un espacio normal está
    entre glifos, nunca encima, así que el resto de plantillas no cambia."""
    glyphs: dict[int, list[tuple[float, float]]] = {}
    for c in page.chars:
        if c["text"] != " ":
            glyphs.setdefault(round(c["top"]), []).append((c["x0"], c["x1"]))

    def keep(obj: dict) -> bool:
        if obj.get("object_type") != "char" or obj["text"] != " ":
            return True
        top = round(obj["top"])
        return not any(
            x0 < obj["x1"] - 0.5 and x1 > obj["x0"] + 0.5
            for t in (top - 1, top, top + 1)
            for x0, x1 in glyphs.get(t, ())
        )

    return page.filter(keep)


def extract_lines(pdf_path: Path, x_tolerance: float = 3) -> list[str]:
    """Extrae el texto de todas las páginas, línea a línea.

    `x_tolerance` (mismo parámetro de `pdfplumber`, `3` es su valor por
    defecto): alguna plantilla (p. ej. Echevarne) usa una fuente cuyo
    espaciado entre palabras es más ajustado de lo normal, y con la
    tolerancia por defecto pdfplumber funde palabras contiguas sin espacio
    entre ellas ("Datanaixement:" en vez de "Data naixement:"). `parse_report`
    reextrae con la tolerancia propia del perfil (`extract_x_tolerance`) tras
    detectarlo, ya que hace falta el texto para detectar el perfil primero.

    `dedupe_chars(extra_attrs=())` corrige un artefacto de la plantilla nueva:
    los valores fuera de rango se dibujan dos veces superpuestas (una vez con
    fuente normal y otra en negrita) para simular el negrita, y sin este
    filtro pdfplumber intercala los caracteres de ambas copias.
    """
    lines: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page = _drop_overlapping_spaces(page.dedupe_chars(extra_attrs=()))
            text = page.extract_text(x_tolerance=x_tolerance) or ""
            # Alguna fuente embebida y subseteada (vista en Quirón) sustituye
            # el dígrafo "ti" por un único glifo de ligadura que pdfplumber
            # extrae como un byte NUL en vez de texto ("Creatinina" ->
            # "Crea\x00nina").
            text = text.replace("\x00", "ti")
            lines.extend(text.split("\n"))
    return lines


def _extract_labeled_fields(
    line: str, labels: list[tuple[str, str]], boundary_re: Optional[re.Pattern] = None
) -> dict[str, str]:
    # Las plantillas no siempre acentúan igual la misma etiqueta (p.ej. "Num."
    # frente a "Núm.", "clínica" frente a "clinica"); se buscan las etiquetas
    # sobre una versión sin acentos, pero los valores se recortan del texto
    # original — `strip_accents` no cambia la longitud carácter a carácter,
    # así que las posiciones de los patrones siguen siendo válidas.
    normalized = strip_accents(line)
    matches = []
    for key, pattern in labels:
        for m in re.finditer(pattern, normalized, re.IGNORECASE):
            matches.append((m.start(), m.end(), key))
    if not matches:
        return {}
    matches.sort(key=lambda t: t[0])
    boundaries = [m.start() for m in boundary_re.finditer(normalized)] if boundary_re else []
    fields: dict[str, str] = {}
    for i, (_start, end, key) in enumerate(matches):
        candidates = [b for b in boundaries if b >= end]
        if i + 1 < len(matches):
            candidates.append(matches[i + 1][0])
        candidates.append(len(line))
        value_end = min(candidates)
        # "/" además de los espacios/dos puntos habituales: alguna plantilla
        # (p. ej. Echevarne) separa campos consecutivos de cabecera con "//"
        # en vez de un espacio, y sin recortarlo se cuela al final del valor
        # anterior ("12345678A//").
        fields[key] = line[end:value_end].strip(" :\t/")
    return fields


def _to_float(text: str) -> Optional[float]:
    candidate = text.strip()
    # Convención catalana/española: "." agrupa millares (siempre en grupos
    # de 3 dígitos) y "," es el separador decimal, p. ej. "1.000" = 1000,
    # "2.534,5" = 2534.5 (visto en Echevarne). Se comprueba esta forma
    # primero porque un simple "," -> "." no la distingue de un valor con
    # "." como separador decimal normal (el resto de perfiles, p. ej.
    # "-3.0" en HUGTIP) — un "." solo cuenta como separador de millares si
    # va seguido de exactamente 3 dígitos.
    if re.fullmatch(r"[-+]?\d{1,3}(\.\d{3})*(,\d+)?", candidate):
        return float(candidate.replace(".", "").replace(",", "."))
    candidate = candidate.replace(",", ".")
    if re.fullmatch(r"[-+]?\d+(\.\d+)?", candidate):
        return float(candidate)
    return None


# HUGTIP escribe la fecha con el mes en catalán y la hora pegada sin
# separador ("13 de nov. 202411:23:16"), en vez de con barras o guiones.
# Con el nombre del mes abreviado a sus 3 primeras letras basta para cubrir
# tanto la forma abreviada ("nov.") como la completa ("novembre").
_CATALAN_MONTH_PREFIXES = {
    "gen": 1, "feb": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "oct": 10, "nov": 11, "des": 12,
}
# "de" se eufoniza en "d'" delante de mes que empieza por vocal ("17 d'abr.
# 2025", visto en un informe real de 2025 con apóstrofo tipográfico ’ —
# U+2019 — en vez de recto '); `d.?` admite "de" (la "e" cae en el `.?`) o
# "d" + cualquier apóstrofo de un carácter, sin enumerar los dos glifos.
_CATALAN_DATE_RE = re.compile(
    r"(\d{1,2})\s+d.?\s*([A-Za-zçÇ]+)\.?\s*(\d{4})(?:\D{0,3}(\d{1,2}):(\d{2})(?::(\d{2}))?)?",
    re.IGNORECASE,
)


def _parse_date(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    # Día/mes admiten 1 o 2 dígitos y el año 2 o 4 (la plantilla 2023-2024
    # escribe "Recepció: 03/11/23 (08:46)", con año a 2 dígitos y la hora
    # entre paréntesis en vez de tras un separador de espacio/coma).
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})(?:\D+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", text)
    if m:
        day, month, year, hh, mm, ss = m.groups()
        if len(year) == 2:
            year = f"20{year}"
    else:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:\D+(\d{2}):(\d{2})(?::(\d{2}))?)?", text)
        if m:
            year, month, day, hh, mm, ss = m.groups()
        else:
            m = _CATALAN_DATE_RE.search(text)
            if not m:
                return None
            day, month_name, year, hh, mm, ss = m.groups()
            month = _CATALAN_MONTH_PREFIXES.get(strip_accents(month_name).lower()[:3])
            if month is None:
                return None
    date_part = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    if hh:
        return f"{date_part} {int(hh):02d}:{mm}:{ss or '00'}"
    return date_part


def _is_heading(line: str) -> bool:
    if not line.strip() or ":" in line or line != line.upper():
        return False
    letters = re.sub(r"[^A-ZÀÁÈÉÌÍÒÓÙÚÏÜÇÑ]", "", line)
    return len(letters) >= 3


def _normalize_heading(line: str) -> str:
    text = re.sub(r"\(\s*[\d.]+-?\d*\s*\)", "", line)
    return strip_accents(text).upper().strip()


def _parse_range_bounds(ref_text: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    if not ref_text:
        return None, None
    mm = re.match(r"(-?[\d.,]+)\s*-\s*(-?[\d.,]+)$", ref_text)
    if mm:
        return _to_float(mm.group(1)), _to_float(mm.group(2))
    if ref_text.startswith(">"):
        return _to_float(ref_text.lstrip(">= ")), None
    if ref_text.startswith("<"):
        return None, _to_float(ref_text.lstrip("<= "))
    if ref_text.lower().startswith("inf"):
        return None, _to_float(re.sub(r"(?i)^inf\.?\s*", "", ref_text))
    return None, None


def _extract_range(content: str) -> tuple[str, Optional[str], Optional[float], Optional[float]]:
    m = PAREN_RANGE_RE.search(content) or BRACKET_RANGE_RE.search(content) or RANGE_RE.search(content)
    if not m:
        m = OPEN_PAREN_RANGE_RE.search(content)
        if m:
            return content[: m.start()].strip(), f">= {m.group('low')}", _to_float(m.group("low")), None
        return content, None, None, None
    ref_text = m.group("range").strip()
    remainder = content[: m.start()].strip()
    ref_low, ref_high = _parse_range_bounds(ref_text)
    return remainder, ref_text, ref_low, ref_high


def _parse_interfaced_value_line(content: str) -> dict[str, Any]:
    """Extrae valor/unidad/rango de la línea `‡ <valor> <unidad> (<rango>)[
    prosa]` de un resultado "interfaced" (p. ej. Quirón): el nombre de la
    prueba va en la línea siguiente, combinado por `_parse_lines`."""
    m = PAREN_RANGE_ANY_RE.search(content)
    if m:
        ref_text = m.group("range").strip()
        value_unit = content[: m.start()].strip()
    else:
        ref_text = None
        value_unit = content
    ref_low, ref_high = _parse_range_bounds(ref_text)
    flag_pdf, value_raw, unit = _extract_value_unit(value_unit)
    return {
        "loinc_code": None,
        "value_raw": value_raw,
        "value_num": _to_float(value_raw) if value_raw else None,
        "unit": unit,
        "ref_low": ref_low,
        "ref_high": ref_high,
        "ref_text": ref_text,
        "flag_pdf": flag_pdf,
    }


def _merge_dot_leader_splits(lines: list[str]) -> list[str]:
    """Recompone en una sola línea la fila de resultado con puntos de relleno
    partida en 3 líneas físicas (ver `_CID_MARKER_LINE_RE`): descarta el
    marcador de flecha (línea 2) y pega la unidad/rango (línea 3) tras el
    valor de la línea 1 — `compute_flag` recalcula alto/bajo del propio
    rango numérico de todos modos, así que no hace falta interpretar la
    dirección de la flecha perdida."""
    merged: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if (
            i + 2 < n
            and DOT_LEADER_RE.match(line.strip())
            and _CID_MARKER_LINE_RE.match(lines[i + 1].strip())
        ):
            merged.append(f"{line.rstrip()} {lines[i + 2].strip()}")
            i += 3
            continue
        merged.append(line)
        i += 1
    return merged


def _is_value_token(token: str) -> bool:
    core = token.lstrip(ARROW_UP + ARROW_DOWN)
    return bool(NUMERIC_TOKEN_RE.fullmatch(core) or CENSORED_VALUE_RE.fullmatch(core))


def _split_name_rest(
    content: str, known_text_values: list[str], prefer_last_numeric_token: bool = False
) -> tuple[str, Optional[str], str]:
    """Separa 'Nombre (LOINC) resto' o, si no hay LOINC, 'Nombre resto'.

    `prefer_last_numeric_token`: para perfiles `bare_range_is_result` (p.
    ej. HUGTIP), donde `content` ya ha pasado por `_extract_range` habiendo
    encontrado un rango real al final de la línea original — así que un
    número suelto al final de `content` (sin unidad detrás) es el valor,
    nunca un límite de rango descolgado (ver el comentario de más abajo,
    que sí puede pasar en líneas SIN rango detectado, la otra rama). Sin
    esto, un nombre de prueba con un número suelto en medio ("Srm-Alfa 1
    Globulines; fr. massa. 2.7", "Alfa-1-globulina") hacía que se tomara
    ese "1" como el valor en vez del "2.7" real al final."""
    m = LOINC_NAME_RE.match(content)
    if m:
        return m.group("name").strip(), m.group("loinc"), m.group("rest").strip()
    tokens = content.split()
    value_idx = None
    if prefer_last_numeric_token:
        for i in range(len(tokens) - 1, -1, -1):
            if _is_value_token(tokens[i]):
                value_idx = i
                break
    else:
        for i in range(len(tokens) - 1, -1, -1):
            if not _is_value_token(tokens[i]):
                continue
            value_idx = i
            # Preferimos un número seguido de una unidad (token no numérico) al
            # último número de la línea a secas: alguna plantilla sin LOINC
            # pierde el símbolo "<"/">" de un límite de rango suelto al final
            # ("Colesterol HDL 47 mg/dL 40", el "40" es el mínimo de
            # referencia, no el valor) y `_extract_range` no lo reconoce por
            # delante; sin esto, ese límite suelto se confundía con el valor y
            # el nombre real quedaba con el valor/unidad pegados, generando un
            # "parámetro" nuevo distinto por cada valor visto en vez de
            # agruparse con el resto de esa misma prueba.
            if i + 1 < len(tokens) and not NUMERIC_TOKEN_RE.fullmatch(tokens[i + 1]):
                break
    if value_idx is None:
        for phrase in known_text_values:
            if content.lower().endswith(phrase.lower()):
                return content[: -len(phrase)].strip(), None, content[-len(phrase):]
        return content.strip(), None, ""
    name = " ".join(tokens[:value_idx])
    rest = " ".join(tokens[value_idx:])
    return name.strip(), None, rest


def _extract_value_unit(rest: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    rest = rest.strip()
    flag_pdf = None
    if rest.startswith(ARROW_UP):
        flag_pdf, rest = "alto", rest[1:].lstrip()
    elif rest.startswith(ARROW_DOWN):
        flag_pdf, rest = "bajo", rest[1:].lstrip()
    if not rest:
        return flag_pdf, None, None
    tokens = rest.split()
    if NUMERIC_TOKEN_RE.fullmatch(tokens[0]) or CENSORED_VALUE_RE.fullmatch(tokens[0]):
        value_raw = tokens[0]
        unit = " ".join(tokens[1:]) if len(tokens) > 1 else None
    else:
        value_raw, unit = rest, None
    return flag_pdf, value_raw, unit


def _bound_is_minimum(name: str, flag_pdf: Optional[str], value_raw: Optional[str], bound: Optional[float]) -> bool:
    """Si un límite de rango suelto (sin "<"/">") es un mínimo. El colesterol
    HDL siempre lo es ("más alto es mejor"); en el resto manda la marca del
    PDF (↓ = el valor está bajo el mínimo) y, sin marca, el valor es normal:
    si supera el límite, este solo puede ser un mínimo."""
    if _HDL_RE.search(name) and not _NON_HDL_RE.search(name):
        return True
    if flag_pdf:
        return flag_pdf == "bajo"
    value = _to_float((value_raw or "").lstrip("<>=≤≥"))
    if value is None or bound is None:
        return False
    return value > bound or (value == bound and value_raw.startswith(">"))


def parse_result_line(
    content: str, known_text_values: list[str] = (), prefer_last_numeric_token: bool = False
) -> dict[str, Any]:
    remainder, ref_text, ref_low, ref_high = _extract_range(content)
    name, loinc_code, rest = _split_name_rest(remainder, list(known_text_values), prefer_last_numeric_token)
    # Alguna plantilla antigua marca con "* " las determinaciones calculadas
    # ("* Colesterol LDL"); sin quitarlo, la misma prueba tendría dos ids.
    name = re.sub(r"^\*\s*", "", name)
    flag_pdf, value_raw, unit = _extract_value_unit(rest)
    value_num = _to_float(value_raw) if value_raw else None

    # Algunas revisiones del informe pierden el símbolo "<"/">" de un rango
    # (queda solo el número, pegado a la unidad); si no se ha detectado
    # ningún rango, se interpreta ese número suelto como límite superior
    # ("< N") en vez de dejarlo colgado dentro de la unidad. Pero no siempre
    # es un máximo: el folato o el filtrado glomerular pierden un mínimo
    # ("Folat sèrum ↓<1 ng/mL 2.9", en la plantilla antigua "( 2.9 -"). La
    # dirección se deduce de la marca del PDF y, sin marca (valor normal),
    # de si el valor supera el límite — ver `_bound_is_minimum`.
    if ref_low is None and ref_high is None and unit:
        unit_tokens = unit.split()
        if NUMERIC_TOKEN_RE.fullmatch(unit_tokens[-1]):
            bound = _to_float(unit_tokens[-1])
            if _bound_is_minimum(name, flag_pdf, value_raw, bound):
                ref_low = bound
                ref_text = f"> {unit_tokens[-1]}"
            else:
                ref_high = bound
                ref_text = f"< {unit_tokens[-1]}"
            unit = " ".join(unit_tokens[:-1]) or None
    return {
        "raw_name": name,
        "loinc_code": loinc_code,
        "value_raw": value_raw,
        "value_num": value_num,
        "unit": unit,
        "ref_low": ref_low,
        "ref_high": ref_high,
        "ref_text": ref_text,
        "flag_pdf": flag_pdf,
    }


def _age_band(m: re.Match) -> tuple[int, int]:
    """Edades (años cumplidos, ambos extremos incluidos) de una franja
    `AGE_BAND_RE`: "<1" = 0, "1-3" = 1..3, ">19" = 20 en adelante."""
    if m.group("under"):
        return 0, int(m.group("under")) - 1
    if m.group("over"):
        return int(m.group("over")) + 1, 200
    return int(m.group("lo")), int(m.group("hi"))


def _age_on(birth_date: str, on_date: str) -> int:
    (y1, m1, d1), (y2, m2, d2) = (tuple(int(x) for x in d[:10].split("-")) for d in (birth_date, on_date))
    return y2 - y1 - ((m2, d2) < (m1, d1))


def _set_range(result: dict[str, Any], ref_text: str) -> None:
    result["ref_text"] = ref_text
    result["ref_low"], result["ref_high"] = _parse_range_bounds(ref_text)


def apply_age_bands(results: list[dict[str, Any]], birth_date: Optional[str], fallback_date: Optional[str]) -> None:
    """Resuelve las franjas de referencia por edad (`age_bands`, ver
    `following_range_labels`): elige la de la edad del paciente en la fecha
    de la muestra (o `fallback_date`). Sin fecha de nacimiento la franja se
    deja pendiente, para que `ingest` la resuelva con la del paciente ya
    guardado (alguna plantilla, p. ej. Synlab, trae a veces "F. Nac." vacío);
    nunca se adivina."""
    for result in results:
        on_date = result.get("sample_date") or fallback_date
        if not (result.get("age_bands") and birth_date and on_date):
            continue
        age = _age_on(birth_date, on_date)
        ref_text = next((text for lo, hi, text in result["age_bands"] if lo <= age <= hi), None)
        if ref_text:
            _set_range(result, ref_text)
            del result["age_bands"]


def compute_flag(value_num: Optional[float], ref_low: Optional[float], ref_high: Optional[float]) -> Optional[str]:
    if value_num is None:
        return None
    if ref_low is not None and value_num < ref_low:
        return "bajo"
    if ref_high is not None and value_num > ref_high:
        return "alto"
    if ref_low is not None or ref_high is not None:
        return "normal"
    return None


def _parse_lines(lines: list[str], profile: ParserProfile) -> dict[str, Any]:
    """Aplica el motor de parseo a `lines` usando las tablas de `profile`."""
    header: dict[str, str] = {}
    results: list[dict[str, Any]] = []
    current_section: Optional[str] = None
    current_group: Optional[str] = None
    current_sample_date: Optional[str] = None
    in_header = True
    expect_name_next = False
    previous_line: Optional[str] = None
    pending_interfaced: Optional[dict[str, Any]] = None
    # Último resultado sin rango propio, a la espera de que una línea
    # posterior se lo dé (ver `following_range_labels`).
    range_target: Optional[dict[str, Any]] = None
    range_target_idx = 0
    collecting_range = False

    if profile.dot_leader_result:
        lines = _merge_dot_leader_splits(lines)

    if profile.sample_date_label:
        # Alguna plantilla (p. ej. Quirón) solo indica la fecha de muestra
        # una vez, al final del documento, después de todos los resultados;
        # sin este preescaneo, los resultados anteriores a esa línea se
        # guardarían con `sample_date=None` en vez de heredarla.
        for raw_line in lines:
            fields = _extract_labeled_fields(raw_line.strip(), [profile.sample_date_label], profile.boundary_re)
            if "sample_date" in fields:
                current_sample_date = _parse_date(fields["sample_date"])
                break

    def _add_result(content: str, prefer_last_numeric_token: bool = False) -> None:
        nonlocal range_target, range_target_idx, collecting_range
        parsed = parse_result_line(content, profile.known_text_values, prefer_last_numeric_token)
        if not parsed["raw_name"]:
            # El nombre y el valor han quedado en líneas separadas (algunas
            # plantillas antiguas cortan la fila cuando el nombre es largo);
            # sin nombre fiable, se descarta la fila en vez de guardarla mal.
            return
        parsed["section"] = current_section
        parsed["test_group"] = current_group
        parsed["sample_date"] = current_sample_date
        results.append(parsed)
        range_target = parsed if parsed["ref_text"] is None else None
        range_target_idx, collecting_range = idx, False

    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        for pattern, replacement in profile.line_substitutions:
            line = pattern.sub(replacement, line)
        # Antes de `strip_mid_tokens`: en Synlab la marca que delata la fila
        # de resultado sin rango (" ü ") es justo uno de esos tokens.
        unranged = bool(profile.unranged_result_re and profile.unranged_result_re.search(line))
        for flag in profile.strip_trailing_flags:
            if line.endswith(flag):
                line = line[: -len(flag)].rstrip()
        for token in profile.strip_mid_tokens:
            line = re.sub(rf"\s+{re.escape(token)}\s+", " ", line)

        if profile.ignore_line_patterns and any(p.search(line) for p in profile.ignore_line_patterns):
            continue

        prev_line, previous_line = previous_line, line

        # Rango de un resultado anterior que no lo traía en su fila (ver
        # `following_range_labels`); solo dentro de unas pocas líneas, para
        # no asignar a un resultado el rango de otro texto más abajo.
        if range_target is not None and idx - range_target_idx > 6:
            range_target = None
        if range_target is not None and profile.following_range_labels:
            if any(line.startswith(label) for label in profile.following_range_labels):
                collecting_range = True
                continue
            if collecting_range:
                band = AGE_BAND_RE.match(line)
                if band:
                    range_target.setdefault("age_bands", []).append((*_age_band(band), band.group("range").strip()))
                    range_target_idx = idx
                    continue
                bare = LEADING_RANGE_RE.match(line)
                if bare and "age_bands" not in range_target:
                    _set_range(range_target, bare.group("range").strip())
                    range_target = None
                    continue
                collecting_range = False

        # Perfiles cuyas secciones no se distinguen por mayúsculas (p. ej.
        # Quirón) sino por preceder a una línea de cabecera de columna fija
        # ("Prueba Resultado Unidades Valores de Normalidad"): la línea justo
        # anterior a esa es el título de sección.
        if profile.section_after_anchor and line == profile.section_after_anchor:
            if prev_line:
                current_section = prev_line
            current_group = None
            in_header = False
            continue

        # Resultado "interfaced" partido en dos líneas (ver
        # `interfaced_result_prefix`): esta línea es el nombre de la prueba
        # cuyo valor/unidad/rango ya se leyó en la línea anterior.
        if pending_interfaced is not None:
            parsed = dict(pending_interfaced)
            pending_interfaced = None
            parsed["raw_name"] = line
            if parsed["raw_name"]:
                parsed["section"] = current_section
                parsed["test_group"] = current_group
                parsed["sample_date"] = current_sample_date
                results.append(parsed)
            in_header = False
            continue

        if profile.interfaced_result_prefix and line.startswith(profile.interfaced_result_prefix):
            in_header = False
            content = line[len(profile.interfaced_result_prefix):].strip()
            pending_interfaced = _parse_interfaced_value_line(content)
            continue

        # Plantillas muy antiguas no tienen ninguna etiqueta "Pacient:": el
        # nombre aparece suelto, en la línea siguiente a un título "Informe".
        if expect_name_next:
            expect_name_next = False
            if in_header and not header.get("full_name") and "," in line and re.fullmatch(r"[A-Za-zÀ-ÿ'’.\-, ]+", line):
                header["full_name"] = line
                continue

        if profile.sample_date_label:
            sample_fields = _extract_labeled_fields(line, [profile.sample_date_label], profile.boundary_re)
            if "sample_date" in sample_fields:
                current_sample_date = _parse_date(sample_fields["sample_date"]) or current_sample_date

        if profile.metadata_row_re:
            m = profile.metadata_row_re.match(line)
            if m:
                groups = m.groupdict()
                for key in ("report_number", "request_date", "validation_date"):
                    if groups.get(key):
                        header.setdefault(key, groups[key])
                if groups.get("sample_date"):
                    current_sample_date = _parse_date(groups["sample_date"]) or current_sample_date
                continue

        if profile.full_name_re and "full_name" not in header:
            m = profile.full_name_re.search(line)
            if m:
                header["full_name"] = m.group("name").strip()

        if in_header and INFORME_TITLE_RE.match(line):
            expect_name_next = True
        # Las etiquetas de cabecera se buscan en todo el documento, no solo
        # mientras `in_header` es verdadero: algunos informes traen líneas de
        # ruido (marcas de agua, texto de redacción) que `_is_heading` toma
        # por un título y cierran el modo cabecera antes de llegar a
        # "Pacient:"/"NIF/DNI:"/etc. `setdefault` evita que una coincidencia
        # tardía o espuria sobrescriba un valor ya capturado antes.
        for key, value in _extract_labeled_fields(line, profile.header_labels, profile.boundary_re).items():
            header.setdefault(key, value)

        section_match = SECTION_LINE_RE.match(line)
        result_match = RESULT_LINE_RE.match(line)

        if section_match:
            current_section = section_match.group(1).strip()
            current_group = None
            in_header = False
            continue

        if result_match:
            in_header = False
            if NON_RESULT_PREFIX_RE.match(result_match.group(1).strip()):
                continue
            _add_result(result_match.group(1))
            continue

        if profile.dot_leader_result:
            m = DOT_LEADER_RE.match(line)
            if m:
                in_header = False
                name = m.group("name").strip()
                if profile.single_result_name_placeholder and name.upper() == profile.single_result_name_placeholder.upper():
                    name = current_section or name
                remainder, ref_text, ref_low, ref_high = _extract_range(m.group("rest"))
                flag_pdf, value_raw, unit = _extract_value_unit(remainder)
                if name:
                    results.append({
                        "raw_name": name,
                        "loinc_code": None,
                        "value_raw": value_raw,
                        "value_num": _to_float(value_raw) if value_raw else None,
                        "unit": unit,
                        "ref_low": ref_low,
                        "ref_high": ref_high,
                        "ref_text": ref_text,
                        "flag_pdf": flag_pdf,
                        "section": current_section,
                        "test_group": current_group,
                        "sample_date": current_sample_date,
                    })
                continue

        if profile.detect_headings and _is_heading(line):
            in_header = False
            heading = _normalize_heading(line)
            # Sin `known_sections` declarado, cada título detectado es
            # directamente la sección (p. ej. Echevarne, un único nivel de
            # título por determinación, sin la jerarquía sección/grupo de
            # Maresme que sí necesita distinguir cuáles son "de verdad" una
            # sección de las que son un subgrupo).
            if not profile.known_sections or heading in profile.known_sections:
                current_section = line.strip()
                current_group = None
            else:
                current_group = line.strip()
            continue

        # Plantillas muy antiguas no llevan marcador "(n)" ni código LOINC en
        # las filas de resultado; se reconocen porque terminan en un rango
        # entre paréntesis ("Nombre valor unidad ( bajo - alto )").
        if PAREN_RANGE_RE.search(line) or OPEN_PAREN_RANGE_RE.search(line):
            in_header = False
            _add_result(line)
            continue

        # Igual que el caso anterior pero con el rango entre corchetes (p.
        # ej. Synlab: "Hematíes 3,89 x106/mm³ [ 3,9 - 5,2 ]"). Un valor no
        # realizado ("DNR") sin ningún número delante del rango no tiene
        # `value_raw` reconocible tras separar nombre/valor — se descarta en
        # vez de guardar una fila sin valor.
        if BRACKET_RANGE_RE.search(line):
            in_header = False
            if parse_result_line(line, profile.known_text_values)["value_raw"] is None:
                continue
            _add_result(line)
            continue

        # Perfiles sin marcador "(n)" ni rango entre paréntesis (p. ej.
        # HUGTIP): una línea que termine en un rango sin paréntesis se trata
        # también como resultado. No se activa por defecto (`bare_range_is_result`,
        # ver `parser_profiles.py`) porque sin marcador ni paréntesis que lo
        # delimiten, es más fácil que texto narrativo termine pareciendo un
        # rango por casualidad.
        if profile.bare_range_is_result and RANGE_RE.search(line):
            in_header = False
            # Perfiles con "resultado principal" seguido de una línea de
            # método/unidad secundaria que también acaba en un rango (p. ej.
            # HUGTIP: "Mètode enzimàtic(AE) 6.4 mmol/L 2.8 - 7.1" justo
            # después del resultado real "Srm-Urea..."), evita duplicar como
            # si fuera otra determinación distinta.
            if any(marker in line for marker in profile.bare_range_skip_if_contains):
                continue
            # Texto narrativo/nota a pie que por casualidad termina en un
            # rango numérico (p. ej. "Valors de normalitat en pacients amb
            # insuficiència renal: 0.37 - 3.1", una referencia alternativa
            # para cierta población, no un resultado) no tiene ningún valor
            # delante del rango — un resultado real siempre lo tiene, sea
            # numérico o un texto reconocido (`known_text_values`). Sin
            # marcador "(n)" ni paréntesis que delimiten la fila (a
            # diferencia de los otros casos de arriba), es el único punto
            # donde hace falta esta comprobación extra.
            if parse_result_line(line, profile.known_text_values, prefer_last_numeric_token=True)["value_raw"] is None:
                continue
            _add_result(line, prefer_last_numeric_token=True)
            continue

        # Fila de resultado sin rango en su propia línea (ver
        # `unranged_result_re`); el rango, si lo hay, llega en líneas
        # posteriores (`following_range_labels`).
        if unranged:
            in_header = False
            if parse_result_line(line, profile.known_text_values)["value_raw"] is not None:
                _add_result(line)
            continue

    header["birth_date"] = _parse_date(header.get("birth_date"))
    header["request_date"] = _parse_date(header.get("request_date"))
    header["validation_date"] = _parse_date(header.get("validation_date"))
    header["sex"] = _parse_sex(header.get("sex"))
    apply_age_bands(results, header["birth_date"], header["request_date"])
    for result in results:
        suffix = profile.section_name_suffixes.get(result.get("section") or "")
        if suffix and suffix not in normalize_test_name(result["raw_name"]).split():
            result["raw_name"] = f"{result['raw_name']} {suffix}"
    # Solo el primer token: alguna plantilla añade el tipo de asistencia
    # entre paréntesis detrás ("23H005387 (Hospitalització)"), y el CIP de
    # HUGTIP compacta llega con ruido de extracción pegado ("XXXX0000000000 aa").
    header["assistance_number"] = (header.get("assistance_number") or "").split(" ")[0] or None
    header["cip"] = (header.get("cip") or "").split(" ")[0] or None
    # Un NHC real es un único token alfanumérico; alguna maquetación (vista
    # en SNB/Eurofins) cuela la dirección del paciente en esa columna
    # ("Calle, 28. 1o 2a"), que no debe guardarse como NHC ni usarse para
    # emparejar pacientes.
    if header.get("nhc") and not re.fullmatch(r"\S+", header["nhc"]):
        header["nhc"] = None
    header.setdefault("full_name", None)
    header.setdefault("dni", None)
    header.setdefault("nhc", None)
    header.setdefault("report_number", None)

    return {"header": header, "results": results}


# Primera palabra del campo "Sexe/Sexo" en cada plantilla: "Home"/"Dona"
# (Maresme, Echevarne), "M"/"F" (HUGTIP), "HOMBRE"/"MUJER" (Synlab/SNB),
# "VARON" (Quirón).
_SEX_VALUES = {
    "home": "Hombre", "hombre": "Hombre", "varon": "Hombre", "m": "Hombre", "h": "Hombre",
    "dona": "Mujer", "mujer": "Mujer", "f": "Mujer",
}


def _parse_sex(text: Optional[str]) -> Optional[str]:
    words = strip_accents(text or "").lower().split()
    return _SEX_VALUES.get(words[0].strip("/")) if words else None


def parse_report(pdf_path: Path) -> dict[str, Any]:
    """Parsea un informe completo: cabecera del paciente y filas de resultados.

    Primero se detecta a qué perfil (centro/laboratorio) corresponde el PDF
    (`parser_profiles.detect_profile`); si el perfil detectado no tiene motor
    de parseo todavía (`manual_review_only`, incluido el perfil interno
    "no reconocido" cuando ninguno coincide), se devuelve sin cabecera ni
    resultados en vez de forzar sobre él la gramática de otro centro.
    """
    lines = extract_lines(pdf_path)
    profile = detect_profile(lines)
    if not profile.manual_review_only and profile.extract_x_tolerance is not None:
        # Se detecta el perfil con la extracción por defecto (las cadenas de
        # firma sin espacios internos no la necesitan) y solo se reextrae
        # con la tolerancia propia del perfil si hace falta — ver
        # `extract_lines`.
        lines = extract_lines(pdf_path, x_tolerance=profile.extract_x_tolerance)

    if profile.manual_review_only:
        header = {
            "full_name": None, "dni": None, "nhc": None, "report_number": None,
            "birth_date": None, "request_date": None, "validation_date": None,
        }
        results: list[dict[str, Any]] = []
    else:
        parsed = _parse_lines(lines, profile)
        header, results = parsed["header"], parsed["results"]

    return {
        "header": header,
        "results": results,
        "source_file": pdf_path.name,
        "format_id": profile.id,
        "format_name": profile.name,
        "format_short_name": profile.short_name or profile.name,
        "manual_review_only": profile.manual_review_only,
    }
