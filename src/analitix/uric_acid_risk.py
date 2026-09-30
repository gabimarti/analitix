# ---------------------------------------------------------------------------
# Script: uric_acid_risk.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-18
# ---------------------------------------------------------------------------
"""Ácido úrico / hiperuricemia orientativa.

Fórmula/umbral citado junto a la constante que lo usa (nunca de memoria,
mismo criterio que `lipid_risk.py`/`hepatic_risk.py`/`renal_risk.py`/
`hemogram_risk.py`/`iron_risk.py`) — ver
`docs/referencias_medicas/referencias_ictus.md` para el detalle de por qué
NO se usa este parámetro como marcador de ictus (evidencia débil para
eso), y el propio módulo para el detalle de por qué sí se usa como
marcador de hiperuricemia (indicación distinta y bien establecida). Como
el resto de la app, esto es **apoyo informativo y de seguimiento, nunca un
diagnóstico**.

El ácido úrico debe venir en mg/dL — si un resultado viene en otra unidad
se descarta ese punto, mismo criterio que `lipid_risk._mg_dl`.

**Limitación importante, a mostrar siempre de forma visible**: un valor
alto es hiperuricemia, **no un diagnóstico de gota**. El diagnóstico real
de gota necesita confirmación por cristales de urato monosódico (o, como
mínimo, el patrón clínico de los criterios ACR/EULAR 2015), ninguno de
los cuales vive en una analítica de sangre — mostrar siempre como
"hiperuricemia", nunca como "gota" ni "riesgo de gota".
"""
from __future__ import annotations

from typing import Any, Optional

from analitix.pdf_parser import compute_flag
from analitix.repository import get_merged_series

URIC_ACID_IDS = ("urat_serum",)

# Umbral de hiperuricemia asintomática, unisex (Analitix no guarda el sexo
# del paciente; otras fuentes sí diferencian por sexo — p. ej. StatPearls
# usa >7 mg/dL hombres / >6 mg/dL mujeres — pero el de la ACR es el único
# umbral único y oficial encontrado que no exige conocer el sexo).
# American College of Rheumatology. "2020 American College of Rheumatology
# Guideline for the Management of Gout." Arthritis Care Res (Hoboken).
# 2020;72(6):744-760. doi:10.1002/acr.24180.
HYPERURICEMIA_HIGH = 6.8

# Objetivo de tratamiento en gota ya diagnosticada (mismo documento ACR
# 2020, y EULAR 2016) — solo relevante si el paciente ya está en
# tratamiento hipouricemiante; se muestra como referencia informativa
# junto al valor "alto", nunca como el umbral que decide "alto"/"normal".
URATE_LOWERING_TARGET = 6.0


def _mg_dl(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico del ácido úrico si su unidad es mg/dL (mismo criterio
    que `lipid_risk._mg_dl`)."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if unit not in ("mg/dl", "mgdl"):
        return None
    return row.get("value_num")


def _index_point(fecha: str, value: float, raw_name: str) -> dict[str, Any]:
    """Fila con la misma forma que `repository.get_series`, para reutilizar
    `charts.evolution_figure` sin cambios."""
    return {
        "fecha": fecha,
        "value_num": value,
        "unit": "",
        "ref_low": None,
        "ref_high": HYPERURICEMIA_HIGH,
        "flag_calc": compute_flag(value, None, HYPERURICEMIA_HIGH),
        "raw_name": raw_name,
    }


def get_uric_acid_series(con, patient_id: int) -> dict[str, list[dict[str, Any]]]:
    """Serie temporal de ácido úrico, en el mismo formato que
    `repository.get_series`, clasificada contra `HYPERURICEMIA_HIGH`."""
    by_date = get_merged_series(con, URIC_ACID_IDS, patient_id)
    points = [
        _index_point(fecha, value, "Ácido úrico")
        for fecha, row in sorted(by_date.items())
        if (value := _mg_dl(row)) is not None
    ]
    return {"idx_acido_urico": points} if points else {}


INDEX_LABELS = {"idx_acido_urico": "Ácido úrico"}


def get_latest_uric_acid_summary(con, patient_id: int) -> Optional[dict[str, Any]]:
    """Último valor de ácido úrico disponible, con su clasificación.
    `None` si el paciente no tiene ninguno guardado."""
    series = get_uric_acid_series(con, patient_id)
    points = series.get("idx_acido_urico")
    if not points:
        return None
    last = points[-1]
    return {
        "fecha": last["fecha"],
        "value": last["value_num"],
        "flag": last["flag_calc"],
    }
