# ---------------------------------------------------------------------------
# Script: inflammation_risk.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-18
# ---------------------------------------------------------------------------
"""Inflamación (PCR + VSG) orientativa.

A diferencia de `lipid_risk.py`/`hepatic_risk.py`/`renal_risk.py`/
`hemogram_risk.py`/`iron_risk.py`, este módulo **no calcula ningún índice
combinado**: no existe ningún score PCR+VSG validado en la literatura,
porque las dos pruebas tienen una cinética demasiado distinta para
combinarlas con sentido fisiológico. En su lugar se muestran las dos
series por separado (cada una ya clasificada contra el rango de
referencia de su propio informe, igual que en Evolución/Comparativa) y se
señala cuándo discrepan entre sí, precisamente porque esa discordancia es
en sí misma informativa.

**Cinética de cada marcador** (nunca de memoria): la PCR la produce el
hígado en respuesta directa a citocinas, sube en horas (inicio en 6-24h,
pico a las 24-72h) y baja con una semivida de ~19h, normalizándose en
3-7 días tras resolverse la causa; la VSG depende del fibrinógeno (un
reactante de fase aguda "lento") y de un fenómeno físico indirecto
(agregación de hematíes), por lo que sube y baja mucho más despacio,
permaneciendo alta semanas después de resuelto el proceso. Fuente: Lapić
I, Padoan A, Bozzato D, Plebani M. "Erythrocyte Sedimentation Rate and
C-Reactive Protein in Acute Inflammation: Meta-Analysis of Diagnostic
Accuracy Studies." Am J Clin Pathol. 2020;153(1):14-29.
doi:10.1093/ajcp/aqz142. Corroborado por el College of American
Pathologists, "C-Reactive Protein and Erythrocyte Sedimentation Rate Test
Use" (documento de práctica clínica, sin fecha de publicación indicada en
el propio PDF): https://documents.cap.org/documents/C-ReactiveProteinandErythrocyteSedimentationRateTestUse.pdf

Como el resto de la app, esto es **apoyo informativo y de seguimiento,
nunca un diagnóstico**; cada valor se clasifica contra el rango de
referencia que trae su propio informe (`ref_low`/`ref_high`/`flag_calc`
ya calculados al importar, igual que cualquier otro parámetro de
Evolución/Comparativa), no contra un umbral fijo inventado por Analitix.
"""
from __future__ import annotations

from typing import Any, Optional

from analitix.repository import get_merged_series

PCR_IDS = (
    "proteina_c_reactiva_serum", "proteina_c_reactiva",
    # PCR sérica en mg/L (Synlab, HUGTIP): se convierte a mg/dL (÷10, exacto).
    "proteina_c_reactiva_en_suero", "srm_proteina_c_reactiva_c_massa",
)
# `pla_proteina_c_reactiva_c_massa` (mg/L, visto una sola vez en los 39 PDF
# reales del proyecto) se deja fuera deliberadamente: es una unidad
# distinta (mg/L, no mg/dL) que además solo aparece con ese nombre en un
# contexto puntual, no confirmado como el mismo tipo de determinación
# rutinaria que las otras dos variantes — mezclarla sin verificarlo a
# fondo podría fusionar magnitudes no comparables sin un factor de
# conversión fiable.
VSG_IDS = ("vsg_velocitat_de_sedimentacio_globular", "vsg_velocitat_de_sedimentacio_globular_sang")


def _mg_dl(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de la PCR si su unidad es mg/dL (mismo criterio que
    `lipid_risk._mg_dl`)."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if unit not in ("mg/dl", "mgdl"):
        return None
    return row.get("value_num")


def _as_mg_dl(row: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """La fila de PCR en mg/dL: tal cual si ya lo está; si viene en mg/L, una
    copia con valor y rango divididos entre 10 (1 mg/dL = 10 mg/L), para no
    mezclar en el mismo gráfico magnitudes de escala distinta. `flag_calc` no
    cambia: se calculó con valor y rango en la misma unidad del informe."""
    if row is None:
        return None
    if _mg_dl(row) is not None:
        return row
    if (row.get("unit") or "").strip().lower().replace(" ", "") != "mg/l" or row.get("value_num") is None:
        return None
    converted = dict(row, unit="mg/dL", value_num=row["value_num"] / 10)
    for key in ("ref_low", "ref_high"):
        if converted.get(key) is not None:
            converted[key] = converted[key] / 10
    return converted


def _mm_h(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de la VSG si su unidad es mm/h."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if unit != "mm/h":
        return None
    return row.get("value_num")


def get_inflammation_series(con, patient_id: int) -> dict[str, list[dict[str, Any]]]:
    """Series de PCR y VSG, ya fusionadas entre variantes de `canonical_id`
    (`repository.get_merged_series`) y ordenadas por fecha, con la misma
    forma que `repository.get_series` (incluido `flag_calc`, calculado
    contra el rango de referencia de cada informe, no un umbral propio de
    este módulo). Ninguna de las dos es un índice sintético: son las series
    reales de cada parámetro, iguales a las que ya se ven en Evolución."""
    pcr_by_date = get_merged_series(con, PCR_IDS, patient_id)
    vsg_by_date = get_merged_series(con, VSG_IDS, patient_id)

    pcr = sorted(
        (row for row in map(_as_mg_dl, pcr_by_date.values()) if row is not None), key=lambda r: r["fecha"]
    )
    vsg = sorted(
        (row for row in vsg_by_date.values() if _mm_h(row) is not None), key=lambda r: r["fecha"]
    )
    series = {}
    if pcr:
        series["pcr"] = pcr
    if vsg:
        series["vsg"] = vsg
    return series


def get_latest_inflammation_summary(con, patient_id: int) -> Optional[dict[str, Any]]:
    """Último valor disponible de PCR y de VSG (no necesariamente del mismo
    informe: cada uno puede haberse pedido en fechas distintas), con su
    clasificación ya calculada por el propio informe, y una nota si los dos
    últimos valores discrepan entre sí (uno fuera de rango y el otro no).
    `None` si el paciente no tiene ninguno de los dos guardado."""
    series = get_inflammation_series(con, patient_id)
    if not series:
        return None

    pcr_last = series["pcr"][-1] if series.get("pcr") else None
    vsg_last = series["vsg"][-1] if series.get("vsg") else None

    discordancia = None
    if pcr_last is not None and vsg_last is not None:
        pcr_alterada = pcr_last["flag_calc"] in ("alto", "bajo")
        vsg_alterada = vsg_last["flag_calc"] in ("alto", "bajo")
        if pcr_alterada != vsg_alterada:
            discordancia = (
                "PCR y VSG no coinciden en su último valor: "
                f"{'PCR fuera de rango, VSG normal' if pcr_alterada else 'VSG fuera de rango, PCR normal'}"
                " — coherente con su cinética distinta, coméntalo con tu médico si te preocupa."
            )

    return {
        "pcr": pcr_last,
        "vsg": vsg_last,
        "discordancia": discordancia,
    }
