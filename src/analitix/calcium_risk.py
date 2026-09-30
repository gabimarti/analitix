# ---------------------------------------------------------------------------
# Script: calcium_risk.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-21
# ---------------------------------------------------------------------------
"""Calcio corregido por albúmina.

Fórmula citada junto a la constante/función que la usa (nunca de memoria,
mismo criterio que el resto de módulos `*_risk.py`) — ver
`docs/referencias_medicas/referencias_calcio.md` para el detalle completo
con DOI/PMID. Como el resto de la app, esto es **apoyo informativo y de
seguimiento, nunca un diagnóstico**.

El calcio debe venir en mg/dL y la albúmina en g/dL (no la fracción %
del proteinograma, magnitud distinta) — si un resultado viene en otra
unidad se descarta ese punto, mismo criterio que `lipid_risk._mg_dl`.
Verificado contra los 39 PDF reales del proyecto: ambas unidades
coinciden siempre con lo esperado.

**Limitación importante, a mostrar siempre de forma visible**: la fórmula
asume una relación lineal que se degrada en los extremos (albúmina < 2.0 o
> 5.5 g/dL); un estudio en UCI quirúrgica encontró que clasificaba mal el
calcio en el 38% de los casos (Byrnes CK, et al. Am J Surg.
2005;189(3):310-314) — con datos ambulatorios como los de Analitix el
riesgo es menor, pero debe advertirse igual.
"""
from __future__ import annotations

from typing import Any, Optional

from analitix.pdf_parser import compute_flag
from analitix.repository import get_merged_series

CALCI_IDS = ("calci_serum", "calci")
ALBUMINA_IDS = (
    "albumina_serum", "albumina_g_dl",
    # Albúmina sérica en g/L (Synlab, HUGTIP, Echevarne): se convierte a
    # g/dL (÷10, exacto) en `_g_dl`.
    "albumina_g_l", "srm_albumina_c_massa", "seroalbumina",
)

# Payne RB, Little AJ, Williams RB, Milner JR. "Interpretation of serum
# calcium in patients with abnormal serum proteins." Br Med J.
# 1973;4(5893):643-646. doi:10.1136/bmj.4.5893.643. Cerca del 40% del
# calcio sérico total va unido a la albúmina, así que con albúmina baja
# (cirrosis, malnutrición, síndrome nefrótico) el calcio total sale
# artificialmente bajo aunque el calcio libre (fisiológicamente activo)
# sea normal.
ALBUMINA_REFERENCIA = 4.0
FACTOR_PAYNE = 0.8


def _mg_dl(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico del calcio si su unidad es mg/dL (mismo criterio que
    `lipid_risk._mg_dl`)."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if unit not in ("mg/dl", "mgdl"):
        return None
    return row.get("value_num")


def _g_dl(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de la albúmina si su unidad es g/dL."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    value = row.get("value_num")
    if unit in ("g/l", "gl") and value is not None:
        return value / 10  # 1 g/dL = 10 g/L
    if unit not in ("g/dl", "gdl"):
        return None
    return value


def corrected_calcium(calci: Optional[float], albumina: Optional[float]) -> Optional[float]:
    """Calcio corregido (Payne et al. 1973): calcio medido + 0.8 × (4.0 −
    albúmina)."""
    if calci is None or albumina is None:
        return None
    return calci + FACTOR_PAYNE * (ALBUMINA_REFERENCIA - albumina)


def _index_point(fecha: str, value: float, ref_low, ref_high, raw_name: str) -> dict[str, Any]:
    """Fila con la misma forma que `repository.get_series`, para reutilizar
    `charts.evolution_figure` sin cambios."""
    return {
        "fecha": fecha,
        "value_num": value,
        "unit": "",
        "ref_low": ref_low,
        "ref_high": ref_high,
        "flag_calc": compute_flag(value, ref_low, ref_high),
        "raw_name": raw_name,
    }


def get_calcium_index_series(con, patient_id: int) -> dict[str, list[dict[str, Any]]]:
    """Serie temporal de calcio corregido, solo en las fechas donde el
    mismo informe trae calcio y albúmina. Se clasifica con el rango de
    referencia que el propio informe ya trae para el calcio total — sin
    inventar un umbral nuevo, tal y como recomendaba la investigación
    original."""
    calci_by_date = get_merged_series(con, CALCI_IDS, patient_id)
    alb_by_date = get_merged_series(con, ALBUMINA_IDS, patient_id)
    points = []
    for fecha in sorted(set(calci_by_date) & set(alb_by_date)):
        calci_row = calci_by_date[fecha]
        calci = _mg_dl(calci_row)
        albumina = _g_dl(alb_by_date[fecha])
        corregido = corrected_calcium(calci, albumina)
        if corregido is not None:
            points.append(
                _index_point(
                    fecha, corregido, calci_row.get("ref_low"), calci_row.get("ref_high"),
                    "Calcio corregido por albúmina",
                )
            )
    return {"idx_calcio_corregido": points} if points else {}


INDEX_LABELS = {"idx_calcio_corregido": "Calcio corregido por albúmina"}


def get_latest_calcium_summary(con, patient_id: int) -> Optional[dict[str, Any]]:
    """Último valor de calcio corregido disponible, con el calcio y la
    albúmina medidos ese día. `None` si el paciente no tiene ningún
    informe con ambos valores el mismo día."""
    series = get_calcium_index_series(con, patient_id)
    points = series.get("idx_calcio_corregido")
    if not points:
        return None
    last = points[-1]
    calci_by_date = get_merged_series(con, CALCI_IDS, patient_id)
    alb_by_date = get_merged_series(con, ALBUMINA_IDS, patient_id)
    return {
        "fecha": last["fecha"],
        "calcio_medido": _mg_dl(calci_by_date[last["fecha"]]),
        "albumina": _g_dl(alb_by_date[last["fecha"]]),
        "calcio_corregido": last["value_num"],
        "ref_low": last["ref_low"],
        "ref_high": last["ref_high"],
        "flag": last["flag_calc"],
    }
