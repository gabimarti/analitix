# ---------------------------------------------------------------------------
# Script: lipid_risk.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-10
# ---------------------------------------------------------------------------
"""Perfil lipídico y riesgo cardiovascular orientativo.

Todas las fórmulas y puntos de corte de este módulo están citados con su
fuente (artículo científico o guía clínica, con URL) junto a la función que
los usa. Igual que el resto de la app (ver `charts.py`), esto es **apoyo
informativo y de seguimiento, nunca un diagnóstico**: los puntos de corte de
los índices lipídicos (Castelli I/II, TG/HDL) son orientativos y varían
según la población de estudio y la fuente consultada — aquí se ha elegido un
único punto de corte no diferenciado por sexo (Analitix no guarda el sexo
del paciente) tomado de un estudio que expresamente lo define así, en vez de
mezclar cifras específicas de sexo de fuentes distintas.

Todos los cálculos requieren mg/dL (la unidad que usa el laboratorio con el
que se ha desarrollado y probado Analitix, ver §1 de
`docs/DOCUMENTACION_TECNICA.md`); si algún resultado viene en otra unidad
(p. ej. mmol/L de un laboratorio distinto) se descarta ese punto en vez de
calcular con cifras que no son comparables — ver `_mg_dl`.
"""
from __future__ import annotations

from typing import Any, Optional

from analitix.pdf_parser import compute_flag
from analitix.repository import get_merged_series

# canonical_id de cada parámetro del panel lipídico. Más de un id por
# parámetro porque distintas plantillas del mismo laboratorio han nombrado
# la misma prueba de forma ligeramente distinta ("Colesterol" vs
# "Colesterol sèrum"), lo que generó canonical_id distintos que "Normalizar
# pruebas" (catalog.py) no funde automáticamente al no saberlos sinónimos de
# antemano — ver docs/DOCUMENTACION_TECNICA.md §5 (catalog.py).
TOTAL_IDS = ("colesterol_serum", "colesterol")
HDL_IDS = ("colesterol_hdl_serum", "colesterol_hdl")
LDL_IDS = ("colesterol_ldl",)
NON_HDL_IDS = ("colesterol_no_hdl_serum",)
VLDL_IDS = ("colesterol_vldl",)
TG_IDS = ("triglicerids_serum", "triglicerids")

# Fórmula de Friedewald: LDL = Total - HDL - TG/5 (mg/dL), no válida con
# triglicéridos >= 400 mg/dL. Cita completa, límite de validez y su
# justificación: ver `data/descripciones/idx_ldl_estimado.txt` (mismo texto
# que se muestra en la GUI, ver `catalog.get_description`).
FRIEDEWALD_MAX_TG = 400.0

# Puntos de corte orientativos (no diferenciados por sexo) para los tres
# índices de riesgo cardiovascular derivados del perfil lipídico: Castelli I
# (CT/HDL) >= 5.0, Castelli II (LDL/HDL) >= 3.0, TG/HDL >= 3.0. Citas
# completas, significado clínico y aviso de aplicabilidad poblacional
# (ninguna fuente usada es población europea; investigado 2026-09-10 —
# las guías europeas actuales, ESC/EAS y SCORE2, no dan un sustituto
# simple): ver `data/descripciones/idx_castelli1.txt`,
# `idx_castelli2.txt` e `idx_tg_hdl.txt` (mismo texto que se muestra en la
# GUI, ver `catalog.get_description`); la GUI (`gui._build_tab_riesgo_cv`)
# avisa además explícitamente de esta limitación poblacional en pantalla.
CASTELLI_1_HIGH = 5.0
CASTELLI_2_HIGH = 3.0
TG_HDL_HIGH = 3.0

# Clasificación de los valores lipídicos "en crudo" (no de los índices):
# National Cholesterol Education Program, Adult Treatment Panel III (ATP
# III). "Third Report of the Expert Panel on Detection, Evaluation, and
# Treatment of High Blood Cholesterol in Adults." NIH/NHLBI, 2002.
# https://www.nhlbi.nih.gov/files/docs/guidelines/atp3xsum.pdf — también
# publicado en Circulation. 2002;106(25):3143-3421.
# https://www.ahajournals.org/doi/10.1161/circ.106.25.3227
# Se usa un único punto de corte "alto" por parámetro (no los 5 niveles
# completos de ATP III) para ser coherente con el resto de la app, que
# clasifica cada resultado como alto/bajo/normal según el propio rango del
# informe (ver `pdf_parser.compute_flag`); el umbral elegido es el de
# "límite alto"/"bajo" de ATP III, no el más estricto de "óptimo":
# - Colesterol total: deseable < 200, límite alto 200-239, alto >= 240.
# - LDL: óptimo < 100, casi óptimo 100-129, límite alto 130-159, alto
#   160-189, muy alto >= 190.
# - HDL: bajo (factor de riesgo) < 40 — algunas guías posteriores usan
#   < 50 mg/dL específicamente para mujeres; Analitix no guarda el sexo del
#   paciente, así que usa el único umbral que define ATP III. Protector
#   >= 60 (no se marca "alto": un HDL alto no es un problema).
# - Triglicéridos: normal < 150, límite alto 150-199, alto 200-499, muy
#   alto >= 500.
ATP3_HIGH = {"total": 200.0, "ldl": 130.0, "tg": 150.0}
ATP3_LOW = {"hdl": 40.0}


def _mg_dl(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de `row` si su unidad es mg/dL (única unidad que usa
    el laboratorio soportado hoy), `None` en cualquier otro caso — incluido
    `row is None` (el parámetro no está en ese informe)."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if unit not in ("mg/dl", "mgdl"):
        return None
    return row.get("value_num")


def ldl_friedewald(total: Optional[float], hdl: Optional[float], tg: Optional[float]) -> Optional[float]:
    """LDL estimado (mg/dL) por la fórmula de Friedewald — ver
    `FRIEDEWALD_MAX_TG` para la cita y el límite de validez."""
    if total is None or hdl is None or tg is None or tg >= FRIEDEWALD_MAX_TG:
        return None
    return total - hdl - tg / 5.0


def castelli_1(total: Optional[float], hdl: Optional[float]) -> Optional[float]:
    """Índice aterogénico / Castelli I: colesterol total ÷ HDL."""
    if total is None or hdl is None or hdl == 0:
        return None
    return total / hdl


def castelli_2(ldl: Optional[float], hdl: Optional[float]) -> Optional[float]:
    """Castelli II: LDL ÷ HDL."""
    if ldl is None or hdl is None or hdl == 0:
        return None
    return ldl / hdl


def tg_hdl_ratio(tg: Optional[float], hdl: Optional[float]) -> Optional[float]:
    """Índice TG/HDL: marcador indirecto de resistencia a la insulina y de
    partículas LDL pequeñas y densas — ver cita de McLaughlin et al. en
    `data/descripciones/idx_tg_hdl.txt`."""
    if tg is None or hdl is None or hdl == 0:
        return None
    return tg / hdl


def _index_point(fecha: str, value: float, ref_high: float, raw_name: str) -> dict[str, Any]:
    """Fila con la misma forma que `repository.get_series` (para poder
    reutilizar `charts.evolution_figure`/`comparison_figure` sin cambios).
    Los índices de esta lista no tienen un mínimo clínicamente significativo
    (más bajo siempre es mejor), así que `ref_low` es siempre `None`."""
    return {
        "fecha": fecha,
        "value_num": value,
        "unit": "",
        "ref_low": None,
        "ref_high": ref_high,
        "flag_calc": compute_flag(value, None, ref_high),
        "raw_name": raw_name,
    }


def get_lipid_index_series(con, patient_id: int) -> dict[str, list[dict[str, Any]]]:
    """Serie temporal (una fecha = un informe) de los índices calculables a
    partir del perfil lipídico ya almacenado, en el mismo formato que
    `repository.get_series` — pensada para pasar directamente a
    `charts.evolution_figure`/`comparison_figure`. Devuelve solo las claves
    de índice que tengan al menos un punto calculable."""
    total_by_date = get_merged_series(con, TOTAL_IDS, patient_id)
    hdl_by_date = get_merged_series(con, HDL_IDS, patient_id)
    ldl_by_date = get_merged_series(con, LDL_IDS, patient_id)
    tg_by_date = get_merged_series(con, TG_IDS, patient_id)

    series: dict[str, list[dict[str, Any]]] = {
        "idx_castelli1": [], "idx_castelli2": [], "idx_tg_hdl": [], "idx_ldl_estimado": [],
    }
    fechas = sorted(set(total_by_date) | set(hdl_by_date) | set(ldl_by_date) | set(tg_by_date))
    for fecha in fechas:
        total = _mg_dl(total_by_date.get(fecha))
        hdl = _mg_dl(hdl_by_date.get(fecha))
        ldl_medido = _mg_dl(ldl_by_date.get(fecha))
        tg = _mg_dl(tg_by_date.get(fecha))
        ldl = ldl_medido if ldl_medido is not None else ldl_friedewald(total, hdl, tg)

        c1 = castelli_1(total, hdl)
        if c1 is not None:
            series["idx_castelli1"].append(_index_point(fecha, c1, CASTELLI_1_HIGH, "Índice aterogénico (Castelli I)"))
        c2 = castelli_2(ldl, hdl)
        if c2 is not None:
            series["idx_castelli2"].append(_index_point(fecha, c2, CASTELLI_2_HIGH, "Índice LDL/HDL (Castelli II)"))
        r = tg_hdl_ratio(tg, hdl)
        if r is not None:
            series["idx_tg_hdl"].append(_index_point(fecha, r, TG_HDL_HIGH, "Índice TG/HDL"))
        if ldl_medido is None and ldl is not None:
            series["idx_ldl_estimado"].append(_index_point(fecha, ldl, ATP3_HIGH["ldl"], "LDL estimado (Friedewald)"))

    return {key: points for key, points in series.items() if points}


# Etiqueta legible + descripción corta de cada índice sintético, para la
# lista de selección de la pestaña "Riesgo cardiovascular" (gui.py). El texto
# largo con las citas completas vive en `data/descripciones/idx_*.txt` (se
# muestra igual que la descripción de cualquier otro parámetro, ver
# `catalog.get_description`).
INDEX_LABELS = {
    "idx_castelli1": "Índice aterogénico (Colesterol total / HDL)",
    "idx_castelli2": "Índice LDL / HDL (Castelli II)",
    "idx_tg_hdl": "Índice Triglicéridos / HDL",
    "idx_ldl_estimado": "LDL estimado (fórmula de Friedewald)",
}


def get_latest_lipid_summary(con, patient_id: int) -> Optional[dict[str, Any]]:
    """Último informe con al menos colesterol total y HDL en mg/dL, con
    todos los valores del panel lipídico disponibles ese día (medidos o,
    para el LDL que falte, estimado) y sus índices — para el resumen de
    texto de la pestaña "Riesgo cardiovascular". `None` si el paciente no
    tiene ningún informe con perfil lipídico utilizable."""
    total_by_date = get_merged_series(con, TOTAL_IDS, patient_id)
    hdl_by_date = get_merged_series(con, HDL_IDS, patient_id)
    if not total_by_date or not hdl_by_date:
        return None
    fechas_comunes = sorted(set(total_by_date) & set(hdl_by_date))
    if not fechas_comunes:
        return None
    fecha = fechas_comunes[-1]
    ldl_by_date = get_merged_series(con, LDL_IDS, patient_id)
    non_hdl_by_date = get_merged_series(con, NON_HDL_IDS, patient_id)
    vldl_by_date = get_merged_series(con, VLDL_IDS, patient_id)
    tg_by_date = get_merged_series(con, TG_IDS, patient_id)

    total = _mg_dl(total_by_date.get(fecha))
    hdl = _mg_dl(hdl_by_date.get(fecha))
    ldl_medido = _mg_dl(ldl_by_date.get(fecha))
    tg = _mg_dl(tg_by_date.get(fecha))
    ldl = ldl_medido if ldl_medido is not None else ldl_friedewald(total, hdl, tg)

    return {
        "fecha": fecha,
        "total": total, "total_flag": compute_flag(total, None, ATP3_HIGH["total"]),
        "hdl": hdl, "hdl_flag": compute_flag(hdl, ATP3_LOW["hdl"], None),
        "ldl": ldl, "ldl_estimado": ldl_medido is None and ldl is not None,
        "ldl_flag": compute_flag(ldl, None, ATP3_HIGH["ldl"]),
        "non_hdl": _mg_dl(non_hdl_by_date.get(fecha)),
        "vldl": _mg_dl(vldl_by_date.get(fecha)),
        "tg": tg, "tg_flag": compute_flag(tg, None, ATP3_HIGH["tg"]),
        "castelli_1": castelli_1(total, hdl),
        "castelli_2": castelli_2(ldl, hdl),
        "tg_hdl": tg_hdl_ratio(tg, hdl),
    }
