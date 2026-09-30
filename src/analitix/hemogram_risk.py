# ---------------------------------------------------------------------------
# Script: hemogram_risk.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-18
# ---------------------------------------------------------------------------
"""Hemograma y series roja/blanca orientativas.

Fórmulas y puntos de corte citados junto a la constante/función que los usa
(nunca de memoria, mismo criterio que `lipid_risk.py`/`hepatic_risk.py`/
`renal_risk.py`) — ver `docs/referencias_medicas/referencias_hemograma.md`
para el detalle completo con DOI/PMID. Como el resto de la app, esto es
**apoyo informativo y de seguimiento, nunca un diagnóstico**.

Los recuentos (neutrófilos, linfocitos, monocitos, plaquetas) deben venir
en x10³/µL (numéricamente igual a las 10⁹/L de las fórmulas), los hematíes
en x10⁶/µL, el VCM en fL y el RDW en % — si un resultado viene en otra
unidad se descarta ese punto, mismo criterio que `lipid_risk._mg_dl`.

**Excluido deliberadamente**: cualquier aviso orientativo de leucemia u
otras neoplasias hematológicas — investigado en
`docs/referencias_medicas/referencias_leucemia_hematologia.md`, conclusión:
no existe un score o índice combinado validado en la literatura para eso,
a diferencia de los índices de este módulo.
"""
from __future__ import annotations

from typing import Any, Optional

from analitix.pdf_parser import compute_flag
from analitix.repository import get_merged_series
from analitix.textutils import is_count_1e9_l, is_count_1e12_l

NEUTROFILS_IDS = ("neutrofils_total",)
# Dos ortografías catalanas distintas de "limfòcits"/"linfòcits" usadas en
# distintas épocas de la misma plantilla del laboratorio generan dos
# `canonical_id` diferentes para el mismo parámetro — confirmado contando
# los 39 PDF reales del proyecto (17 + 15 = 32, igual que neutrofils_total/
# monocits_total). Sin fusionar ambas, la serie de linfocitos perdería casi
# la mitad de los puntos.
LIMFOCITS_IDS = ("limfocits_total", "linfocits_total")
MONOCITS_IDS = ("monocits_total",)
PLAQUETES_IDS = ("plaquetes",)
VCM_IDS = ("vcm",)
HEMATIES_IDS = ("hematies",)
RDW_IDS = ("rdw_cv",)

# NLR: Wang J, Zhang F, Jiang F, et al. "Distribution and reference
# interval establishment of neutral-to-lymphocyte ratio (NLR),
# lymphocyte-to-monocyte ratio (LMR), and platelet-to-lymphocyte ratio
# (PLR) in Chinese healthy adults." J Clin Lab Anal. 2021;35(9):e23935.
# doi:10.1002/jcla.23935 (404 272 adultos sanos; NLR 0-2.696 hombres,
# 0-2.805 mujeres — Analitix no guarda el sexo del paciente). Se usa en su
# lugar el intervalo global (sin diferenciar por sexo) de una corroboración
# independiente con población y método distintos, mismo orden de magnitud:
# Wang Q, Jiang Y, Jin F, et al. Front Cell Infect Microbiol.
# 2025;15:1529532. doi:10.3389/fcimb.2025.1529532 (165 504 personas,
# percentil 2.5-97.5 global). Es un intervalo de normalidad poblacional,
# no un umbral de riesgo de ninguna enfermedad — ver `idx_nlr.txt`.
NLR_HIGH = 3.83

# PLR: mismo estudio que NLR (Wang J et al. 2021), sin corroboración global
# no diferenciada por sexo disponible. Se usa el mayor de los dos umbrales
# por sexo (mujeres) para no marcar "alto" de más en un paciente cuyo sexo
# no se conoce — mismo criterio ya aplicado al HDL de `lipid_risk.ATP3_LOW`.
PLR_HIGH = 185.52

# LMR: mismo estudio (Wang J et al. 2021) da un intervalo de normalidad
# poblacional (0-9.00 hombres, 0-10.00 mujeres), pero la literatura
# pronóstica en oncología asocia un valor **bajo** (no alto) a peor
# pronóstico — un sentido opuesto al de NLR/PLR. Como esa literatura no da
# aquí un punto de corte numérico verificado para "bajo", no se marca
# ningún `ref_low`/`ref_high`: el índice se muestra como serie/tendencia
# sin alerta automática, ver `idx_lmr.txt`.

# Índice de Mentzer: Mentzer WC Jr. "Differentiation of iron deficiency
# from thalassaemia trait." Lancet. 1973 Apr 21;1(7808):882. PMID: 4123424.
# Por debajo de 13 orienta a rasgo talasémico-β, por encima a anemia
# ferropénica — solo tiene sentido clínico cuando el VCM ya es microcítico
# (< `VCM_MICROCITIC_HIGH`), que es el contexto para el que se validó
# (diferencial de una microcitosis, no un cribado general).
MENTZER_LOW = 13.0

# Clasificación de VCM: Regalla DKR, Killeen RB. "Anemia." En: StatPearls
# [Internet]. StatPearls Publishing; 2026. NBK499994. Microcítica < 80 fL,
# normocítica 80-100 fL, macrocítica > 100 fL.
VCM_MICROCITIC_HIGH = 80.0
VCM_MACROCITIC_LOW = 100.0

# Linfocitosis sostenida: umbral diagnóstico LLC/MBL de iwCLL 2018 (Hallek
# M et al. Blood. 2018;131(25):2745-2760), adoptado por la guía europea de
# referencia ESMO (Eichhorst B, Robak T, Montserrat E, Ghia P, et al. Ann
# Oncol. 2021;32(1):23-33. doi:10.1016/j.annonc.2020.09.019) y coincidente
# con la guía de derivación NHS Scotland — texto completo y limitaciones
# (Analitix no distingue clonal/reactivo ni registra síntomas) en
# `data/descripciones/aviso_linfocitosis.txt`. Investigado 2026-09-21.
LYMPHOCYTOSIS_HIGH = 5.0


def _x10e3_ul(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de un recuento (neutrófilos/linfocitos/monocitos/
    plaquetas) si su unidad empieza por x10³ (numéricamente igual a
    10⁹/L). Mismo criterio que `hepatic_risk._plaquetes_1e9_l`: se acepta
    el prefijo en vez de la cadena completa porque la extracción de alguna
    plantilla trunca el sufijo de unidad."""
    if row is None or not is_count_1e9_l(row.get("unit")):
        return None
    return row.get("value_num")


def _x10e6_ul(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de los hematíes si su unidad empieza por x10⁶ (millones
    por µL, la unidad del índice de Mentzer)."""
    if row is None or not is_count_1e12_l(row.get("unit")):
        return None
    return row.get("value_num")


def _fl(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico del VCM/VPM si su unidad es fL."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if unit != "fl":
        return None
    return row.get("value_num")


def _percent(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico del RDW si su unidad es %."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().replace(" ", "")
    if unit != "%":
        return None
    return row.get("value_num")


def nlr(neutrofils: Optional[float], limfocits: Optional[float]) -> Optional[float]:
    """NLR: neutrófilos absolutos ÷ linfocitos absolutos."""
    if neutrofils is None or limfocits is None or limfocits == 0:
        return None
    return neutrofils / limfocits


def plr(plaquetes: Optional[float], limfocits: Optional[float]) -> Optional[float]:
    """PLR: plaquetas ÷ linfocitos absolutos."""
    if plaquetes is None or limfocits is None or limfocits == 0:
        return None
    return plaquetes / limfocits


def lmr(limfocits: Optional[float], monocits: Optional[float]) -> Optional[float]:
    """LMR: linfocitos absolutos ÷ monocitos absolutos."""
    if limfocits is None or monocits is None or monocits == 0:
        return None
    return limfocits / monocits


def mentzer_index(vcm: Optional[float], hematies: Optional[float]) -> Optional[float]:
    """Índice de Mentzer: VCM (fL) ÷ hematíes (millones/µL). Cálculo puro,
    sin comprobar si el VCM es microcítico — esa comprobación (el índice
    solo tiene sentido clínico en ese contexto) la hacen
    `get_hemogram_index_series`/`get_latest_hemogram_summary`."""
    if vcm is None or hematies is None or hematies == 0:
        return None
    return vcm / hematies


def vcm_category(vcm: Optional[float]) -> Optional[str]:
    """Categoría de VCM: "microcitica"/"normocitica"/"macrocitica"."""
    if vcm is None:
        return None
    if vcm < VCM_MICROCITIC_HIGH:
        return "microcitica"
    if vcm > VCM_MACROCITIC_LOW:
        return "macrocitica"
    return "normocitica"


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


def get_hemogram_index_series(con, patient_id: int) -> dict[str, list[dict[str, Any]]]:
    """Serie temporal (una fecha = un informe) de los índices de hemograma
    calculables a partir de lo ya almacenado, en el mismo formato que
    `repository.get_series`. Devuelve solo las claves de índice que tengan
    al menos un punto calculable — el índice de Mentzer no aparecerá para
    fechas en las que el VCM no sea microcítico."""
    neu_by_date = get_merged_series(con, NEUTROFILS_IDS, patient_id)
    lim_by_date = get_merged_series(con, LIMFOCITS_IDS, patient_id)
    mon_by_date = get_merged_series(con, MONOCITS_IDS, patient_id)
    plq_by_date = get_merged_series(con, PLAQUETES_IDS, patient_id)
    vcm_by_date = get_merged_series(con, VCM_IDS, patient_id)
    hem_by_date = get_merged_series(con, HEMATIES_IDS, patient_id)

    series: dict[str, list[dict[str, Any]]] = {
        "idx_nlr": [], "idx_plr": [], "idx_lmr": [], "idx_mentzer": [],
    }
    fechas = sorted(
        set(neu_by_date) | set(lim_by_date) | set(mon_by_date)
        | set(plq_by_date) | set(vcm_by_date) | set(hem_by_date)
    )
    for fecha in fechas:
        neutrofils = _x10e3_ul(neu_by_date.get(fecha))
        limfocits = _x10e3_ul(lim_by_date.get(fecha))
        monocits = _x10e3_ul(mon_by_date.get(fecha))
        plaquetes = _x10e3_ul(plq_by_date.get(fecha))
        vcm = _fl(vcm_by_date.get(fecha))
        hematies = _x10e6_ul(hem_by_date.get(fecha))

        n = nlr(neutrofils, limfocits)
        if n is not None:
            series["idx_nlr"].append(_index_point(fecha, n, None, NLR_HIGH, "NLR (neutrófilos/linfocitos)"))
        p = plr(plaquetes, limfocits)
        if p is not None:
            series["idx_plr"].append(_index_point(fecha, p, None, PLR_HIGH, "PLR (plaquetas/linfocitos)"))
        m = lmr(limfocits, monocits)
        if m is not None:
            series["idx_lmr"].append(_index_point(fecha, m, None, None, "LMR (linfocitos/monocitos)"))
        if vcm is not None and vcm < VCM_MICROCITIC_HIGH:
            mz = mentzer_index(vcm, hematies)
            if mz is not None:
                series["idx_mentzer"].append(
                    _index_point(fecha, mz, MENTZER_LOW, None, "Índice de Mentzer")
                )

    return {key: points for key, points in series.items() if points}


# Etiqueta legible de cada índice sintético, para la lista de selección de
# la pestaña "🩸 Hemograma" (gui.py). El texto largo con las citas
# completas y la explicación en lenguaje llano vive en
# `data/descripciones/idx_*.txt` (mismo patrón que el resto de módulos de
# riesgo clínico).
INDEX_LABELS = {
    "idx_nlr": "NLR (neutrófilos/linfocitos)",
    "idx_plr": "PLR (plaquetas/linfocitos)",
    "idx_lmr": "LMR (linfocitos/monocitos)",
    "idx_mentzer": "Índice de Mentzer",
}


def get_latest_hemogram_summary(con, patient_id: int) -> Optional[dict[str, Any]]:
    """Último informe con hemograma disponible (al menos VCM), con los
    índices calculables ese mismo día y la categoría de VCM/RDW para la
    orientación de anemia en texto. `None` si el paciente no tiene ningún
    VCM en fL guardado."""
    vcm_by_date = get_merged_series(con, VCM_IDS, patient_id)
    fechas_vcm = sorted(f for f, row in vcm_by_date.items() if _fl(row) is not None)
    if not fechas_vcm:
        return None
    fecha = fechas_vcm[-1]

    neu_by_date = get_merged_series(con, NEUTROFILS_IDS, patient_id)
    lim_by_date = get_merged_series(con, LIMFOCITS_IDS, patient_id)
    mon_by_date = get_merged_series(con, MONOCITS_IDS, patient_id)
    plq_by_date = get_merged_series(con, PLAQUETES_IDS, patient_id)
    hem_by_date = get_merged_series(con, HEMATIES_IDS, patient_id)
    rdw_by_date = get_merged_series(con, RDW_IDS, patient_id)

    neutrofils = _x10e3_ul(neu_by_date.get(fecha))
    limfocits = _x10e3_ul(lim_by_date.get(fecha))
    monocits = _x10e3_ul(mon_by_date.get(fecha))
    plaquetes = _x10e3_ul(plq_by_date.get(fecha))
    vcm = _fl(vcm_by_date.get(fecha))
    hematies = _x10e6_ul(hem_by_date.get(fecha))
    rdw = _percent(rdw_by_date.get(fecha))
    vcm_cat = vcm_category(vcm)
    mentzer = mentzer_index(vcm, hematies) if vcm is not None and vcm < VCM_MICROCITIC_HIGH else None

    return {
        "fecha": fecha,
        "vcm": vcm,
        "vcm_categoria": vcm_cat,
        "rdw": rdw,
        "hematies": hematies,
        "nlr": nlr(neutrofils, limfocits),
        "plr": plr(plaquetes, limfocits),
        "lmr": lmr(limfocits, monocits),
        "mentzer": mentzer,
    }


def get_sustained_lymphocytosis_alert(con, patient_id: int) -> Optional[dict[str, Any]]:
    """Fechas con linfocitos > `LYMPHOCYTOSIS_HIGH` (x10³/µL, equivalente a
    x10⁹/L), si hay al menos dos — "sostenido" en el sentido de las guías
    citadas junto a `LYMPHOCYTOSIS_HIGH`, no un valor aislado. `None` si no
    hay ninguna o solo una."""
    lim_by_date = get_merged_series(con, LIMFOCITS_IDS, patient_id)
    fechas_altas = sorted(
        fecha for fecha, row in lim_by_date.items()
        if (valor := _x10e3_ul(row)) is not None and valor > LYMPHOCYTOSIS_HIGH
    )
    if len(fechas_altas) < 2:
        return None
    return {
        "fechas": fechas_altas,
        "ultimo_valor": _x10e3_ul(lim_by_date[fechas_altas[-1]]),
    }
