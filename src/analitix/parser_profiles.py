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

import json
import logging
import re
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from analitix import config
from analitix.config import PARSER_PROFILES_DIR
from analitix.textutils import strip_accents

logger = logging.getLogger(__name__)

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
    sample_date_label: tuple[str, str] | None = None
    boundary_re: re.Pattern | None = None
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
    extract_x_tolerance: float | None = None
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
    full_name_re: re.Pattern | None = None
    # Regex con grupos nombrados opcionales `report_number`/`sample_date`/
    # `request_date`/`validation_date` para una fila de metadatos en la que
    # las etiquetas y los valores van en líneas separadas, no "Etiqueta:
    # valor" en la misma línea (p. ej. Echevarne: cabecera de columna "Nº
    # Anàlisi / Data presa de mostra / Data recepció / Data edició" seguida,
    # en la línea siguiente, de los valores en ese mismo orden — se
    # reconoce la fila de valores directamente por su forma, sin necesitar
    # la fila de etiquetas). `None` (por defecto) desactiva esta gramática.
    metadata_row_re: re.Pattern | None = None
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
    unranged_result_re: re.Pattern | None = None
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
    # De dónde viene: "app" (`PARSER_PROFILES_DIR`, revisado con el código)
    # o "usuario" (`config.USER_PARSER_PROFILES_DIR`, validado al cargar).
    origin: str = "app"
    path: Path | None = None


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


def _build_boundary_re(terms: list[str]) -> re.Pattern | None:
    if not terms:
        return None
    pattern = (
        r"(?:"
        + "|".join(re.escape(strip_accents(t)) for t in terms)
        + r")"
        + _TRANSLATION_SUFFIX
        + r"\s*:"
    )
    return re.compile(pattern, re.IGNORECASE)


def _load_profile(path: Path, origin: str = "app") -> ParserProfile:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    if origin != "app":
        validate_user_profile_data(data, path.stem)
    profile = _profile_from_data(data)
    profile.origin = origin
    profile.path = path
    return profile


def _profile_from_data(data: dict) -> ParserProfile:
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
        metadata_row_re=re.compile(data["metadata_row_re"])
        if data.get("metadata_row_re")
        else None,
        line_substitutions=[
            (re.compile(item["pattern"]), item["replacement"])
            for item in data.get("line_substitutions", [])
        ],
        unranged_result_re=re.compile(data["unranged_result_re"])
        if data.get("unranged_result_re")
        else None,
        following_range_labels=data.get("following_range_labels", []),
        section_name_suffixes=data.get("section_name_suffixes", {}),
    )


# -- Plantillas del usuario: validación estricta ---------------------------
# Las plantillas de la aplicación se revisan con el código; las del usuario
# (o las que alguien comparta) no, así que antes de usarlas se comprueba que
# solo traen claves conocidas, un id seguro como nombre de fichero y
# expresiones regulares acotadas. `re` no tiene tiempo máximo: un patrón con
# cuantificadores anidados ("(a+)+") puede tardar un tiempo exponencial en
# una línea concreta y colgar la importación (ReDoS). Se rechazan esos
# patrones al cargar; el resto del riesgo lo cubre el tiempo máximo del
# proceso aparte en el que se parsean los PDF.

KNOWN_PROFILE_KEYS = frozenset(
    {
        "id",
        "name",
        "short_name",
        "manual_review_only",
        "priority",
        "signature",
        "header_labels",
        "sample_date_label",
        "boundary_terms",
        "known_sections",
        "known_text_values",
        "bare_range_is_result",
        "bare_range_skip_if_contains",
        "strip_trailing_flags",
        "strip_mid_tokens",
        "detect_headings",
        "interfaced_result_prefix",
        "section_after_anchor",
        "extract_x_tolerance",
        "ignore_line_patterns",
        "dot_leader_result",
        "single_result_name_placeholder",
        "full_name_re",
        "metadata_row_re",
        "line_substitutions",
        "unranged_result_re",
        "following_range_labels",
        "section_name_suffixes",
    }
)
PROFILE_ID_RE = re.compile(r"[a-z0-9_]{1,64}")
MAX_PATTERN_LENGTH = 300
MAX_REPLACEMENT_LENGTH = 200
# Referencias a grupos dentro del texto de reemplazo de `re.sub`.
_GROUP_REF_RE = re.compile(r"\\g<([^>]*)>|\\(\d{1,2})")


class ProfileValidationError(ValueError):
    """Plantilla del usuario no válida (el mensaje dice por qué)."""


def _repeat_bounds(op, av) -> tuple[int, int] | None:
    """(mínimo, máximo) de repeticiones de un nodo de `re._parser`, o None
    si no es una repetición."""
    from re import _constants as c

    if op in (c.MAX_REPEAT, c.MIN_REPEAT, getattr(c, "POSSESSIVE_REPEAT", None)):
        return av[0], av[1]
    return None


def _has_nested_repeat(items, inside_repeat: bool = False) -> bool:
    """¿Hay una repetición de longitud variable («+», «*», «{1,3}») dentro
    de otra que se repite más de una vez? Una interior de longitud fija
    («(\\.\\d{3})*») no es peligrosa: cada vuelta consume lo mismo. No
    detecta alternativas solapadas («(?:a|aa)+»); para eso está el tiempo
    máximo del proceso aparte."""
    from re import _constants as c

    for op, av in items:
        bounds = _repeat_bounds(op, av)
        if bounds is not None:
            minimum, maximum = bounds
            if inside_repeat and minimum != maximum:
                return True
            if _has_nested_repeat(av[2], inside_repeat or maximum > 1):
                return True
        elif op == c.SUBPATTERN:
            if _has_nested_repeat(av[-1], inside_repeat):
                return True
        elif op == c.BRANCH:
            if any(_has_nested_repeat(branch, inside_repeat) for branch in av[1]):
                return True
        elif op in (c.ASSERT, c.ASSERT_NOT):
            if _has_nested_repeat(av[1], inside_repeat):
                return True
        elif op == getattr(c, "ATOMIC_GROUP", None):
            if _has_nested_repeat(av, inside_repeat):
                return True
    return False


def check_pattern(pattern: object, where: str) -> re.Pattern:
    """Compila un patrón de una plantilla del usuario o lanza
    `ProfileValidationError`: tiene que ser texto, de longitud acotada,
    válido y sin un cuantificador sin límite dentro de otro («(a+)+»,
    «(\\s*x)*»), la forma típica de los patrones de coste exponencial.
    Un «?» (como mucho una vez) que contenga un «+» sí se admite: es lo
    que usan las plantillas de la aplicación para las traducciones."""
    if not isinstance(pattern, str):
        raise ProfileValidationError(f"{where}: el patrón tiene que ser texto")
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise ProfileValidationError(
            f"{where}: patrón demasiado largo ({len(pattern)} caracteres, "
            f"máximo {MAX_PATTERN_LENGTH})"
        )
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise ProfileValidationError(f"{where}: patrón no válido ({exc})") from exc
    try:
        from re import _parser

        tree = _parser.parse(pattern)
    except Exception:  # API interna de `re`: si cambia, queda la longitud
        return compiled
    if _has_nested_repeat(list(tree)):
        raise ProfileValidationError(
            f"{where}: repetición dentro de otra repetición (p. ej. «(a+)+»); "
            "puede tardar muchísimo en algunas líneas"
        )
    return compiled


def check_replacement(replacement: object, compiled: re.Pattern, where: str) -> None:
    """El texto de reemplazo de `line_substitutions`: solo texto, acotado y
    sin referencias a grupos que el patrón no tiene (`re.sub` fallaría en
    mitad de la importación). Un reemplazo nunca ejecuta código."""
    if not isinstance(replacement, str):
        raise ProfileValidationError(f"{where}: el reemplazo tiene que ser texto")
    if len(replacement) > MAX_REPLACEMENT_LENGTH:
        raise ProfileValidationError(f"{where}: reemplazo demasiado largo")
    for m in _GROUP_REF_RE.finditer(replacement):
        ref = m.group(1) if m.group(1) is not None else m.group(2)
        if ref.isdigit():
            if int(ref) > compiled.groups:
                raise ProfileValidationError(f"{where}: el patrón no tiene el grupo {ref}")
        elif ref not in compiled.groupindex:
            raise ProfileValidationError(f"{where}: el patrón no tiene el grupo «{ref}»")


def _str_list(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ProfileValidationError(f"{where}: tiene que ser una lista de textos")
    return value


def validate_user_profile_data(data: dict, file_stem: str | None = None) -> None:
    """Valida una plantilla del usuario ya leída con `tomllib` (que nunca
    ejecuta código). Lanza `ProfileValidationError` con el primer problema."""
    unknown = sorted(set(data) - KNOWN_PROFILE_KEYS)
    if unknown:
        raise ProfileValidationError(f"claves desconocidas: {', '.join(unknown)}")
    for key in ("id", "name"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ProfileValidationError(f"falta «{key}» (texto)")
    if not PROFILE_ID_RE.fullmatch(data["id"]):
        raise ProfileValidationError(
            "«id» solo puede tener minúsculas sin acentos, cifras y «_» (máximo 64)"
        )
    if file_stem is not None and data["id"] != file_stem:
        raise ProfileValidationError(
            f"el «id» ({data['id']}) no coincide con el nombre del fichero ({file_stem}.toml)"
        )
    if "priority" in data and (
        not isinstance(data["priority"], int) or isinstance(data["priority"], bool)
    ):
        raise ProfileValidationError("«priority» tiene que ser un número entero")
    for key in (
        "boundary_terms",
        "known_sections",
        "known_text_values",
        "bare_range_skip_if_contains",
        "strip_trailing_flags",
        "strip_mid_tokens",
        "following_range_labels",
    ):
        if key in data:
            _str_list(data[key], key)
    signature = data.get("signature", {})
    if not isinstance(signature, dict) or set(signature) - {"requires_any", "header_label_any"}:
        raise ProfileValidationError("«signature» solo admite requires_any y header_label_any")
    for key in ("requires_any", "header_label_any"):
        if key in signature:
            _str_list(signature[key], f"signature.{key}")
    if not signature.get("requires_any") and not signature.get("header_label_any"):
        raise ProfileValidationError("falta la firma ([signature] requires_any o header_label_any)")
    labels = data.get("header_labels", [])
    if not isinstance(labels, list):
        raise ProfileValidationError("«header_labels» tiene que ser una lista de tablas")
    for i, item in enumerate(labels, 1):
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            raise ProfileValidationError(f"header_labels nº {i}: falta «key»")
        check_pattern(item.get("pattern"), f"header_labels «{item['key']}»")
    if "sample_date_label" in data:
        item = data["sample_date_label"]
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            raise ProfileValidationError("sample_date_label: falta «key»")
        check_pattern(item.get("pattern"), "sample_date_label")
    for i, pattern in enumerate(data.get("ignore_line_patterns", []), 1):
        check_pattern(pattern, f"ignore_line_patterns nº {i}")
    for key in ("full_name_re", "metadata_row_re", "unranged_result_re"):
        if data.get(key):
            check_pattern(data[key], key)
    for i, item in enumerate(data.get("line_substitutions", []), 1):
        if not isinstance(item, dict):
            raise ProfileValidationError(f"line_substitutions nº {i}: tiene que ser una tabla")
        compiled = check_pattern(item.get("pattern"), f"line_substitutions nº {i}")
        check_replacement(item.get("replacement"), compiled, f"line_substitutions nº {i}")
    suffixes = data.get("section_name_suffixes", {})
    if not isinstance(suffixes, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in suffixes.items()
    ):
        raise ProfileValidationError("«section_name_suffixes» tiene que ser texto = texto")
    try:
        _profile_from_data(data)
    except (KeyError, TypeError, ValueError, re.error) as exc:
        raise ProfileValidationError(f"no se puede cargar: {exc}") from exc


# -- Carga de las plantillas -------------------------------------------------


@dataclass
class ProfileIssue:
    """Plantilla del usuario que no se usa, y por qué (para avisar)."""

    file: str
    kind: str  # "error" (no válida) o "conflicto" (mismo id que una de la app)
    message: str
    profile_id: str | None = None


_issues: list[ProfileIssue] = []


def replaced_app_profiles() -> set[str]:
    """Ids de plantillas de la aplicación que el usuario ha decidido
    sustituir por la suya del mismo id (`config.json`,
    `plantillas_sustituidas`). Sin decisión, gana la de la aplicación."""
    try:
        cfg = json.loads(config.APP_CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return set()
    value = cfg.get("plantillas_sustituidas", []) if isinstance(cfg, dict) else []
    return {v for v in value if isinstance(v, str)}


@lru_cache(maxsize=1)
def load_profiles() -> tuple[ParserProfile, ...]:
    """Carga las plantillas de la aplicación (`PARSER_PROFILES_DIR`) y las
    del usuario (`config.USER_PARSER_PROFILES_DIR`).

    Una plantilla del usuario no válida no se usa (ni rompe la carga del
    resto): queda en `profile_issues()`. Si tiene el mismo id que una de la
    aplicación, **no la sustituye en silencio**: se avisa (conflicto) y
    decide el usuario (`replaced_app_profiles`).

    Se devuelven ordenadas por `priority` ascendente (las más específicas,
    con una señal propia del centro, antes que las genéricas) para que
    `detect_profile` las evalúe en ese orden.
    """
    _issues.clear()
    app = [_load_profile(p) for p in sorted(PARSER_PROFILES_DIR.glob("*.toml"))]
    by_id = {p.id: p for p in app}
    app_ids = set(by_id)
    replaced = replaced_app_profiles()
    user_dir = config.USER_PARSER_PROFILES_DIR
    user_ids: set[str] = set()
    for path in sorted(user_dir.glob("*.toml")) if user_dir.is_dir() else []:
        try:
            profile = _load_profile(path, origin="usuario")
        except (OSError, tomllib.TOMLDecodeError, ProfileValidationError) as exc:
            _issues.append(ProfileIssue(path.name, "error", str(exc)))
            logger.warning("Plantilla del usuario no válida: %s", path.name)
            continue
        if profile.id in user_ids:
            _issues.append(
                ProfileIssue(path.name, "error", "id repetido en otra plantilla", profile.id)
            )
            continue
        user_ids.add(profile.id)
        if profile.id in app_ids and profile.id not in replaced:
            _issues.append(
                ProfileIssue(
                    path.name,
                    "conflicto",
                    "mismo id que una plantilla de la aplicación: se usa la de la aplicación",
                    profile.id,
                )
            )
            continue
        by_id[profile.id] = profile
    return tuple(sorted(by_id.values(), key=lambda p: p.priority))


def profile_issues() -> list[ProfileIssue]:
    """Plantillas del usuario que no se están usando (errores y conflictos)
    en la última carga."""
    load_profiles()
    return list(_issues)


def reload_profiles() -> tuple[ParserProfile, ...]:
    """Vuelve a leer las plantillas (tras guardar o borrar una)."""
    load_profiles.cache_clear()
    return load_profiles()


def _matches(profile: ParserProfile, text: str, deaccented: str) -> bool:
    if any(term in text or term in deaccented for term in profile.signature_requires_any):
        return True
    if profile.signature_header_label_any:
        header_labels_by_key = dict(profile.header_labels)
        for key in profile.signature_header_label_any:
            pattern = header_labels_by_key.get(key)
            if pattern and re.search(pattern, deaccented, re.IGNORECASE):
                return True
    return False


def matching_profiles(lines: list[str]) -> list[ParserProfile]:
    """Todas las plantillas cuya firma aparece en el documento, en el orden
    en que las prueba `detect_profile` (la primera es la que se usa). Más de
    una = firmas que se solapan: hay que revisarlas."""
    text = "\n".join(lines)
    deaccented = strip_accents(text)
    return [p for p in load_profiles() if _matches(p, text, deaccented)]


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
        if _matches(profile, text, deaccented):
            return profile
    return UNKNOWN_PROFILE
