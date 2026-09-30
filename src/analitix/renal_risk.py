# ---------------------------------------------------------------------------
# Script: renal_risk.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-18
# ---------------------------------------------------------------------------
"""Función renal orientativa.

Fórmulas y puntos de corte citados junto a la constante/función que los usa
(nunca de memoria, mismo criterio que `lipid_risk.py`/`hepatic_risk.py`) —
ver `docs/referencias_medicas/referencias_renal.md` y
`referencias_deterioro_renal_agudo.md` para el detalle completo con
DOI/PMID. Como el resto de la app, esto es **apoyo informativo y de
seguimiento, nunca un diagnóstico**.

El filtrado glomerular estimado debe venir en mL/min, la urea y la
creatinina en mg/dL, y el ratio albúmina/creatinina en mg/g (o su
equivalente numérico µg/mg) — si un resultado viene en otra unidad se
descarta ese punto en vez de calcular con cifras no comparables, mismo
criterio que `lipid_risk._mg_dl`.

**No implementado deliberadamente**: CKD-EPI 2021 (necesitaría el sexo del
paciente, dato sensible que Analitix no guarda, y la inmensa mayoría de los
informes reales ya traen el FG calculado por el laboratorio — ver
`referencias_renal.md` §2 para el detalle de por qué no se justifica hoy).
"""
from __future__ import annotations

import datetime as dt
import statistics
from typing import Any, Optional

from analitix.pdf_parser import compute_flag
from analitix.repository import get_merged_series

FG_IDS = (
    "filtrat_glomerular_estimat_serum", "filtrat_glomerular_estimat", "filtrat_glomerular_estimat_90_ml_min",
)
UREA_IDS = ("urea_serum",)
CREATININA_IDS = ("creatinina_serum",)
# `albuminuria`/`microalbuminuria` (mg/L) son concentración de albúmina en
# orina, NO un ratio albúmina/creatinina — confirmado revisando los PDF
# reales del proyecto (unidad mg/L, no convertible a un ACR en mg/g sin
# conocer también la creatinina de esa misma muestra de orina, que no viene
# junto a ellas). Solo estos dos sí son un ACR utilizable para KDIGO:
ACR_IDS = ("albumina_creatinina", "albumina_creatinina_orina_esporadica")

# Clasificación KDIGO de enfermedad renal crónica (categorías G y A) y mapa
# de riesgo cruzado G×A: Kidney Disease: Improving Global Outcomes (KDIGO)
# CKD Work Group. "KDIGO 2012 Clinical Practice Guideline for the
# Evaluation and Management of Chronic Kidney Disease." Kidney Int Suppl.
# 2013;3(1):1-150. doi:10.1038/kisup.2012.73. Categorías G/A verificadas de
# forma independiente contra StatPearls (NIH/NCBI Bookshelf, NBK535404); el
# mapa de riesgo verificado contra la adaptación oficial de la National
# Kidney Foundation ("CKD Risk Assessment Tool", 2015, "Adapted with
# permission from KDIGO 2012 CPG"):
# https://www.kidney.org/sites/default/files/01-10-7027_ABG_HeatMap_Card_3_0.pdf
GFR_CATEGORIES = (
    ("G1", 90.0), ("G2", 60.0), ("G3a", 45.0), ("G3b", 30.0), ("G4", 15.0), ("G5", 0.0),
)
ACR_A1_HIGH = 30.0
ACR_A2_HIGH = 300.0

KDIGO_RISK = {
    ("G1", "A1"): "verde", ("G1", "A2"): "amarillo", ("G1", "A3"): "naranja",
    ("G2", "A1"): "verde", ("G2", "A2"): "amarillo", ("G2", "A3"): "naranja",
    ("G3a", "A1"): "amarillo", ("G3a", "A2"): "naranja", ("G3a", "A3"): "rojo",
    ("G3b", "A1"): "naranja", ("G3b", "A2"): "rojo", ("G3b", "A3"): "rojo",
    ("G4", "A1"): "rojo", ("G4", "A2"): "rojo", ("G4", "A3"): "rojo_oscuro",
    ("G5", "A1"): "rojo_oscuro", ("G5", "A2"): "rojo_oscuro", ("G5", "A3"): "rojo_oscuro",
}
KDIGO_RISK_LABELS = {
    "verde": "Riesgo bajo",
    "amarillo": "Riesgo moderadamente aumentado",
    "naranja": "Riesgo alto",
    "rojo": "Riesgo muy alto",
    "rojo_oscuro": "Riesgo máximo",
}

# Ratio urea/creatinina: Higgins C. "Urea and creatinine concentration, the
# urea:creatinine ratio." acutecaretesting.org, 2016. El laboratorio con el
# que se ha desarrollado Analitix informa "urea" real (no BUN) en mg/dL —
# confirmado con el propio rango de referencia de los informes reales
# (17.1-49.3 mg/dL, coherente con urea real; el de BUN sería mucho más
# bajo, ~6-20 mg/dL). El corte clásico ">20 sugiere causa prerenal, <10
# sugiere causa renal intrínseca" está definido sobre BUN/creatinina (ambos
# mg/dL), así que aquí se escala por el factor peso molecular urea/nitrógeno
# ureico = 60/28 ≈ 2.14 (el mismo factor con el que la propia fuente
# relaciona urea y BUN) para obtener el corte equivalente sobre urea
# real/creatinina.
UREA_CREATININA_FACTOR = 60.0 / 28.0
UREA_CREATININA_LOW = 10.0 * UREA_CREATININA_FACTOR   # ≈21.4: sugiere causa renal intrínseca
UREA_CREATININA_HIGH = 20.0 * UREA_CREATININA_FACTOR  # ≈42.8: sugiere causa prerenal

# Aviso de subida brusca de creatinina (señal débil, no "detección de AKI"):
# Sawhney S, Fluck N, Marks A, et al. "Acute kidney injury—how does
# automated detection perform?" Nephrol Dial Transplant. 2015;30(11):
# 1853-1861. doi:10.1093/ndt/gfv094 — criterio 1 del algoritmo nacional de
# alerta de AKI del NHS England, el único de los tres pensado para
# analíticas espaciadas semanas/meses (los otros dos, de 48h y 7 días, no
# tienen sentido con el patrón de datos de Analitix): creatinina actual >=
# 1.5x la mediana de las creatininas de ese paciente entre 8 y 365 días
# antes.
AKI_WINDOW_MIN_DAYS = 8
AKI_WINDOW_MAX_DAYS = 365
AKI_RATIO_HIGH = 1.5


def _mg_dl(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico si la unidad es mg/dL (urea/creatinina)."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if unit not in ("mg/dl", "mgdl"):
        return None
    return row.get("value_num")


def _ml_min(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico del FG si la unidad empieza por mL/min."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if not unit.startswith("ml/min"):
        return None
    return row.get("value_num")


def _acr_mg_g(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico del ratio albúmina/creatinina si la unidad es mg/g o
    su equivalente numérico µg/mg (1 µg/mg = 1 mg/g: numerador y
    denominador escalan ×1000 en sentido opuesto, se cancela)."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if unit not in ("mg/g_creat", "mg/g", "mcg/mg"):
        return None
    return row.get("value_num")


def gfr_category(value: Optional[float]) -> Optional[str]:
    """Categoría KDIGO G1-G5 de un filtrado glomerular estimado (mL/min)."""
    if value is None:
        return None
    for label, threshold in GFR_CATEGORIES:
        if value >= threshold:
            return label
    return "G5"


def acr_category(value: Optional[float]) -> Optional[str]:
    """Categoría KDIGO A1-A3 de un ratio albúmina/creatinina (mg/g)."""
    if value is None:
        return None
    if value < ACR_A1_HIGH:
        return "A1"
    if value < ACR_A2_HIGH:
        return "A2"
    return "A3"


def kdigo_risk(g: Optional[str], a: Optional[str]) -> Optional[str]:
    """Nivel de riesgo KDIGO ("verde".."rojo_oscuro") para una combinación
    G×A, o `None` si falta cualquiera de las dos categorías (sin
    albuminuria no se puede clasificar el riesgo con fiabilidad, ni
    siquiera con G1/G2 — ver KDIGO 2012)."""
    if g is None or a is None:
        return None
    return KDIGO_RISK.get((g, a))


def urea_creatinina_ratio(urea: Optional[float], creatinina: Optional[float]) -> Optional[float]:
    """Ratio urea/creatinina (ambos mg/dL, urea real de este laboratorio —
    ver `UREA_CREATININA_FACTOR` para la escala frente al BUN/Cr clásico)."""
    if urea is None or creatinina is None or creatinina == 0:
        return None
    return urea / creatinina


def aki_ratio(
    creatinina_actual: Optional[float], creatininas_previas: list[tuple[str, float]], fecha: str
) -> Optional[float]:
    """Ratio de la creatinina actual frente a la mediana de las creatininas
    de ese paciente entre `AKI_WINDOW_MIN_DAYS` y `AKI_WINDOW_MAX_DAYS` días
    antes de `fecha` (criterio 1 de Sawhney et al. 2015). `creatininas_previas`
    es una lista de `(fecha, value)` de todos los informes de ese paciente
    (puede incluir `fecha` misma, se excluye internamente). `None` si no hay
    ninguna creatinina previa en esa ventana."""
    if creatinina_actual is None:
        return None
    referencia = dt.date.fromisoformat(fecha[:10])
    ventana = [
        value for f, value in creatininas_previas
        if f != fecha and AKI_WINDOW_MIN_DAYS <= (referencia - dt.date.fromisoformat(f[:10])).days <= AKI_WINDOW_MAX_DAYS
    ]
    if not ventana:
        return None
    return creatinina_actual / statistics.median(ventana)


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


def get_renal_index_series(con, patient_id: int) -> dict[str, list[dict[str, Any]]]:
    """Serie temporal (una fecha = un informe) de los índices renales
    calculables a partir de lo ya almacenado, en el mismo formato que
    `repository.get_series`. Devuelve solo las claves de índice que tengan
    al menos un punto calculable."""
    urea_by_date = get_merged_series(con, UREA_IDS, patient_id)
    creat_by_date = get_merged_series(con, CREATININA_IDS, patient_id)
    creatininas_todas = [
        (fecha, row["value_num"]) for fecha, row in creat_by_date.items() if _mg_dl(row) is not None
    ]

    series: dict[str, list[dict[str, Any]]] = {"idx_urea_creatinina": [], "idx_aki_creatinina": []}
    fechas = sorted(set(urea_by_date) | set(creat_by_date))
    for fecha in fechas:
        urea = _mg_dl(urea_by_date.get(fecha))
        creatinina = _mg_dl(creat_by_date.get(fecha))

        r = urea_creatinina_ratio(urea, creatinina)
        if r is not None:
            series["idx_urea_creatinina"].append(
                _index_point(fecha, r, UREA_CREATININA_LOW, UREA_CREATININA_HIGH, "Ratio urea/creatinina")
            )
        ratio_aki = aki_ratio(creatinina, creatininas_todas, fecha)
        if ratio_aki is not None:
            series["idx_aki_creatinina"].append(
                _index_point(fecha, ratio_aki, None, AKI_RATIO_HIGH, "Creatinina actual / mediana del último año")
            )

    return {key: points for key, points in series.items() if points}


# Etiqueta legible de cada índice sintético, para la lista de selección de
# la pestaña "🩺 Función renal" (gui.py). El texto largo con las citas
# completas vive en `data/descripciones/idx_*.txt` (mismo patrón que
# `lipid_risk.INDEX_LABELS`/`hepatic_risk.INDEX_LABELS`).
INDEX_LABELS = {
    "idx_urea_creatinina": "Ratio urea/creatinina",
    "idx_aki_creatinina": "Creatinina actual / mediana del último año",
}


def get_latest_renal_summary(con, patient_id: int) -> Optional[dict[str, Any]]:
    """Último informe con filtrado glomerular estimado disponible, con la
    clasificación KDIGO (si también hay un ACR utilizable ese mismo día) y
    los índices calculables. `None` si el paciente no tiene ningún FG en
    mL/min guardado."""
    fg_by_date = get_merged_series(con, FG_IDS, patient_id)
    fechas_fg = sorted(f for f, row in fg_by_date.items() if _ml_min(row) is not None)
    if not fechas_fg:
        return None
    fecha = fechas_fg[-1]

    acr_by_date = get_merged_series(con, ACR_IDS, patient_id)
    urea_by_date = get_merged_series(con, UREA_IDS, patient_id)
    creat_by_date = get_merged_series(con, CREATININA_IDS, patient_id)
    creatininas_todas = [
        (f, row["value_num"]) for f, row in creat_by_date.items() if _mg_dl(row) is not None
    ]

    fg = _ml_min(fg_by_date.get(fecha))
    acr = _acr_mg_g(acr_by_date.get(fecha))
    urea = _mg_dl(urea_by_date.get(fecha))
    creatinina = _mg_dl(creat_by_date.get(fecha))
    g = gfr_category(fg)
    a = acr_category(acr)

    return {
        "fecha": fecha,
        "fg": fg,
        "acr": acr,
        "urea": urea,
        "creatinina": creatinina,
        "g_categoria": g,
        "a_categoria": a,
        "riesgo_kdigo": kdigo_risk(g, a),
        "urea_creatinina": urea_creatinina_ratio(urea, creatinina),
        "aki_ratio": aki_ratio(creatinina, creatininas_todas, fecha),
    }
