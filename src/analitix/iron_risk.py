# ---------------------------------------------------------------------------
# Script: iron_risk.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-18
# ---------------------------------------------------------------------------
"""Metabolismo del hierro orientativo.

Fórmulas y puntos de corte citados junto a la constante/función que los usa
(nunca de memoria, mismo criterio que `lipid_risk.py`/`hepatic_risk.py`/
`renal_risk.py`/`hemogram_risk.py`) — ver
`docs/referencias_medicas/referencias_hierro_glucosa.md` para el detalle
completo con URL. Como el resto de la app, esto es **apoyo informativo y de
seguimiento, nunca un diagnóstico**.

El hierro sérico debe venir en µg/dL, la ferritina en ng/mL (numéricamente
igual a µg/L), la transferrina en mg/dL y la saturación de transferrina en
% — si un resultado viene en otra unidad se descarta ese punto, mismo
criterio que `lipid_risk._mg_dl`.

**No implementado deliberadamente**: un algoritmo automático que decida
entre ferropenia/anemia de trastorno crónico/sobrecarga de hierro — Analitix
no guarda de forma estructurada si el paciente tiene un proceso inflamatorio
activo (la ferritina es un reactante de fase aguda, sube con cualquier
inflamación sin que signifique sobrecarga), así que un algoritmo así podría
sugerir con más seguridad de la debida una interpretación que en realidad
depende de contexto clínico que la app no tiene. En su lugar se muestran
los valores clasificados por separado y una tabla de referencia orientativa
como texto, dejando la síntesis final al usuario/médico — ver
`referencias_hierro_glucosa.md` para el detalle de esta decisión.
"""
from __future__ import annotations

from typing import Any, Optional

from analitix.pdf_parser import compute_flag
from analitix.repository import get_merged_series
from analitix.textutils import unit_key

# Dos plantillas del mismo laboratorio nombran estos parámetros de forma
# distinta según la época (con o sin el sufijo "sèrum") generando
# `canonical_id` diferentes para el mismo parámetro — confirmado revisando
# los 39 PDF reales del proyecto (p. ej. "Ferritina" en informes de 2014,
# "Ferritina sèrum" en informes más recientes). Fusionados con
# `repository.get_merged_series`, mismo criterio que
# `hemogram_risk.LIMFOCITS_IDS`.
FERRO_IDS = ("ferro_serum", "ferro")
FERRITINA_IDS = ("ferritina_serum", "ferritina")
TRANSFERRINA_IDS = ("transferrina_serum", "transferrina")
# "saturacio" (sin más apellido) es un `canonical_id` genérico que en teoría
# podría corresponder a cualquier "saturación" (de ahí que exista también
# `saturacio_o2` como `canonical_id` aparte para la saturación de oxígeno) —
# verificado que su única aparición en los 39 PDF reales del proyecto es en
# un informe de 2014, justo a continuación de "Ferro"/"Transferrina" y con
# un valor (17.3%) compatible solo con saturación de transferrina, nunca con
# saturación de oxígeno (fisiológicamente incompatible con la vida). Se
# incluye aquí con esa comprobación explícita, no por asunción.
TSAT_IDS = ("saturacio_transferrina_serum", "saturacio")

# Fórmula de saturación de transferrina (solo como relleno para el día en
# que el informe no la traiga ya calculada, mismo patrón que el LDL por
# Friedewald en `lipid_risk.py`): TSAT (%) = [Hierro (µg/dL) ÷
# (Transferrina (mg/dL) × 1.42)] × 100. El factor de conversión (~1.40-1.49
# mg de hierro por gramo de transferrina, capacidad de fijación de la
# proteína) — ver Wikipedia, "Total iron-binding capacity":
# https://en.wikipedia.org/wiki/Total_iron-binding_capacity — y la fórmula
# exacta con el factor 1.42 en el apéndice de un protocolo de ensayo
# clínico público (NCT03920657, Appendix G): "Transferrin saturation
# calculation [Serum iron / (serum transferrin x 1.42)] x 100".
TSAT_TRANSFERRINA_FACTOR = 1.42

# Umbral bajo de TSAT (sugiere ferropenia): University of Iowa, Department
# of Pathology, "Iron Panel (IRON, TRANSFERRIN, TIBC and % SATURATION)":
# https://www.healthcare.uiowa.edu/path_handbook/handbook/test1151.html
TSAT_LOW = 20.0
# Umbral alto de TSAT ("motivo de estudio", no hemocromatosis establecida
# -esa suele ser >60%-): Medscape, "Transferrin Saturation: Reference
# Range, Interpretation, Collection and Panels", rango citado 45-50% —
# https://emedicine.medscape.com/article/2087960-overview — se usa el
# extremo superior del rango (50%) para no marcar "alto" de más en una app
# de seguimiento personal, mismo criterio ya aplicado al HDL de
# `lipid_risk.ATP3_LOW` y al PLR de `hemogram_risk.PLR_HIGH`.
TSAT_HIGH = 50.0

# Umbral bajo de ferritina en adultos sin inflamación/infección activa (con
# inflamación el umbral relevante sube a 70 µg/L, pero Analitix no guarda
# si hay un proceso inflamatorio activo, así que no se automatiza ese
# segundo umbral — ver el aviso del panel). WHO, "WHO guideline on use of
# ferritin concentrations to assess iron status in individuals and
# populations", Geneva, 2020 (umbrales de 1993 revalidados por opinión de
# expertos, certeza de evidencia baja/muy baja — el propio documento lo
# señala como limitación): https://www.ncbi.nlm.nih.gov/books/NBK569877/
FERRITINA_LOW = 15.0


def _mcg_dl(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico del hierro sérico si su unidad es µg/dL (extraída
    como "mcg/dl" en los PDF reales del proyecto)."""
    if row is None:
        return None
    if unit_key(row.get("unit")) not in ("mcg/dl", "mcgdl"):
        return None
    return row.get("value_num")


def _ng_ml(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de la ferritina si su unidad es ng/mL (numéricamente
    igual a µg/L, la unidad de los umbrales de la OMS)."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if unit not in ("ng/ml", "ngml"):
        return None
    return row.get("value_num")


def _mg_dl(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de la transferrina si su unidad es mg/dL (mismo
    criterio que `lipid_risk._mg_dl`)."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if unit not in ("mg/dl", "mgdl"):
        return None
    return row.get("value_num")


def _percent(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de la saturación de transferrina si su unidad es %."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().replace(" ", "")
    if unit != "%":
        return None
    return row.get("value_num")


def tsat_from_iron_transferrin(ferro: Optional[float], transferrina: Optional[float]) -> Optional[float]:
    """TSAT (%) = [hierro (µg/dL) ÷ (transferrina (mg/dL) × 1.42)] × 100 —
    solo como relleno cuando el informe no trae ya la saturación de
    transferrina calculada."""
    if ferro is None or transferrina is None or transferrina == 0:
        return None
    return (ferro / (transferrina * TSAT_TRANSFERRINA_FACTOR)) * 100


def _index_point(
    fecha: str, value: float, ref_low: Optional[float], ref_high: Optional[float], raw_name: str
) -> dict[str, Any]:
    """Fila con la misma forma que `repository.get_series`, para reutilizar
    `charts.evolution_figure`/`comparison_figure` sin cambios."""
    return {
        "fecha": fecha,
        "value_num": value,
        "unit": "",
        "ref_low": ref_low,
        "ref_high": ref_high,
        "flag_calc": compute_flag(value, ref_low, ref_high),
        "raw_name": raw_name,
    }


def get_iron_index_series(con, patient_id: int) -> dict[str, list[dict[str, Any]]]:
    """Serie temporal (una fecha = un informe) de ferritina y TSAT, en el
    mismo formato que `repository.get_series`. La TSAT usa el valor del
    laboratorio si ese informe lo trae; si no, se calcula con
    `tsat_from_iron_transferrin` a partir del hierro y la transferrina de
    ese mismo informe (si ambos están disponibles)."""
    ferro_by_date = get_merged_series(con, FERRO_IDS, patient_id)
    ferritina_by_date = get_merged_series(con, FERRITINA_IDS, patient_id)
    transferrina_by_date = get_merged_series(con, TRANSFERRINA_IDS, patient_id)
    tsat_by_date = get_merged_series(con, TSAT_IDS, patient_id)

    series: dict[str, list[dict[str, Any]]] = {"idx_ferritina": [], "idx_tsat": []}
    fechas = sorted(
        set(ferro_by_date) | set(ferritina_by_date) | set(transferrina_by_date) | set(tsat_by_date)
    )
    for fecha in fechas:
        ferritina = _ng_ml(ferritina_by_date.get(fecha))
        if ferritina is not None:
            series["idx_ferritina"].append(_index_point(fecha, ferritina, FERRITINA_LOW, None, "Ferritina"))

        tsat = _percent(tsat_by_date.get(fecha))
        if tsat is None:
            ferro = _mcg_dl(ferro_by_date.get(fecha))
            transferrina = _mg_dl(transferrina_by_date.get(fecha))
            tsat = tsat_from_iron_transferrin(ferro, transferrina)
        if tsat is not None:
            series["idx_tsat"].append(
                _index_point(fecha, tsat, TSAT_LOW, TSAT_HIGH, "Saturación de transferrina (TSAT)")
            )

    return {key: points for key, points in series.items() if points}


# Etiqueta legible de cada índice, para la lista de selección de la pestaña
# "🩸 Metabolismo del hierro" (gui.py). El texto largo con las citas
# completas y la explicación en lenguaje llano vive en
# `data/descripciones/idx_*.txt` (mismo patrón que el resto de módulos de
# riesgo clínico).
INDEX_LABELS = {
    "idx_ferritina": "Ferritina",
    "idx_tsat": "Saturación de transferrina (TSAT)",
}


def get_latest_iron_summary(con, patient_id: int) -> Optional[dict[str, Any]]:
    """Último informe con algún dato del metabolismo del hierro disponible
    (hierro, ferritina, transferrina o TSAT), con sus valores y
    clasificaciones. `None` si el paciente no tiene ninguno guardado."""
    ferro_by_date = get_merged_series(con, FERRO_IDS, patient_id)
    ferritina_by_date = get_merged_series(con, FERRITINA_IDS, patient_id)
    transferrina_by_date = get_merged_series(con, TRANSFERRINA_IDS, patient_id)
    tsat_by_date = get_merged_series(con, TSAT_IDS, patient_id)

    fechas = sorted(
        f
        for f in set(ferro_by_date) | set(ferritina_by_date) | set(transferrina_by_date) | set(tsat_by_date)
        if _mcg_dl(ferro_by_date.get(f)) is not None
        or _ng_ml(ferritina_by_date.get(f)) is not None
        or _mg_dl(transferrina_by_date.get(f)) is not None
        or _percent(tsat_by_date.get(f)) is not None
    )
    if not fechas:
        return None
    fecha = fechas[-1]

    ferro = _mcg_dl(ferro_by_date.get(fecha))
    ferritina = _ng_ml(ferritina_by_date.get(fecha))
    transferrina = _mg_dl(transferrina_by_date.get(fecha))
    tsat_lab = _percent(tsat_by_date.get(fecha))
    tsat_estimado = tsat_lab is None
    tsat = tsat_lab if tsat_lab is not None else tsat_from_iron_transferrin(ferro, transferrina)

    return {
        "fecha": fecha,
        "ferro": ferro,
        "ferritina": ferritina,
        "ferritina_flag": compute_flag(ferritina, FERRITINA_LOW, None),
        "transferrina": transferrina,
        "tsat": tsat,
        "tsat_estimado": tsat_estimado if tsat is not None else False,
        "tsat_flag": compute_flag(tsat, TSAT_LOW, TSAT_HIGH),
    }
