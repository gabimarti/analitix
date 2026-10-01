# ---------------------------------------------------------------------------
# Script: tyg_risk.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-10-01
# ---------------------------------------------------------------------------
"""Índice TyG (triglicéridos-glucosa): marcador indirecto de resistencia a
la insulina calculado solo con dos parámetros de una analítica rutinaria.

Apoyo informativo y de seguimiento, nunca un diagnóstico. Se muestra **solo
como tendencia, sin umbral**: los puntos de corte publicados (~8,5-8,8)
dependen de la población estudiada y ninguno está validado para la
población de los usuarios de Analitix. Fuentes y limitaciones:
`docs/referencias_medicas/referencias_hierro_glucosa.md` (sección "Índice
TyG").

Requiere glucosa y triglicéridos **del mismo informe** y en mg/dL (se
descarta el punto si falta alguno o viene en otra unidad). La fórmula se
validó con analíticas **en ayunas**; Analitix no registra si lo eran (la
extracción rutinaria suele serlo), así que se avisa en la ficha.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from analitix.glycemic_risk import GLUCOSA_IDS, _mg_dl
from analitix.lipid_risk import TG_IDS
from analitix.repository import get_merged_series

# Simental-Mendía LE, Rodríguez-Morán M, Guerrero-Romero F. Metab Syndr
# Relat Disord 2008;6(4):299-304. doi:10.1089/met.2008.0034. La fórmula
# salió mal impresa en el original; corregida en Eur J Pediatr
# 2020;179:1171, doi:10.1007/s00431-020-03644-1:
# TyG = ln[triglicéridos (mg/dL) × glucosa en ayunas (mg/dL) / 2].
def tyg(tg_mg_dl: Optional[float], glucosa_mg_dl: Optional[float]) -> Optional[float]:
    if not tg_mg_dl or not glucosa_mg_dl or tg_mg_dl <= 0 or glucosa_mg_dl <= 0:
        return None
    return math.log(tg_mg_dl * glucosa_mg_dl / 2)


INDEX_LABELS = {"idx_tyg": "Índice TyG (triglicéridos-glucosa)"}


def get_tyg_series(con, patient_id: int) -> dict[str, list[dict[str, Any]]]:
    """Serie del índice TyG con la forma de `repository.get_series`, sin
    rango de referencia (solo tendencia, ver docstring del módulo)."""
    tgs = get_merged_series(con, TG_IDS, patient_id)
    glucosas = get_merged_series(con, GLUCOSA_IDS, patient_id)
    points = []
    for fecha in sorted(tgs.keys() & glucosas.keys()):
        valor = tyg(_mg_dl(tgs[fecha]), _mg_dl(glucosas[fecha]))
        if valor is None:
            continue
        points.append({
            "fecha": fecha, "value_num": round(valor, 2), "unit": "", "ref_low": None, "ref_high": None,
            "flag_calc": None, "raw_name": INDEX_LABELS["idx_tyg"],
            # Mismo informe para los dos valores: su laboratorio vale para el punto.
            "lab": tgs[fecha].get("lab"),
        })
    return {"idx_tyg": points} if points else {}
