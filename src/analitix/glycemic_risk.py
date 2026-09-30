# ---------------------------------------------------------------------------
# Script: glycemic_risk.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-21
# ---------------------------------------------------------------------------
"""Glucosa media estimada (eAG) a partir de la HbA1c.

Fórmula/umbrales citados junto a la constante que los usa (nunca de
memoria, mismo criterio que el resto de módulos `*_risk.py`) — ver
`docs/referencias_medicas/referencias_hierro_glucosa.md` (sección
"Metabolismo glucídico") para el detalle completo con DOI/PMID. Como el
resto de la app, esto es **apoyo informativo y de seguimiento, nunca un
diagnóstico**, con más motivo aquí porque los puntos de corte de HbA1c son
umbrales diagnósticos oficiales de diabetes, no solo orientativos.

La HbA1c debe venir en % — si un resultado viene en otra unidad se
descarta ese punto (algún informe real del proyecto la trae en mmol/mol,
método IFCC, bajo un `canonical_id` distinto —
`hb_glicosilada_hba1c_ifcc_sang` — sin conversión implementada por baja
densidad de datos reales: 1 solo informe de 39).

**Limitación importante, a mostrar siempre de forma visible**: la fórmula
(y la propia HbA1c) asume una vida media eritrocitaria normal. Da valores
**falsamente bajos** en anemia hemolítica, pérdida de sangre o embarazo, y
**falsamente altos** en ferropenia, déficit de B12/fólico o alcoholismo
crónico — hay un caso clínico real de HbA1c falsamente baja enmascarando
diabetes real en un paciente con hemoglobinopatía (PMC12906350).

`GLUCOSA_IDS`/`get_glucose_series` (añadido 2026-09-21) no calculan nada
nuevo: exponen la serie real de glucosa (mg/dL) para el gráfico combinado
Glucosa + eAG de la idea §6 punto 2 ("Gráficos combinados de dos
parámetros, sin cálculo nuevo"), mismo patrón que
`inflammation_risk.get_inflammation_series`.
"""
from __future__ import annotations

from typing import Any, Optional

from analitix.pdf_parser import compute_flag
from analitix.repository import get_merged_series

HBA1C_IDS = ("hb_glicosilada_hba1c_sang",)
GLUCOSA_IDS = ("glucosa_serum", "glucosa")

# Nathan DM, Kuenen J, Borg R, Zheng H, Schoenfeld D, Heine RJ, for the
# A1c-Derived Average Glucose (ADAG) Study Group. "Translating the A1C
# Assay Into Estimated Average Glucose Values." Diabetes Care.
# 2008;31(8):1473-1478. doi:10.2337/dc08-0545. PMID: 18540046. Fórmula
# adoptada oficialmente por la ADA (calculadora eAG/A1C,
# https://professional.diabetes.org/glucose_calc). La regresión no varía
# significativamente por edad, sexo, tipo de diabetes, raza/etnia ni
# tabaquismo — no hace falta ningún dato demográfico adicional.
EAG_SLOPE = 28.7
EAG_INTERCEPT = -46.7

# Puntos de corte diagnósticos de la American Diabetes Association
# vigentes (International Expert Committee, adoptado 2009-2010 por su
# asociación con aparición de retinopatía). Requieren un HbA1c medido con
# método estandarizado IFCC/NGSP para uso diagnóstico formal — en
# Analitix son solo orientativos de seguimiento.
ADA_NORMAL_HIGH = 5.7
ADA_DIABETES_LOW = 6.5


def _pct(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de la HbA1c si su unidad es % (mismo criterio que
    `hemogram_risk._percent`)."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().replace(" ", "")
    if unit != "%":
        return None
    return row.get("value_num")


def _mg_dl(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de la glucosa si su unidad es mg/dL (mismo criterio
    que `lipid_risk._mg_dl`)."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if unit not in ("mg/dl", "mgdl"):
        return None
    return row.get("value_num")


def eag(hba1c: Optional[float]) -> Optional[float]:
    """Glucosa media estimada (mg/dL), fórmula ADAG."""
    if hba1c is None:
        return None
    return EAG_SLOPE * hba1c + EAG_INTERCEPT


def hba1c_category(hba1c: Optional[float]) -> Optional[str]:
    """Categoría diagnóstica ADA: "normal"/"prediabetes"/"diabetes"."""
    if hba1c is None:
        return None
    if hba1c < ADA_NORMAL_HIGH:
        return "normal"
    if hba1c < ADA_DIABETES_LOW:
        return "prediabetes"
    return "diabetes"


# Umbral de la serie eAG: traducción directa (misma fórmula ADAG) del
# corte diagnóstico de diabetes (HbA1c >= 6.5%), no un umbral nuevo.
EAG_HIGH = EAG_SLOPE * ADA_DIABETES_LOW + EAG_INTERCEPT


def _index_point(fecha: str, value: float, raw_name: str) -> dict[str, Any]:
    """Fila con la misma forma que `repository.get_series`, para reutilizar
    `charts.evolution_figure` sin cambios."""
    return {
        "fecha": fecha,
        "value_num": value,
        "unit": "",
        "ref_low": None,
        "ref_high": EAG_HIGH,
        "flag_calc": compute_flag(value, None, EAG_HIGH),
        "raw_name": raw_name,
    }


def get_glycemic_index_series(con, patient_id: int) -> dict[str, list[dict[str, Any]]]:
    """Serie temporal de eAG (glucosa media estimada), en el mismo formato
    que `repository.get_series`."""
    by_date = get_merged_series(con, HBA1C_IDS, patient_id)
    points = [
        _index_point(fecha, value, "Glucosa media estimada (eAG)")
        for fecha, row in sorted(by_date.items())
        if (value := eag(_pct(row))) is not None
    ]
    return {"idx_eag": points} if points else {}


INDEX_LABELS = {"idx_eag": "Glucosa media estimada (eAG)"}


def get_glucose_series(con, patient_id: int) -> list[dict[str, Any]]:
    """Serie real de glucosa (no un índice sintético), con la misma forma
    que `repository.get_series` — para el gráfico combinado
    Glucosa + eAG (idea §6, "Gráficos combinados de dos parámetros"),
    mismo patrón que `inflammation_risk.get_inflammation_series`."""
    by_date = get_merged_series(con, GLUCOSA_IDS, patient_id)
    return sorted((row for row in by_date.values() if _mg_dl(row) is not None), key=lambda r: r["fecha"])


def get_latest_glycemic_summary(con, patient_id: int) -> Optional[dict[str, Any]]:
    """Última HbA1c disponible, con su categoría ADA y la eAG derivada.
    `None` si el paciente no tiene ninguna HbA1c en % guardada."""
    by_date = get_merged_series(con, HBA1C_IDS, patient_id)
    fechas = sorted(f for f, row in by_date.items() if _pct(row) is not None)
    if not fechas:
        return None
    fecha = fechas[-1]
    hba1c = _pct(by_date[fecha])
    return {
        "fecha": fecha,
        "hba1c": hba1c,
        "categoria": hba1c_category(hba1c),
        "eag": eag(hba1c),
    }
