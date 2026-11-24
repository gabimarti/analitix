# ---------------------------------------------------------------------------
# Script: profile_assistant.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-11-24
# ---------------------------------------------------------------------------
"""Asistente de plantillas de laboratorio: la lógica, sin interfaz.

Analiza las líneas de un PDF (las mismas que ve el motor,
`pdf_parser.extract_lines`) y propone, para que el usuario las acepte o
corrija, las piezas de una plantilla `.toml` nueva:

- etiquetas de cabecera y a qué campo corresponden (nombre, fechas, DNI...),
- textos que identifican al laboratorio (firma),
- secciones y cabeceras de columna,
- cuál de las gramáticas de fila del motor encaja y cuántas filas captura,
- la convención decimal del documento y los valores ambiguos («7.349»),
- las unidades (conocidas, desconocidas o sospechosas),
- si cada parámetro ya existe (catálogo o base de datos) o puede ser el mismo
  que otro (con las mismas reglas que `alias_audit`).

Después genera el `.toml` (escritor propio para el esquema conocido), lo
valida como una plantilla del usuario, comprueba que no lleva ningún dato
del paciente y lo guarda en `config.USER_PARSER_PROFILES_DIR`, con copia de
la versión anterior. También evalúa una plantilla sobre un documento y
compara resultados entre plantillas o con lo guardado en la base de datos.

Privacidad: las líneas del PDF y los valores que se leen solo están en
memoria. Las propuestas de etiquetas guardan **el tipo** de valor (fecha,
documento, número, texto), nunca el valor; la plantilla solo lleva
etiquetas y patrones. Nada de este módulo escribe en el log texto del PDF.
"""

from __future__ import annotations

import re
import shutil
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from analitix import config, pdf_parser as engine
from analitix.alias_audit import (
    TestGroup,
    add_result,
    find_proposals,
    panel_ids,
    unit_dimension,
    unit_relation,
)
from analitix.catalog import canonical_id_for, known_canonical_ids
from analitix.parser_profiles import (
    HEADER_FIELDS,
    KNOWN_PROFILE_KEYS,
    PROFILE_ID_RE,
    ParserProfile,
    ProfileValidationError,
    check_pattern,
    load_profiles,
    matching_profiles,
    profile_from_data,
    reload_profiles,
    validate_user_profile_data,
)
from analitix.textutils import normalize_test_name, strip_accents

DATE_FIELDS = ("birth_date", "request_date", "validation_date", "sample_date")
# Campos que identifican al paciente o al informe: sus valores nunca pueden
# acabar dentro de una plantilla.
PATIENT_FIELDS = ("full_name", "birth_date", "dni", "nhc", "cip", "assistance_number")
PRIVATE_FIELDS = (*PATIENT_FIELDS, "report_number")

# -- 1. Etiquetas de cabecera ------------------------------------------------

# Palabras (sin acentos, minúsculas, sin signos) que forman etiquetas de
# cabecera en los informes vistos (catalán y castellano). Al buscar hacia
# atrás desde los «:», la etiqueta se alarga mientras las palabras sean de
# esta lista; la primera que no lo es (normalmente el valor del campo
# anterior) la corta. Se completa con los `boundary_terms` de las
# plantillas instaladas.
_BASE_LABEL_WORDS = frozenset(
    """
    nom nombre cognoms apellidos pacient paciente i y o de del la el en d fecha data hora
    naixement nacimiento nac f edad edat sexe sexo dni nif nie ipf identificacion passaport
    pasaporte n no num numero historia clinica nhc cip targeta tarjeta sanitaria autonomic
    autonomico sns peticio peticion laboratorio laboratori lab analisi analisis registro
    registre sollicitud solicitud activacio activacion validacio validacion edicion edicio
    finalitzacio finalizacion signatura firma recepcio recepcion mostra muestra toma presa
    extraccio extraccion referencia centre centro servei servicio doctor metge medico origen
    cama assistencia asistencia procedencia sollicitant solicitante razon social cargo
    informe ref externa tipus tipo programada destinatari destinatario
    """.split()
)

KEY_HINTS: dict[str, frozenset[str]] = {
    "full_name": frozenset({"nom", "nombre", "pacient", "paciente", "cognoms", "apellidos"}),
    "birth_date": frozenset({"naixement", "nacimiento", "nac"}),
    "dni": frozenset({"dni", "nif", "nie", "ipf", "identificacion", "passaport", "pasaporte"}),
    "nhc": frozenset({"nhc", "historia"}),
    "cip": frozenset({"cip", "targeta", "tarjeta"}),
    "sex": frozenset({"sexe", "sexo"}),
    "assistance_number": frozenset({"assistencia", "asistencia"}),
    "report_number": frozenset({"peticio", "peticion", "laboratorio", "lab", "analisi"}),
    "request_date": frozenset(
        {"registro", "registre", "peticio", "peticion", "sollicitud", "solicitud", "activacio"}
        | {"activacion", "programada"}
    ),
    "validation_date": frozenset(
        {"validacio", "validacion", "edicion", "edicio", "finalitzacio", "signatura", "firma"}
    ),
    "sample_date": frozenset(
        {"mostra", "muestra", "recepcio", "recepcion", "extraccio", "extraccion", "toma"}
        | {"presa"}
    ),
}

_DNI_RE = re.compile(r"^[XYZ]?\d{7,8}[A-Z]\b", re.IGNORECASE)
_DIGIT_RE = re.compile(r"\d")


def _norm_word(token: str) -> str:
    """Palabra comparable: sin acentos, minúsculas, sin «d'»/«l'» delante y
    sin signos («Nº» -> «n», «D.N.I.» -> «dni», «Sol·licitud» ->
    «sollicitud»)."""
    word = strip_accents(token).lower()
    word = re.sub(r"^[dl]['’]", "", word)
    return re.sub(r"[^a-z0-9]", "", word)


def _label_words() -> frozenset[str]:
    words = set(_BASE_LABEL_WORDS)
    for path in sorted(config.PARSER_PROFILES_DIR.glob("*.toml")):
        with open(path, "rb") as f:
            data = tomllib.load(f)
        for term in data.get("boundary_terms", []):
            words.update(w for w in (_norm_word(t) for t in term.split()) if w)
    return frozenset(words)


def _value_kind(value: str) -> str:
    """Tipo del valor de un campo, sin guardarlo: «fecha», «documento» (DNI o
    NIE), «número», «texto» o «vacío»."""
    value = value.strip(" :/-\t")
    if not value:
        return "vacío"
    if value[0].isdigit() and engine._parse_date(" ".join(value.split()[:4])):
        return "fecha"
    if _DNI_RE.match(value):
        return "documento"
    if _DIGIT_RE.search(value.split()[0]):
        return "número"
    return "texto"


@dataclass
class LabelCandidate:
    """Etiqueta de cabecera encontrada en el documento («Fecha Recepción»).
    No guarda el valor que la sigue, solo su tipo."""

    label: str
    line_idx: int
    value_kind: str
    suggested_key: str | None
    occurrences: int = 1


@dataclass
class _Field:
    label: str
    label_start: int
    value: str


def _fields_in_line(line: str, vocabulary: frozenset[str]) -> list[_Field]:
    """Pares etiqueta/valor de una línea «Etiqueta: valor Otra: valor»."""
    # Echevarne separa campos con «//» sin espacios: «...A//Data naixement:».
    text = line.replace("//", " // ")
    tokens = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", text)]
    found: list[tuple[str, int, int]] = []
    for m in re.finditer(":", text):
        i = m.start()
        if 0 < i < len(text) - 1 and text[i - 1].isdigit() and text[i + 1].isdigit():
            continue  # una hora, «08:00»
        if text[i + 1 : i + 3] == "//":
            continue  # una dirección web
        before = [t for t in tokens if t[1] <= i or (t[0] < i < t[1])]
        collected: list[tuple[int, int, str]] = []
        for start, end, tok in reversed(before):
            tok = tok[: i - start] if end > i else tok
            if not collected:
                if not re.search(r"[^\W\d_]", tok):
                    break
                collected.insert(0, (start, end, tok))
                continue
            if tok == "/":
                collected.insert(0, (start, end, tok))
                continue
            if tok == "//" or _norm_word(tok) not in vocabulary:
                break
            collected.insert(0, (start, end, tok))
        while collected and collected[0][2] == "/":
            collected.pop(0)
        if collected:
            label = " ".join(t[2] for t in collected).strip()
            found.append((label, collected[0][0], m.end()))
    fields = []
    for n, (label, start, value_start) in enumerate(found):
        value_end = found[n + 1][1] if n + 1 < len(found) else len(text)
        fields.append(_Field(label, start, text[value_start:value_end].strip(" \t/")))
    return fields


def _suggest_key(label: str, kind: str) -> str | None:
    if kind == "vacío":
        return None
    words = {_norm_word(t) for t in label.replace("/", " ").split()}
    joined = "".join(sorted(words))
    best, best_score = None, 0
    for key, hints in KEY_HINTS.items():
        if (key in DATE_FIELDS) != (kind == "fecha"):
            continue
        score = 2 * len(words & hints) or int(any(len(h) >= 5 and h in joined for h in hints))
        if kind == "documento" and key == "dni":
            score += 1
        if score > best_score:
            best, best_score = key, score
    return best


def header_label_candidates(lines: list[str], max_lines: int = 80) -> list[LabelCandidate]:
    """Etiquetas «texto:» de las primeras `max_lines` líneas, con el campo
    que parecen (o `None`: entonces sirven de frontera, `boundary_terms`)."""
    vocabulary = _label_words()
    candidates: dict[str, LabelCandidate] = {}
    for idx, line in enumerate(lines[:max_lines]):
        for f in _fields_in_line(line.strip(), vocabulary):
            words = [_norm_word(t) for t in f.label.split()]
            if idx >= 15 and not any(w in vocabulary for w in words):
                continue  # «...insuficiència renal: 0.37 - 3.1», no es cabecera
            key = _norm_word(f.label.replace(" ", ""))
            if key in candidates:
                candidates[key].occurrences += 1
                continue
            kind = _value_kind(f.value)
            candidates[key] = LabelCandidate(f.label, idx, kind, _suggest_key(f.label, kind))
    return list(candidates.values())


def label_values(lines: list[str], fields: tuple[str, ...] = PRIVATE_FIELDS) -> set[str]:
    """Valores (en memoria) de las etiquetas que parecen datos del paciente o
    del informe: solo para comprobar que no acaban en la plantilla."""
    vocabulary = _label_words()
    values = set()
    for line in lines:
        for f in _fields_in_line(line.strip(), vocabulary):
            if f.value and _suggest_key(f.label, _value_kind(f.value)) in fields:
                values.add(f.value)
    return values


def label_pattern(label: str) -> str:
    """Patrón de `header_labels` para una etiqueta literal: sin acentos (el
    motor busca sobre la línea sin acentos), cada palabra escapada y
    cualquier espacio entre ellas, terminado en «:»."""
    words = [re.escape(strip_accents(w)) for w in label.split()]
    return r"\s*".join(words) + r"\s*:" if len(words) == 1 else r"\s+".join(words) + r"\s*:"


# -- 2. Firma ------------------------------------------------------------------

ORG_HINTS = (
    "laborator",
    "hospital",
    "clinic",
    "diagnost",
    "enac",
    "www.",
    "http",
    ".com",
    ".es",
    ".cat",
    "s.l.",
    "s.a.",
    "fundaci",
    "consorci",
    "institut",
)


# Líneas que llevan el nombre de una persona (tratamiento o «Apellidos,
# Nombre»): nunca se proponen como firma aunque nombren también al centro.
_PERSON_RE = re.compile(r"\b(?:Sra?|Dra?|D|Dña|Doña|Don)\.?\s|[^\W\d_]{2,},\s*[^\W\d_]{2,}")


@dataclass
class SignatureCandidate:
    """Texto que puede identificar al laboratorio (`signature.requires_any`)."""

    text: str
    line_idx: int
    used_by: list[str]  # plantillas instaladas cuya firma ya lo contiene
    in_other_documents: int  # documentos de otros laboratorios donde aparece


def signature_candidates(
    lines: list[str], other_documents: list[list[str]] = ()
) -> list[SignatureCandidate]:
    """Líneas con el nombre del centro, su web o su acreditación. Primero las
    que ninguna otra plantilla ni ningún otro documento usa."""
    found: dict[str, SignatureCandidate] = {}
    others = [strip_accents("\n".join(doc)) for doc in other_documents]
    for idx, line in enumerate(lines):
        text = line.strip()
        lowered = strip_accents(text).lower()
        if not text or ":" in text or len(text) > 80 or text in found:
            continue
        if not any(hint in lowered for hint in ORG_HINTS) or _PERSON_RE.search(text):
            continue
        deaccented = strip_accents(text)
        used_by = [
            p.id
            for p in load_profiles()
            if any(t in text or t in deaccented or text in t for t in p.signature_requires_any)
        ]
        in_others = sum(deaccented in doc for doc in others)
        found[text] = SignatureCandidate(text, idx, used_by, in_others)
    return sorted(
        found.values(), key=lambda c: (bool(c.used_by), c.in_other_documents, len(c.text))
    )


# -- 3. Secciones y cabeceras de columna --------------------------------------

COLUMN_WORDS = frozenset(
    "prueba prova resultado resultat resultats unidades unidad unitats valores valors "
    "referencia normalidad normalitat rango rang".split()
)


@dataclass
class SectionCandidate:
    line_idx: int
    text: str
    reason: str  # «mayúsculas», «antes de la cabecera de columna», «marcador del motor»


def _is_column_header(line: str) -> bool:
    words = {_norm_word(w) for w in re.split(r"[\s.]+", line)}
    return len(words & COLUMN_WORDS) >= 3


def column_header_lines(lines: list[str]) -> list[tuple[int, str]]:
    """Cabeceras de tabla («Prueba Resultado Unidades Valores de
    Normalidad»), sin repetir."""
    seen, found = set(), []
    for idx, line in enumerate(lines):
        text = line.strip()
        if text and _is_column_header(text) and text not in seen:
            seen.add(text)
            found.append((idx, text))
    return found


def _has_value_token(line: str) -> bool:
    return any(
        _DIGIT_RE.search(t) and engine.NUMERIC_TOKEN_RE.fullmatch(t.strip("()[]"))
        for t in line.split()
    )


def section_candidates(lines: list[str]) -> list[SectionCandidate]:
    """Títulos de sección: el marcador «Secció / Sección X» que el motor ya
    entiende, líneas en mayúsculas sin valores y la línea anterior a cada
    cabecera de columna."""
    found: list[SectionCandidate] = []
    shown = [(i, line.strip()) for i, line in enumerate(lines) if line.strip()]
    for n, (idx, text) in enumerate(shown):
        if _is_column_header(text):
            continue
        if engine.SECTION_LINE_RE.match(text):
            found.append(SectionCandidate(idx, text, "marcador del motor"))
            continue
        nxt = shown[n + 1][1] if n + 1 < len(shown) else ""
        if nxt and _is_column_header(nxt) and ":" not in text and not _DIGIT_RE.search(text):
            found.append(SectionCandidate(idx, text, "antes de la cabecera de columna"))
        elif engine._is_heading(text) and not _has_value_token(text):
            found.append(SectionCandidate(idx, text, "mayúsculas"))
    return found


def _token_shape(token: str) -> str:
    """Forma de un token con cifras, para patrones que no lleven el valor
    concreto: «U00000000» -> `[A-Za-z]+\\d+`."""
    parts = []
    for m in re.finditer(r"[A-Za-z]+|\d+|.", token):
        piece = m.group()
        if piece.isdigit():
            parts.append(r"\d+")
        elif piece.isalpha() and piece.isascii():
            parts.append("[A-Za-z]+")
        else:
            parts.append(re.escape(piece))
    return "".join(parts)


def ignore_pattern_for(line: str) -> str:
    """Patrón de `ignore_line_patterns` para una línea de maquetación que se
    repite con un número distinto en cada informe (las palabras, literales;
    los tokens con cifras, por su forma)."""
    pieces = [
        _token_shape(t) if _DIGIT_RE.search(t) else re.escape(t) for t in line.strip().split()
    ]
    pattern = "^" + r"\s+".join(pieces) + "$"
    check_pattern(pattern, "ignore_line_patterns")
    return pattern


# -- 4. Filas de metadatos sin etiquetas ----------------------------------------

_DATE_TOKEN_RE = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}")
METADATA_ROLES = ("report_number", "request_date", "sample_date", "validation_date")


def metadata_row_candidates(lines: list[str]) -> list[int]:
    """Líneas sin «:» con dos o más fechas y nada más que identificadores: la
    fila de valores de una cabecera de columnas (p. ej. «nº de análisis,
    fecha de toma, de recepción, de edición»)."""
    found = []
    for idx, line in enumerate(lines):
        tokens = line.split()
        dates = sum(bool(_DATE_TOKEN_RE.match(t)) for t in tokens)
        if ":" not in line and dates >= 2 and len(tokens) <= dates + 2:
            found.append(idx)
    return found


def metadata_row_pattern(line: str, roles: list[str | None]) -> str:
    """Patrón de `metadata_row_re` a partir de una fila de ejemplo y del campo
    de cada token (`None` = no se guarda). Lanza `ValueError` si no cuadra."""
    tokens = line.split()
    if len(roles) != len(tokens):
        raise ValueError(f"hacen falta {len(tokens)} campos, uno por token")
    pieces = []
    for token, role in zip(tokens, roles, strict=True):
        if role is not None and role not in METADATA_ROLES:
            raise ValueError(f"campo desconocido: {role}")
        date = _DATE_TOKEN_RE.match(token)
        if date:
            shape = r"\d{1,2}/\d{1,2}/\d{2,4}"
            tail = r"\S*" if date.end() < len(token) else ""
        else:
            shape, tail = _token_shape(token), ""
        pieces.append((f"(?P<{role}>{shape})" if role else f"(?:{shape})") + tail)
    pattern = "^" + r"\s+".join(pieces) + r"\s*$"
    compiled = check_pattern(pattern, "metadata_row_re")
    if not compiled.match(line.strip()):
        raise ValueError("el patrón generado no reconoce la línea de ejemplo")
    return pattern


# -- 5. Gramáticas de fila ---------------------------------------------------------

# Fila sin rango («Nombre valor [unidad]»): solo para probar si encaja.
GENERIC_UNRANGED_RE = r"^[^\d:]+\s[<>]?-?\d[\d.,]*(?:\s\S+)?$"
_SKIP_MARK_CHARS = set("()[]<>-+/:.,;%=&'\"")


def _single_marks(tokens: list[str]) -> list[str]:
    return [t for t in tokens if len(t) == 1 and not t.isascii() or t in ("*", "#", "!")]


def detect_trailing_flags(lines: list[str]) -> list[str]:
    """Marcas sueltas al final de una fila de resultado («... 12.0 - 15.0 *»)
    que hay que quitar antes de buscar el rango (`strip_trailing_flags`)."""
    counts: Counter[str] = Counter()
    for line in lines:
        tokens = line.split()
        if len(tokens) >= 3 and _single_marks(tokens[-1:]) and _DIGIT_RE.search(tokens[-2]):
            counts[tokens[-1]] += 1
        elif len(tokens) >= 3 and _single_marks(tokens[-1:]) and tokens[-2][-1:] in ")]":
            counts[tokens[-1]] += 1
    return sorted(counts)


def detect_mid_tokens(lines: list[str]) -> list[str]:
    """Marcas sueltas junto al valor, en medio de la fila («Hematíes 3,89 *
    x106/mm³ [...]», «... ü 9,8 seg»): `strip_mid_tokens`."""
    counts: Counter[str] = Counter()
    for line in lines:
        tokens = line.split()
        for i in range(1, len(tokens) - 1):
            tok = tokens[i]
            if tok in _SKIP_MARK_CHARS or not _single_marks([tok]):
                continue
            if _DIGIT_RE.search(tokens[i - 1]) or _DIGIT_RE.search(tokens[i + 1]):
                counts[tok] += 1
    return sorted(counts)


def detect_interfaced_prefix(lines: list[str]) -> str:
    """Prefijo de la fila partida «‡ 9,9 mg/dl (74 - 109)» (el nombre va en
    la línea siguiente), si se repite en dos o más líneas."""
    counts: Counter[str] = Counter()
    for line in lines:
        tokens = line.split()
        if (
            len(tokens) >= 2
            and len(tokens[0]) == 1
            and not tokens[0].isalnum()
            and tokens[0] not in _SKIP_MARK_CHARS | {"*"}
            and engine.NUMERIC_TOKEN_RE.fullmatch(tokens[1])
        ):
            counts[tokens[0]] += 1
    prefix, n = counts.most_common(1)[0] if counts else ("", 0)
    return prefix if n >= 2 else ""


def detect_following_range_labels(lines: list[str]) -> list[str]:
    """Etiquetas tras las que llega, en la línea siguiente, el rango de un
    resultado que no lo trae en su fila («Valores de referencia» / «>19
    años (0.61-1.12 ng/dL)»)."""
    shown = [line.strip() for line in lines if line.strip()]
    labels: list[str] = []
    for text, nxt in zip(shown, shown[1:], strict=False):
        if _DIGIT_RE.search(text) or len(text.split()) > 6:
            continue
        if engine.AGE_BAND_RE.match(nxt) or engine.LEADING_RANGE_RE.match(nxt):
            if text not in labels:
                labels.append(text)
    return labels


def detect_unranged_marker(lines: list[str]) -> str:
    """Marca suelta justo delante del valor (« ü 9,8 seg», Synlab: las
    determinaciones acreditadas) en dos o más líneas: delata la fila de
    resultado aunque no traiga rango (`unranged_result_re`)."""
    counts: Counter[str] = Counter()
    for line in lines:
        tokens = line.split()
        for i in range(1, len(tokens) - 1):
            tok = tokens[i]
            if tok in _SKIP_MARK_CHARS or tok == "*" or not _single_marks([tok]):
                continue
            if engine.NUMERIC_TOKEN_RE.fullmatch(tokens[i + 1]) and _DIGIT_RE.search(tokens[i + 1]):
                counts[tok] += 1
    marker, n = counts.most_common(1)[0] if counts else ("", 0)
    return marker if n >= 2 else ""


# Resultados cualitativos habituales (catalán y castellano) que el motor solo
# separa del nombre si la plantilla los declara (`known_text_values`).
TEXT_VALUES = (
    "No és procedent",
    "No es procedente",
    "No procedeix",
    "No detectable",
    "No detectat",
    "No detectado",
    "Indetectable",
    "Mostra insuficient",
    "Muestra insuficiente",
    "Mostra no rebuda",
    "Muestra no recibida",
    "Negatiu",
    "Negativo",
    "Positiu",
    "Positivo",
    "Normal",
)


def detect_text_values(lines: list[str]) -> list[str]:
    """Resultados de texto de `TEXT_VALUES` que aparecen al final de alguna
    línea del documento."""
    ends = [strip_accents(line.strip()).casefold() for line in lines]
    return [
        v for v in TEXT_VALUES if any(e.endswith(" " + strip_accents(v).casefold()) for e in ends)
    ]


def detect_placeholder(lines: list[str]) -> str:
    """Nombre genérico que una plantilla con puntos de relleno repite en vez
    del nombre real («RESULTAT.....»): el motor lo cambia por la sección."""
    names = Counter(
        m.group("name").strip() for line in lines if (m := engine.DOT_LEADER_RE.match(line.strip()))
    )
    repeated = [name for name, n in names.items() if n >= 2 and name.isupper()]
    return repeated[0] if repeated else ""


@dataclass
class GrammarTrial:
    """Resultado de probar una gramática del motor sobre el documento."""

    key: str
    description: str
    settings: dict[str, Any]  # claves del `.toml` que la activan
    results: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    near_misses: list[int]  # líneas que parecen resultados y no se capturan

    @property
    def n_results(self) -> int:
        return len(self.results)

    @property
    def n_clean(self) -> int:
        """Filas con pinta de resultado de verdad: nombre con letras, sin «:»
        ni puntos de relleno, y con valor."""
        return sum(
            r.get("value_raw") is not None
            and len(re.findall(r"[^\W\d_]", r.get("raw_name") or "")) >= 3
            and ":" not in r["raw_name"]
            and ".." not in r["raw_name"]
            for r in self.results
        )


def _looks_like_result(line: str) -> bool:
    tokens = line.split()
    return (
        ":" not in line
        and bool(re.match(r"[^\W\d_]", line))
        and any(_DIGIT_RE.search(t) and engine._is_value_token(t) for t in tokens[1:])
    )


def _near_misses(trace: list[dict[str, Any]]) -> list[int]:
    return [
        t["idx"]
        for t in trace
        if t["kind"] in (engine.TRACE_UNCLASSIFIED, engine.TRACE_DISCARDED)
        and _looks_like_result(t["line"])
    ]


def _draft_profile(data: dict[str, Any]) -> ParserProfile:
    full = {"id": "borrador", "name": "Borrador", "signature": {"requires_any": ["?"]}}
    full.update(data)
    return profile_from_data(full)


def run_profile(lines: list[str], data: dict[str, Any]) -> tuple[dict, list[dict]]:
    """Parsea `lines` con una plantilla en edición (datos del `.toml`);
    devuelve el resultado del motor y su traza."""
    trace: list[dict[str, Any]] = []
    profile = data if isinstance(data, ParserProfile) else _draft_profile(data)
    lines = list(lines)
    return engine._parse_lines(lines, profile, trace), trace


def base_settings(lines: list[str]) -> dict[str, Any]:
    """Ajustes que no dependen de la gramática: marcas que quitar, secciones
    por cabecera de columna y líneas de maquetación que ignorar."""
    settings: dict[str, Any] = {}
    if flags := detect_trailing_flags(lines):
        settings["strip_trailing_flags"] = flags
    if tokens := detect_mid_tokens(lines):
        settings["strip_mid_tokens"] = tokens
    if marker := detect_unranged_marker(lines):
        # Se mira antes de quitar las marcas sueltas: la marca delata la fila.
        settings["unranged_result_re"] = rf" {re.escape(marker)} -?[\d.,]+(?: \S+)?$"
        if labels := detect_following_range_labels(lines):
            settings["following_range_labels"] = labels
    if values := detect_text_values(lines):
        settings["known_text_values"] = values
    headers = column_header_lines(lines)
    anchors = [
        text
        for _, text in headers
        if any(c.reason == "antes de la cabecera de columna" for c in section_candidates(lines))
        and not engine._is_heading(text)
    ]
    if anchors:
        settings["section_after_anchor"] = anchors[0]
        settings["detect_headings"] = False
    else:
        caps = [ignore_pattern_for(text) for _, text in headers if engine._is_heading(text)]
        if caps:
            settings["ignore_line_patterns"] = caps
        has_headings = any(c.reason == "mayúsculas" for c in section_candidates(lines))
        settings["detect_headings"] = has_headings
    return settings


def try_grammars(lines: list[str], base: dict[str, Any] | None = None) -> list[GrammarTrial]:
    """Prueba cada gramática de fila del motor (sobre los ajustes `base`) y
    dice cuántas filas captura cada una. La primera de la lista (marcador
    «(n)» y rango entre paréntesis o corchetes) está siempre activa."""
    base = base_settings(lines) if base is None else base
    options: list[tuple[str, str, dict[str, Any]]] = [
        ("marcadores", "Marcador «(n)», rango entre paréntesis o corchetes", {}),
        (
            "rango_suelto",
            "Rango sin paréntesis al final de la línea",
            {"bare_range_is_result": True},
        ),
    ]
    dots: dict[str, Any] = {"dot_leader_result": True}
    if placeholder := detect_placeholder(lines):
        dots["single_result_name_placeholder"] = placeholder
    options.append(("puntos_relleno", "Nombre y valor separados por puntos de relleno", dots))
    if prefix := detect_interfaced_prefix(lines):
        options.append(
            (
                "fila_partida",
                f"Valor en una línea que empieza por «{prefix}» y nombre en la siguiente",
                {"interfaced_result_prefix": prefix},
            )
        )
    unranged: dict[str, Any] = {"unranged_result_re": GENERIC_UNRANGED_RE}
    if labels := detect_following_range_labels(lines):
        unranged["following_range_labels"] = labels
    options.append(("sin_rango", "Fila sin rango («nombre valor unidad»)", unranged))
    trials = []
    for key, description, settings in options:
        parsed, trace = run_profile(lines, {**base, **settings})
        trials.append(
            GrammarTrial(key, description, settings, parsed["results"], trace, _near_misses(trace))
        )
    return trials


def best_trial(trials: list[GrammarTrial]) -> GrammarTrial:
    """La gramática propuesta, contando solo filas limpias (`n_clean`): la
    básica (la primera) salvo que otra capture claramente más (una fila, o
    un 10 % si hay muchas), porque cada gramática extra también captura
    texto que solo se parece a un resultado. La genérica «sin rango» solo
    se propone si ninguna otra captura nada (con PDF reales capturaba notas
    y comentarios)."""
    basic, rest = trials[0], [t for t in trials[1:] if t.key != "sin_rango"]
    best = basic
    for trial in sorted(rest, key=lambda t: -t.n_clean):
        if trial.n_clean >= basic.n_clean + max(1, basic.n_clean // 10):
            best = trial
            break
    if best.n_clean == 0:
        generic = next((t for t in trials if t.key == "sin_rango"), None)
        if generic is not None and generic.n_clean:
            return generic
    return best


_SPECIMEN_WORDS = frozenset({"orina", "femta", "femtes", "heces", "liquid", "liquids", "liquido"})


def detect_section_suffixes(results: list[dict[str, Any]]) -> dict[str, str]:
    """Secciones cuyas pruebas repiten el nombre de una prueba de otra
    sección («Glucosa» en orina frente a «Glucosa sèrum»): sin una palabra
    añadida (`section_name_suffixes`) compartirían `canonical_id`. Solo
    secciones de otra muestra (orina, heces, líquidos), con la primera
    palabra de su título («orina»): con PDF reales, añadirlo a otras
    secciones (proteinograma) separaba pruebas que son la misma."""
    from analitix.alias_audit import name_signature

    sections_by_key: dict[str, list[str]] = {}
    for r in results:
        if r.get("section"):
            key = name_signature(r["raw_name"])[0]
            sections = sections_by_key.setdefault(key, [])
            if r["section"] not in sections:
                sections.append(r["section"])
    suffixes: dict[str, str] = {}
    for sections in sections_by_key.values():
        if len(sections) < 2:
            continue
        words = {s: _norm_word(re.split(r"[^\w·]+", s.strip())[0]) for s in sections}
        for section in sections:
            if words[section] in _SPECIMEN_WORDS:
                suffixes.setdefault(section, words[section])
    return suffixes


def skip_marker_candidates(trial: GrammarTrial) -> list[tuple[str, int]]:
    """Marcas cortas entre paréntesis («(AE)») que se repiten en los nombres
    capturados: pueden ser líneas secundarias (método, otra unidad) de la
    fila anterior (`bare_range_skip_if_contains`). No se aplican solas: una
    abreviatura real («(GGT)») tiene la misma forma."""
    counts = Counter(
        m for r in trial.results for m in re.findall(r"\([A-Z]{1,4}\)", r.get("raw_name") or "")
    )
    return [(m, n) for m, n in counts.most_common() if n >= 2]


# -- 6. Números ------------------------------------------------------------------

_COMMA_DECIMAL_RE = re.compile(r"[-+]?\d+,\d+|[-+]?\d{1,3}(?:\.\d{3})+,\d+")
_POINT_DECIMAL_RE = re.compile(r"[-+]?\d+\.\d+")
_AMBIGUOUS_RE = re.compile(r"[-+]?\d{1,3}\.\d{3}")


@dataclass
class NumberConvention:
    """Convención decimal del documento (`decimal_separator`)."""

    separator: str  # ",", "." o "auto" (no se puede decidir)
    comma_decimals: int
    point_decimals: int
    ambiguous: int
    note: str


def _numeric_tokens(rows: list[dict[str, Any]]) -> list[str]:
    tokens = []
    for row in rows:
        for text in (row.get("value_raw"), row.get("ref_text")):
            tokens += [t.lstrip("<>=≤≥") for t in engine.NUMERIC_TOKEN_RE.findall(text or "")]
    return tokens


def number_convention(rows: list[dict[str, Any]]) -> NumberConvention:
    """Decide la convención con todos los valores y rangos del documento: con
    coma decimal y ningún punto decimal claro es «,»; al revés, «.». Un
    «7.349» no cuenta para ninguna (es justo lo ambiguo)."""
    comma = point = ambiguous = 0
    for token in _numeric_tokens(rows):
        if _COMMA_DECIMAL_RE.fullmatch(token):
            comma += 1
        elif _AMBIGUOUS_RE.fullmatch(token):
            ambiguous += 1
        elif _POINT_DECIMAL_RE.fullmatch(token):
            point += 1
    if comma and not point:
        return NumberConvention(
            ",", comma, point, ambiguous, "coma decimal; el punto es de millares"
        )
    if point and not comma:
        return NumberConvention(".", comma, point, ambiguous, "punto decimal; nunca de millares")
    note = "mezcla coma y punto decimal" if comma else "no hay decimales con los que decidir"
    return NumberConvention("auto", comma, point, ambiguous, note)


@dataclass
class AmbiguousValue:
    raw_name: str
    value_raw: str
    as_thousands: float
    as_decimal: float
    proposed: float | None
    reason: str
    doubtful: bool  # hay que confirmarlo a mano


def ambiguous_values(rows: list[dict[str, Any]], separator: str) -> list[AmbiguousValue]:
    """Valores «1.000»/«7.349» y la lectura propuesta con su motivo."""
    found = []
    for row in rows:
        value = (row.get("value_raw") or "").strip()
        if not _AMBIGUOUS_RE.fullmatch(value):
            continue
        with engine.decimal_convention(separator):
            proposed = engine._value_to_float(value, row.get("ref_low"), row.get("ref_high"))
        has_range = row.get("ref_low") is not None or row.get("ref_high") is not None
        if separator == ",":
            reason, doubtful = "el documento usa coma decimal: el punto es de millares", False
        elif separator == ".":
            reason, doubtful = "el documento usa punto decimal", False
        elif has_range:
            reason, doubtful = "la lectura más próxima a su rango de referencia", False
        else:
            reason, doubtful = "sin rango ni convención del documento: se lee como millares", True
        found.append(
            AmbiguousValue(
                row.get("raw_name", ""),
                value,
                float(value.replace(".", "")),
                float(value),
                proposed,
                reason,
                doubtful,
            )
        )
    return found


# -- 7. Unidades -----------------------------------------------------------------


@dataclass
class UnitInfo:
    unit: str
    dimension: str | None
    status: str  # «conocida», «desconocida» o «sospechosa»
    tests: list[str] = field(default_factory=list)
    reason: str = ""


def _unit_suspicion(unit: str) -> str:
    tokens = unit.split()
    if engine.NUMERIC_TOKEN_RE.fullmatch(tokens[-1]) and _DIGIT_RE.search(tokens[-1]):
        return "termina en un número: puede ser un límite del rango pegado"
    if re.search(r"\d\s*-\s*\d", unit) or unit[0] in "<>([":
        return "parece parte del rango de referencia"
    if len(tokens[0]) == 1 and not tokens[0].isalnum() and tokens[0] != "%":
        return "empieza por una marca suelta: quítala con strip_mid_tokens"
    return ""


def classify_units(rows: list[dict[str, Any]]) -> list[UnitInfo]:
    """Cada unidad del documento, con su dimensión si `alias_audit` la
    reconoce, y las que parecen restos de la fila mal partida."""
    units: dict[str, UnitInfo] = {}
    for row in rows:
        unit = (row.get("unit") or "").strip()
        if not unit:
            continue
        if unit not in units:
            dimension = unit_dimension(unit)
            reason = _unit_suspicion(unit)
            status = "sospechosa" if reason else "conocida" if dimension else "desconocida"
            units[unit] = UnitInfo(unit, dimension[0] if dimension else None, status, [], reason)
        units[unit].tests.append(row.get("raw_name", ""))
    return list(units.values())


# -- 8. Parámetros y duplicados ---------------------------------------------------


@dataclass
class MatchCandidate:
    canonical_id: str
    raw_names: list[str]
    relation: str  # relación de unidades (`alias_audit.unit_relation`)
    reasons: list[str]


@dataclass
class ParameterMatch:
    raw_name: str
    unit: str | None
    canonical_id: str
    status: str  # «base de datos», «catálogo» o «nuevo»
    candidates: list[MatchCandidate] = field(default_factory=list)


_THIS_PDF = "este PDF"


def parameter_matches(
    rows: list[dict[str, Any]], known_rows: list[dict[str, Any]] = ()
) -> list[ParameterMatch]:
    """¿Existe ya cada parámetro? `known_rows`: resultados ya guardados
    (`repository.get_all_results`: `raw_name`, `unit`, `source_file`). Para
    los nuevos, propone «puede ser el mismo que…» con las señales de
    `alias_audit` (nombre, abreviatura, LOINC) y unidades compatibles,
    **nunca** con uno que aparece en el mismo informe."""
    groups: dict[str, TestGroup] = {}
    for row in known_rows:
        add_result(
            groups, row["raw_name"], row.get("unit"), "bd", None, row.get("source_file") or ""
        )
    known_ids = set(groups)
    for row in rows:
        add_result(
            groups, row["raw_name"], row.get("unit"), "pdf", row.get("loinc_code"), _THIS_PDF
        )
    catalog_ids = known_canonical_ids() | panel_ids()
    proposals = find_proposals(groups)
    matches = []
    for row in rows:
        cid = canonical_id_for(row["raw_name"])
        if cid in known_ids:
            status = "base de datos"
        elif cid in catalog_ids:
            status = "catálogo"
        else:
            status = "nuevo"
        match = ParameterMatch(row["raw_name"], row.get("unit"), cid, status)
        if status == "nuevo":
            for proposal in proposals:
                if cid not in proposal.ids:
                    continue
                for other in proposal.ids:
                    if other == cid or groups[cid].reports & groups[other].reports:
                        continue
                    relation = unit_relation(groups[cid].units, groups[other].units)
                    if relation == "incompatible":
                        continue
                    match.candidates.append(
                        MatchCandidate(
                            other, sorted(groups[other].raw_names), relation, proposal.reasons
                        )
                    )
        matches.append(match)
    return matches


def aliases_for(accepted: dict[str, str]) -> dict[str, str]:
    """`{nombre crudo: canonical_id destino}` aceptados por el usuario ->
    entradas para `catalog.add_aliases` (capa del usuario)."""
    return {normalize_test_name(raw): target for raw, target in accepted.items()}


# -- 9. Evaluación y comparaciones -------------------------------------------------


@dataclass
class Evaluation:
    """Cómo lee una plantilla un documento. Sin valores de la cabecera: solo
    qué campos lee."""

    profile_id: str
    results: list[dict[str, Any]]
    header_read: dict[str, bool]
    missing_required: list[str]
    near_misses: list[int]
    review_reasons: list[str]
    signature_matches: bool
    other_matching: list[str]  # otras plantillas instaladas cuya firma aparece

    @property
    def coverage(self) -> float | None:
        """Parte de las filas con forma de resultado que la plantilla captura."""
        total = len(self.results) + len(self.near_misses)
        return len(self.results) / total if total else None


def evaluate(lines: list[str], profile: ParserProfile | dict[str, Any]) -> Evaluation:
    """Prueba una plantilla (instalada o en edición) sobre un documento, con
    los mismos criterios con los que `ingest` deja un informe en revisión."""
    if not isinstance(profile, ParserProfile):
        profile = profile_from_data(profile)
    parsed, trace = run_profile(lines, profile)
    header, results = parsed["header"], parsed["results"]
    read = {key: bool(header.get(key)) for key in HEADER_FIELDS if key != "sample_date"}
    read["sample_date"] = any(r.get("sample_date") for r in results)
    missing = [key for key in profile.required_fields if not read.get(key)]
    text = "\n".join(lines)
    from analitix.parser_profiles import _matches

    signature = _matches(profile, text, strip_accents(text))
    reasons = []
    if profile.manual_review_only:
        reasons.append("la plantilla no tiene motor (manual_review_only)")
    if not signature:
        reasons.append("la firma de la plantilla no aparece en el documento")
    if not read["full_name"]:
        reasons.append("no se reconoció el nombre del paciente")
    if not results:
        reasons.append("no se extrajo ningún resultado")
    if missing:
        reasons.append("faltan campos obligatorios: " + ", ".join(missing))
    others = [p.id for p in matching_profiles(lines) if p.id != profile.id]
    return Evaluation(
        profile.id, results, read, missing, _near_misses(trace), reasons, signature, others
    )


def compare_header_fields(
    lines: list[str], profiles: list[ParserProfile]
) -> dict[str, dict[str, bool]]:
    """Qué campos de cabecera lee cada plantilla en este documento."""
    return {p.id: evaluate(lines, p).header_read for p in profiles}


@dataclass
class ResultDiff:
    """Diferencias de `candidate` respecto a `reference`."""

    missing: list[dict[str, Any]]  # en la referencia y no en la candidata
    extra: list[dict[str, Any]]  # solo en la candidata
    changed: list[tuple[dict[str, Any], dict[str, Any], list[str]]]

    @property
    def same(self) -> bool:
        return not (self.missing or self.extra or self.changed)


COMPARED_FIELDS = ("value_raw", "unit", "ref_text")


def _keyed(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    seen: Counter[str] = Counter()
    keyed = {}
    for row in rows:
        name = normalize_test_name(row.get("raw_name") or "")
        keyed[(name, seen[name])] = row
        seen[name] += 1
    return keyed


def compare_results(reference: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> ResultDiff:
    """Compara dos listas de resultados (dos plantillas sobre el mismo PDF, o
    la plantilla frente a lo guardado en la base de datos,
    `repository.get_report_results`) por nombre y orden de aparición."""
    a, b = _keyed(reference), _keyed(candidate)
    changed = []
    for key in a.keys() & b.keys():
        fields = [f for f in COMPARED_FIELDS if (a[key].get(f) or "") != (b[key].get(f) or "")]
        if fields:
            changed.append((a[key], b[key], fields))
    return ResultDiff(
        [a[k] for k in a if k not in b],
        [b[k] for k in b if k not in a],
        sorted(changed, key=lambda c: c[0].get("raw_name") or ""),
    )


# -- 10. Análisis completo y propuesta de plantilla --------------------------------


@dataclass
class Analysis:
    labels: list[LabelCandidate]
    signatures: list[SignatureCandidate]
    sections: list[SectionCandidate]
    column_headers: list[tuple[int, str]]
    metadata_rows: list[int]
    base: dict[str, Any]
    trials: list[GrammarTrial]
    best: GrammarTrial
    convention: NumberConvention
    ambiguous: list[AmbiguousValue]
    units: list[UnitInfo]


def analyze(lines: list[str], other_documents: list[list[str]] = ()) -> Analysis:
    """Todas las propuestas para un documento, en el orden del asistente."""
    base = base_settings(lines)
    trials = try_grammars(lines, base)
    best = best_trial(trials)
    convention = number_convention(best.results)
    return Analysis(
        header_label_candidates(lines),
        signature_candidates(lines, other_documents),
        section_candidates(lines),
        column_header_lines(lines),
        metadata_row_candidates(lines),
        base,
        trials,
        best,
        convention,
        ambiguous_values(best.results, convention.separator),
        classify_units(best.results),
    )


@dataclass
class TemplateProposal:
    data: dict[str, Any]
    analysis: Analysis
    warnings: list[str]


def propose_template(
    lines: list[str],
    template_id: str,
    name: str,
    other_documents: list[list[str]] = (),
) -> TemplateProposal:
    """Plantilla completa con las propuestas por defecto, para que el usuario
    la revise paso a paso (todo se puede cambiar antes de guardar)."""
    if not PROFILE_ID_RE.fullmatch(template_id):
        raise ValueError("el identificador solo puede tener minúsculas sin acentos, cifras y «_»")
    analysis = analyze(lines, other_documents)
    warnings: list[str] = []
    data: dict[str, Any] = {"id": template_id, "name": name.strip(), "priority": 100}

    header_labels, sample_patterns, boundary = [], [], []
    for c in analysis.labels:
        if c.suggested_key == "sample_date":
            sample_patterns.append(label_pattern(c.label))
        elif c.suggested_key:
            header_labels.append({"key": c.suggested_key, "pattern": label_pattern(c.label)})
        elif c.label not in boundary:
            boundary.append(c.label)
    assigned = {item["key"] for item in header_labels}
    if "full_name" not in assigned:
        warnings.append("no se ha encontrado la etiqueta del nombre del paciente")

    signature = next(
        (s for s in analysis.signatures if not s.used_by and not s.in_other_documents), None
    )
    if signature:
        data["signature"] = {"requires_any": [signature.text]}
    elif assigned:
        keys = [k for k in ("dni", "full_name", "birth_date") if k in assigned]
        data["signature"] = {"header_label_any": keys or sorted(assigned)}
        warnings.append(
            "no hay un texto propio del laboratorio para la firma: se usan etiquetas de "
            "cabecera, que pueden coincidir con otros laboratorios"
        )
    else:
        warnings.append("falta la firma: añade un texto propio del laboratorio")

    data.update(analysis.base)
    data.update(analysis.best.settings)
    if suffixes := detect_section_suffixes(analysis.best.results):
        data["section_name_suffixes"] = suffixes
    if analysis.best.n_results == 0:
        warnings.append(
            "ninguna gramática del motor captura resultados: este formato necesita un motor nuevo"
        )
    if analysis.convention.separator != "auto":
        data["decimal_separator"] = analysis.convention.separator
    if any(a.doubtful for a in analysis.ambiguous):
        warnings.append("hay valores con punto que pueden ser millares o decimales: confírmalos")
    if analysis.metadata_rows:
        warnings.append("hay una fila de fechas sin etiquetas: asigna sus campos (metadata_row_re)")
    if boundary:
        data["boundary_terms"] = boundary
    if header_labels:
        data["header_labels"] = header_labels
    if sample_patterns:
        data["sample_date_label"] = {"key": "sample_date", "pattern": "|".join(sample_patterns)}
    if "signature" in data:
        validate_user_profile_data(data, template_id)
    return TemplateProposal(data, analysis, warnings)


# -- 11. Escritura, validación y guardado del `.toml` ---------------------------------

TOP_LEVEL_ORDER = (
    "id",
    "name",
    "short_name",
    "priority",
    "manual_review_only",
    "decimal_separator",
    "required_fields",
    "extract_x_tolerance",
    "detect_headings",
    "bare_range_is_result",
    "bare_range_skip_if_contains",
    "dot_leader_result",
    "single_result_name_placeholder",
    "interfaced_result_prefix",
    "section_after_anchor",
    "unranged_result_re",
    "following_range_labels",
    "strip_trailing_flags",
    "strip_mid_tokens",
    "full_name_re",
    "metadata_row_re",
    "boundary_terms",
    "known_sections",
    "known_text_values",
    "ignore_line_patterns",
)
TABLES = ("signature", "sample_date_label", "section_name_suffixes")
ARRAY_TABLES = ("header_labels", "line_substitutions")
# Caracteres de control (NUL, salto de página...) y guion blando: restos de
# la extracción que nunca deben acabar en la plantilla.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f\xad]")


def _toml_string(text: str) -> str:
    text = _CONTROL_RE.sub("", text)
    if "'" not in text:
        return f"'{text}'"  # literal: los patrones no necesitan escapar «\»
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, list):
        items = [_toml_value(v) for v in value]
        if sum(len(i) + 2 for i in items) <= 76:
            return "[" + ", ".join(items) + "]"
        return "[\n" + "".join(f"    {i},\n" for i in items) + "]"
    raise ProfileValidationError(f"valor no admitido en una plantilla: {type(value).__name__}")


def _toml_table(table: dict[str, Any]) -> list[str]:
    return [
        f"{_toml_string(k) if not re.fullmatch(r'[A-Za-z0-9_-]+', k) else k} = {_toml_value(v)}"
        for k, v in table.items()
    ]


def render_toml(data: dict[str, Any]) -> str:
    """Texto `.toml` de una plantilla (solo el esquema conocido)."""
    unknown = set(data) - KNOWN_PROFILE_KEYS
    if unknown:
        raise ProfileValidationError(f"claves desconocidas: {', '.join(sorted(unknown))}")
    out = [
        "# Plantilla de laboratorio creada con el asistente de Analitix.",
        "# Solo lleva etiquetas y patrones de la plantilla: ningún dato de paciente.",
        "",
    ]
    out += [f"{k} = {_toml_value(data[k])}" for k in TOP_LEVEL_ORDER if k in data]
    for key in TABLES:
        if data.get(key):
            out += ["", f"[{key}]", *_toml_table(data[key])]
    for key in ARRAY_TABLES:
        for item in data.get(key, []):
            out += ["", f"[[{key}]]", *_toml_table(item)]
    return "\n".join(out) + "\n"


class TemplatePrivacyError(ProfileValidationError):
    """La plantilla lleva un dato del informe (nunca se dice cuál en el
    mensaje: el mensaje puede acabar en pantalla o en el log)."""


_DNI_ANY_RE = re.compile(r"\b([XYZ]?)(\d{7,8})([A-Z])\b")
_LITERAL_DATE_RE = re.compile(r"(?<![\\\w{])\d{1,2}/\d{1,2}/\d{2,4}\b")
_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"


def _dni_valid(prefix: str, number: str, letter: str) -> bool:
    if prefix:
        if len(number) != 7:
            return False
        number = str("XYZ".index(prefix)) + number
    elif len(number) != 8:
        return False
    return int(number) != 0 and _DNI_LETTERS[int(number) % 23] == letter


def check_privacy(text: str, private_values: set[str] | list[str] = ()) -> None:
    """Lanza `TemplatePrivacyError` si el `.toml` lleva un valor de la
    cabecera del informe, un DNI/NIE válido o una fecha concreta."""
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    folded = strip_accents(body).casefold()
    vocabulary = _label_words()
    for value in private_values:
        # «Apellidos, Nombre»: también cada parte, salvo las que solo son
        # palabras de etiqueta (un nombre inventado «NOMBRE» frente a la
        # etiqueta «Nombre:»).
        parts = [value] + [
            p
            for p in value.split(",")[1:] + value.split(",")[:1]
            if "," in value and not all(_norm_word(w) in vocabulary for w in p.split())
        ]
        for part in parts:
            needle = strip_accents(part).casefold().strip()
            if len(needle) >= 4 and needle in folded:
                raise TemplatePrivacyError(
                    "la plantilla contiene un dato de la cabecera del informe; quítalo"
                )
    if any(_dni_valid(*m.groups()) for m in _DNI_ANY_RE.finditer(body.upper())):
        raise TemplatePrivacyError("la plantilla contiene un DNI o NIE")
    if _LITERAL_DATE_RE.search(body):
        raise TemplatePrivacyError("la plantilla contiene una fecha concreta")


def private_values(lines: list[str], data: dict[str, Any] | None = None) -> set[str]:
    """Datos del paciente y del informe que hay en el documento (en memoria):
    los valores de sus etiquetas y lo que lee la plantilla `data`. Es la
    lista que `check_privacy` busca dentro del `.toml`."""
    values = label_values(lines)
    # También lo que leen las plantillas instaladas que reconocen el
    # documento (p. ej. un nombre sin etiqueta, `full_name_re`).
    profiles: list[Any] = list(matching_profiles(lines))
    if data is not None:
        profiles.append(data)
    for profile in profiles:
        header = run_profile(lines, profile)[0]["header"]
        values |= {str(header[k]) for k in PRIVATE_FIELDS if header.get(k)}
    return values


def check_template_text(text: str, private_values: set[str] | list[str] = ()) -> dict[str, Any]:
    """Vuelve a leer el `.toml` con `tomllib`, lo valida como plantilla del
    usuario (claves, id, patrones) y comprueba la privacidad. Devuelve los
    datos leídos."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileValidationError(f"el texto no es un TOML válido ({exc})") from exc
    validate_user_profile_data(data)
    check_privacy(text, private_values)
    return data


@dataclass
class SavedTemplate:
    path: Path
    backup: Path | None
    # Mismo id que una plantilla de la aplicación: hasta que el usuario lo
    # decida (`config.json`, `plantillas_sustituidas`) se usa la de la app.
    same_id_as_app: bool


def app_template_ids() -> set[str]:
    return {p.stem for p in config.PARSER_PROFILES_DIR.glob("*.toml")}


def save_user_template(
    text: str, private_values: set[str] | list[str] = (), overwrite: bool = False
) -> SavedTemplate:
    """Guarda la plantilla en la carpeta de plantillas del usuario (nunca en
    la de la aplicación), tras validarla. Si ya existe, solo con
    `overwrite` y guardando antes una copia en `copias/` (subcarpeta que no
    se carga como plantilla)."""
    data = check_template_text(text, private_values)
    folder = config.USER_PARSER_PROFILES_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{data['id']}.toml"
    if path.resolve().parent != folder.resolve():
        raise ProfileValidationError("ruta de la plantilla fuera de su carpeta")
    backup = None
    if path.exists():
        if not overwrite:
            raise FileExistsError(f"ya hay una plantilla «{data['id']}»")
        copies = folder / "copias"
        copies.mkdir(exist_ok=True)
        backup = copies / f"{data['id']}-{datetime.now():%Y%m%d-%H%M%S}.toml"
        shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8", newline="\n")
    reload_profiles()
    return SavedTemplate(path, backup, data["id"] in app_template_ids())
