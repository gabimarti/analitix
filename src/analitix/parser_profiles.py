# ---------------------------------------------------------------------------
# Script: parser_profiles.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-17
# Última actualización: 2026-09-28
# ---------------------------------------------------------------------------
"""Perfiles de reconocimiento de plantillas de informe.

Cada perfil describe, en un fichero `.toml` externo (uno por centro/
laboratorio en `PARSER_PROFILES_DIR`), las etiquetas de cabecera, secciones y
demás datos que hoy varían entre plantillas — en vez de estar embebidos como
constantes en `pdf_parser.py`. Esto permite incorporar un centro nuevo cuya
gramática de línea sea compatible con la ya soportada (marcador `"(n)"` o
rango entre paréntesis, ver `pdf_parser.py`) sin tocar código: basta añadir un
`.toml` nuevo.

Un centro con una gramática de resultado genuinamente distinta (fuera de
rango marcado de otra forma, filas de resultado con otra estructura...) sigue
necesitando motor de parseo nuevo en `pdf_parser.py` el día que se implemente
de verdad — este módulo solo cubre la detección de qué perfil aplica a cada
PDF y los datos de reconocimiento, no un lenguaje universal de gramáticas.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from analitix.config import PARSER_PROFILES_DIR
from analitix.textutils import strip_accents

# Las etiquetas de cabecera están en catalán seguidas, opcionalmente, de
# "/ <traducción>" cuya redacción exacta ha variado a lo largo de los años;
# se admite cualquier traducción con este sufijo genérico en vez de
# enumerarlas todas en cada término de `boundary_terms`.
_TRANSLATION_SUFFIX = r"(?:\s*/\s*[A-Za-zÀ-ÿ.º ]+)?"


@dataclass
class ParserProfile:
    id: str
    name: str
    manual_review_only: bool = False
    # Nombre corto para leyendas y listados ("H. Mataró", "HUGTIP"); si el
    # perfil no lo define, se usa `name`.
    short_name: str = ""
    priority: int = 100
    signature_requires_any: list[str] = field(default_factory=list)
    signature_header_label_any: list[str] = field(default_factory=list)
    header_labels: list[tuple[str, str]] = field(default_factory=list)
    sample_date_label: Optional[tuple[str, str]] = None
    boundary_re: Optional[re.Pattern] = None
    known_sections: set[str] = field(default_factory=set)
    known_text_values: list[str] = field(default_factory=list)
    # Habilita, para perfiles cuya gramática de resultado no lleva marcador
    # "(n)" ni rango entre paréntesis (p. ej. HUGTIP), tratar como fila de
    # resultado cualquier línea que termine en un rango sin paréntesis
    # (`pdf_parser.RANGE_RE`) aunque no tenga marcador. Desactivado por
    # defecto: activarlo sin que la plantilla lo garantice arriesga capturar
    # texto narrativo que termine pareciendo un rango por casualidad.
    bare_range_is_result: bool = False
    # Con `bare_range_is_result` activo, ignora igualmente la línea si
    # contiene alguna de estas cadenas (p. ej. `"(AE)"` en HUGTIP: marca de
    # acreditación ENAC en una línea de método/unidad secundaria que
    # también termina en un rango, para no capturarla como una
    # determinación distinta de la que la precede).
    bare_range_skip_if_contains: list[str] = field(default_factory=list)
    # Caracteres/cadenas que se recortan del final de cada línea antes de
    # clasificarla (p. ej. `"*"` en HUGTIP, marca de fuera de rango sin
    # indicar dirección alto/bajo — `compute_flag` ya la recalcula del rango
    # numérico de todos modos).
    strip_trailing_flags: list[str] = field(default_factory=list)
    # Igual que `strip_trailing_flags` pero para un token suelto EN MEDIO de
    # la línea, no al final (p. ej. Synlab: un glifo "ü" delante del valor
    # en las determinaciones acreditadas ENAC, o un "*" de fuera de rango
    # entre el valor y la unidad — "Hematíes 3,89 * x106/mm³ [...]"). Se
    # quita con los espacios que lo rodean, colapsados a uno solo.
    strip_mid_tokens: list[str] = field(default_factory=list)
    # `_is_heading` (línea íntegramente en mayúsculas y sin ":") asume
    # encabezados de sección tipo Maresme; en perfiles donde los títulos van
    # en minúscula/mixta (p. ej. HUGTIP) esa misma regla solo capta ruido de
    # extracción en mayúsculas ("SDF", "DDD"...), así que se puede desactivar.
    detect_headings: bool = True
    # Prefijo que marca una fila de resultado "interfaced" partida en dos
    # líneas: valor/unidad/rango en una línea que empieza por este prefijo,
    # nombre de la prueba en la línea siguiente (p. ej. Quirón: "‡ 9,9 mg/dl
    # (74 - 109)" seguida de "Glucosa plasma"). Vacío (por defecto) desactiva
    # esta gramática.
    interfaced_result_prefix: str = ""
    # Línea de cabecera de columna ("Prueba Resultado Unidades Valores de
    # Normalidad" en Quirón) que marca el inicio de una sección tabular; la
    # línea INMEDIATAMENTE ANTERIOR a esta se toma como título de sección, en
    # vez de detectarla por mayúsculas (`detect_headings`). Vacío (por
    # defecto) desactiva esta gramática.
    section_after_anchor: str = ""
    # `x_tolerance` de `pdfplumber.extract_text` para este perfil (ver
    # `pdf_parser.extract_lines`); `None` (por defecto) usa el valor por
    # defecto de `pdfplumber`. Solo hace falta bajarlo en plantillas cuya
    # fuente funde palabras contiguas sin espacio (p. ej. Echevarne).
    extract_x_tolerance: Optional[float] = None
    # Patrones (regex, comprobados con `re.search` sobre la línea ya
    # extraída) que descartan la línea sin más procesado — ruido de
    # maquetación que se repite en cada página y que, sin excluirlo, se
    # confundiría con contenido real (p. ej. Echevarne: la cabecera de
    # columna de la tabla de resultados, con el número de análisis
    # inyectado en medio, sale en mayúsculas y se leería como un título de
    # sección nuevo).
    ignore_line_patterns: list[re.Pattern] = field(default_factory=list)
    # Habilita, para perfiles cuya fila de resultado separa nombre de valor
    # con puntos de relleno hasta una columna fija en vez de marcador "(n)"
    # o rango pegado al final de línea (p. ej. Echevarne:
    # "SEROALBÚMINA..................... 39,0 g/L (36,0-54,0)"), esta
    # gramática — ver `pdf_parser.DOT_LEADER_RE`.
    dot_leader_result: bool = False
    # Con `dot_leader_result` activo: cuando el nombre extraído es
    # literalmente este texto (p. ej. "RESULTAT" en Echevarne, la plantilla
    # repite la palabra genérica de la columna en vez del nombre real
    # cuando una sección solo tiene una determinación), se sustituye por el
    # título de la sección actual. Vacío (por defecto) desactiva la
    # sustitución.
    single_result_name_placeholder: str = ""
    # Regex con un grupo nombrado `name` para capturar el nombre completo
    # del paciente cuando no va detrás de una etiqueta con ":" (p. ej.
    # Echevarne: "Sra. Apellido Uno Apellido Dos, Nombre..." tras un
    # tratamiento sin ninguna etiqueta "Nombre:"). `None` (por defecto)
    # desactiva esta extracción, usando solo `header_labels`.
    full_name_re: Optional[re.Pattern] = None
    # Regex con grupos nombrados opcionales `report_number`/`sample_date`/
    # `request_date`/`validation_date` para una fila de metadatos en la que
    # las etiquetas y los valores van en líneas separadas, no "Etiqueta:
    # valor" en la misma línea (p. ej. Echevarne: cabecera de columna "Nº
    # Anàlisi / Data presa de mostra / Data recepció / Data edició" seguida,
    # en la línea siguiente, de los valores en ese mismo orden — se
    # reconoce la fila de valores directamente por su forma, sin necesitar
    # la fila de etiquetas). `None` (por defecto) desactiva esta gramática.
    metadata_row_re: Optional[re.Pattern] = None
    # Sustituciones (regex, reemplazo) aplicadas a cada línea antes de
    # clasificarla, para reparar artefactos de extracción propios de una
    # plantilla (p. ej. Maresme antiguo: el nombre se solapa con la columna
    # del valor y sale pegado a él, "sèrum23 U/L").
    line_substitutions: list[tuple[re.Pattern, str]] = field(default_factory=list)
    # Regex (`re.search` sobre la línea ANTES de quitar `strip_mid_tokens`)
    # que reconoce una fila de resultado aunque no lleve rango de
    # referencia (p. ej. Synlab: la marca " ü " delante del valor; HUGTIP:
    # "Srm-...; c. subst. <valor> <unidad>"). Sin esto la fila se descarta.
    # `None` (por defecto) desactiva esta gramática.
    unranged_result_re: Optional[re.Pattern] = None
    # Etiquetas tras las que, en las líneas siguientes, viene el rango de un
    # resultado que no lo trae en su propia fila: un rango suelto al inicio
    # de línea ("Valors recomanats:" / "<200 ( 5.2 mmol/L )", HUGTIP) o
    # franjas por edad ("Valores de referencia" / ">19 años (0.61-1.12
    # ng/dL)", Synlab), de las que se elige la de la edad del paciente.
    following_range_labels: list[str] = field(default_factory=list)
    # Sección -> palabra que se añade al nombre de sus pruebas, para que el
    # mismo nombre en muestras distintas no comparta `canonical_id` (p. ej.
    # Maresme: "Glucosa", "pH" o "Hematies" en la sección de orina frente a
    # los mismos nombres en sangre). No se añade si el nombre ya la lleva.
    section_name_suffixes: dict[str, str] = field(default_factory=dict)


# Perfil interno (no viene de un fichero .toml) para un PDF que no coincide
# con ningún perfil conocido: nunca se ha visto ese laboratorio/centro, así
# que no hay ninguna tabla de etiquetas fiable que aplicarle. Se marca
# directamente para revisión manual en vez de forzar sobre él la gramática de
# otro centro.
UNKNOWN_PROFILE = ParserProfile(
    id="unknown",
    name="Formato no reconocido",
    manual_review_only=True,
    priority=1_000_000,
)


def _build_boundary_re(terms: list[str]) -> Optional[re.Pattern]:
    if not terms:
        return None
    pattern = (
        r"(?:" + "|".join(re.escape(strip_accents(t)) for t in terms) + r")"
        + _TRANSLATION_SUFFIX + r"\s*:"
    )
    return re.compile(pattern, re.IGNORECASE)


def _load_profile(path: Path) -> ParserProfile:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    header_labels = [(item["key"], item["pattern"]) for item in data.get("header_labels", [])]
    sample_date = data.get("sample_date_label")
    sample_date_label = (sample_date["key"], sample_date["pattern"]) if sample_date else None
    signature = data.get("signature", {})
    return ParserProfile(
        id=data["id"],
        name=data["name"],
        short_name=data.get("short_name") or data["name"],
        manual_review_only=data.get("manual_review_only", False),
        priority=data.get("priority", 100),
        signature_requires_any=signature.get("requires_any", []),
        signature_header_label_any=signature.get("header_label_any", []),
        header_labels=header_labels,
        sample_date_label=sample_date_label,
        boundary_re=_build_boundary_re(data.get("boundary_terms", [])),
        known_sections=set(data.get("known_sections", [])),
        known_text_values=data.get("known_text_values", []),
        bare_range_is_result=data.get("bare_range_is_result", False),
        bare_range_skip_if_contains=data.get("bare_range_skip_if_contains", []),
        strip_trailing_flags=data.get("strip_trailing_flags", []),
        strip_mid_tokens=data.get("strip_mid_tokens", []),
        detect_headings=data.get("detect_headings", True),
        interfaced_result_prefix=data.get("interfaced_result_prefix", ""),
        section_after_anchor=data.get("section_after_anchor", ""),
        extract_x_tolerance=data.get("extract_x_tolerance"),
        ignore_line_patterns=[re.compile(p) for p in data.get("ignore_line_patterns", [])],
        dot_leader_result=data.get("dot_leader_result", False),
        single_result_name_placeholder=data.get("single_result_name_placeholder", ""),
        full_name_re=re.compile(data["full_name_re"]) if data.get("full_name_re") else None,
        metadata_row_re=re.compile(data["metadata_row_re"]) if data.get("metadata_row_re") else None,
        line_substitutions=[
            (re.compile(item["pattern"]), item["replacement"]) for item in data.get("line_substitutions", [])
        ],
        unranged_result_re=re.compile(data["unranged_result_re"]) if data.get("unranged_result_re") else None,
        following_range_labels=data.get("following_range_labels", []),
        section_name_suffixes=data.get("section_name_suffixes", {}),
    )


@lru_cache(maxsize=1)
def load_profiles() -> tuple[ParserProfile, ...]:
    """Carga todos los perfiles `.toml` de `PARSER_PROFILES_DIR`.

    Se devuelven ordenados por `priority` ascendente (los más específicos,
    con una señal propia del centro, antes que los genéricos) para que
    `detect_profile` los evalúe en ese orden.
    """
    profiles = [_load_profile(p) for p in sorted(PARSER_PROFILES_DIR.glob("*.toml"))]
    return tuple(sorted(profiles, key=lambda p: p.priority))


def detect_profile(lines: list[str]) -> ParserProfile:
    """Elige el perfil cuyo patrón de reconocimiento aparece en el documento.

    Se prueban los perfiles por `priority` ascendente y se usa el primero que
    coincida: una señal específica del centro (`signature.requires_any`, p.
    ej. su nombre) tiene preferencia sobre una señal genérica
    (`signature.header_label_any`, cualquier etiqueta de cabecera propia del
    perfil). Si ninguno coincide, se devuelve `UNKNOWN_PROFILE`.
    """
    text = "\n".join(lines)
    deaccented = strip_accents(text)
    for profile in load_profiles():
        if any(term in text or term in deaccented for term in profile.signature_requires_any):
            return profile
        if profile.signature_header_label_any:
            header_labels_by_key = dict(profile.header_labels)
            for key in profile.signature_header_label_any:
                pattern = header_labels_by_key.get(key)
                if pattern and re.search(pattern, deaccented, re.IGNORECASE):
                    return profile
    return UNKNOWN_PROFILE
