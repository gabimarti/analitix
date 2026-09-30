# ---------------------------------------------------------------------------
# Script: thyroid_risk.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-21
# ---------------------------------------------------------------------------
"""TSH + T4 libre, gráfico combinado.

**Alcance deliberadamente reducido**: de toda la idea investigada en
`docs/referencias_medicas/referencias_tiroides_inflamacion_coagulacion.md`
§8, este módulo implementa **solo** la parte de menor riesgo señalada allí
mismo (punto 4 de la "Recomendación") — el gráfico combinado TSH+T4L, sin
ningún cálculo nuevo. **No** implementa la clasificación por cuadrante
(hipotiroidismo/hipertiroidismo manifiesto o subclínico): esa tabla es
literalmente el criterio clínico diagnóstico estándar, no una aproximación
de riesgo como Castelli I/II, y su umbral cambia con el embarazo (dato que
Analitix no registra) — se deja explícitamente para una fase futura si se
retoma la idea completa.

Cada serie se clasifica contra el `ref_low`/`ref_high` que el propio
informe ya trae (igual que `inflammation_risk.py`), nunca contra un
umbral fijo — el rango de TSH/T4L varía por laboratorio y método (American
Thyroid Association, *Clinical Thyroidology for the Public*, "TSH and
Free T4").

TSH debe venir en µUI/mL (visto en los PDF reales del proyecto como
"mcUI/mL" o "mcIU/mL", mismo valor con distinto orden de letras entre
plantillas) y T4 libre en ng/dL — si un resultado viene en otra unidad se
descarta ese punto, mismo criterio que `lipid_risk._mg_dl`.
"""
from __future__ import annotations

from typing import Any, Optional

from analitix.repository import get_merged_series

TSH_IDS = ("tirotropina_tsh_serum", "tirotropina_tsh")
T4L_IDS = ("tiroxina_lliure_t4l", "tiroxina_lliure_t4_lliure_serum")


def _uui_ml(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de la TSH si su unidad es µUI/mL (aceptando tanto
    "mcUI/mL" como "mcIU/mL", el mismo valor con las letras en distinto
    orden según la plantilla)."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    # mU/L (Synlab) es exactamente el mismo valor que µUI/mL.
    if unit not in ("mcui/ml", "mciu/ml", "mu/l", "mui/l"):
        return None
    return row.get("value_num")


def _ng_dl(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de la T4 libre si su unidad es ng/dL."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if unit not in ("ng/dl",):
        return None
    return row.get("value_num")


def get_thyroid_series(con, patient_id: int) -> dict[str, list[dict[str, Any]]]:
    """Series de TSH y T4 libre, ya fusionadas entre variantes de
    `canonical_id` y ordenadas por fecha, con la misma forma que
    `repository.get_series` (incluido `flag_calc`, calculado contra el
    rango de referencia de cada informe). Ninguna es un índice sintético:
    son las series reales de cada parámetro, iguales a las que ya se ven
    en Evolución."""
    tsh_by_date = get_merged_series(con, TSH_IDS, patient_id)
    t4l_by_date = get_merged_series(con, T4L_IDS, patient_id)

    tsh = sorted(
        (row for row in tsh_by_date.values() if _uui_ml(row) is not None), key=lambda r: r["fecha"]
    )
    t4l = sorted(
        (row for row in t4l_by_date.values() if _ng_dl(row) is not None), key=lambda r: r["fecha"]
    )
    series = {}
    if tsh:
        series["tsh"] = tsh
    if t4l:
        series["t4l"] = t4l
    return series


def get_latest_thyroid_summary(con, patient_id: int) -> Optional[dict[str, Any]]:
    """Último valor disponible de TSH y de T4L (no necesariamente del
    mismo informe), con su clasificación ya calculada por el propio
    informe. Sin ninguna nota de patrón/cuadrante — ver el aviso del
    módulo. `None` si el paciente no tiene ninguno de los dos guardado."""
    series = get_thyroid_series(con, patient_id)
    if not series:
        return None
    return {
        "tsh": series["tsh"][-1] if series.get("tsh") else None,
        "t4l": series["t4l"][-1] if series.get("t4l") else None,
    }
