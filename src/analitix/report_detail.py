# ---------------------------------------------------------------------------
# Script: report_detail.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-11-15
# ---------------------------------------------------------------------------
"""Detalle de analítica individual cotejable y comparativa delta con la anterior.

Permite:
1. Explorar una analítica individual estructurada por sección y en orden
   fiel al PDF original para cotejar los datos extraídos contra el documento.
2. Comparar los parámetros con el informe cronológicamente anterior del mismo
   paciente, calculando diferencias absolutas, porcentuales, flechas de tendencia
   y alertas de cambio de rango (entradas, salidas o persistencia).
3. Agrupar y formatear los datos para visualización en GUI (Treeview) y exportación
   en documento único (PDF / Excel / CSV).
"""

from __future__ import annotations

import unicodedata
from typing import Any

ARROW_UP = "↑"
ARROW_DOWN = "↓"
ARROW_STABLE = "≈"

ALERT_NORMAL = ""
ALERT_ENTERED_HIGH = "🔴 Entra en alto"
ALERT_ENTERED_LOW = "🔵 Entra en bajo"
ALERT_ENTERED_OUT = "⚠ Entra fuera de rango"
ALERT_NORMALIZED = "🟢 Normalizado"
ALERT_STILL_HIGH = "▲ Sigue alto"
ALERT_STILL_LOW = "▼ Sigue bajo"
ALERT_STILL_OUT = "⚠ Sigue fuera de rango"
ALERT_CHANGED = "⚡ Cambio de límite"


def normalize_name_key(name: str | None) -> str:
    """Clave normalizada en minúsculas y sin acentos para emparejar parámetros."""
    if not name:
        return ""
    norm = unicodedata.normalize("NFKD", name).encode("ASCII", "ignore").decode("utf-8")
    return " ".join(norm.strip().lower().split())


NON_ANALYTICAL_PATTERNS = (
    "no és procedent",
    "no es procedent",
    "no procedent",
    "no procede",
    "no realitzat",
    "no realitzada",
    "no realizado",
    "no realizada",
    "anul·lat",
    "anul.lat",
    "anulado",
    "anulada",
    "dnr",
    "dnt",
)

COMMENT_NAME_PATTERNS = (
    "comentari",
    "comentario",
    "observaci",
    "interpretaci",
    "conclusi",
)


def is_comment_or_note(name: str | None, value_num: float | None = None) -> bool:
    """True si el parámetro corresponde a un comentario, nota u observación no cuantitativa.

    Se excluye cualquier parámetro cuyo nombre contenga un patrón de comentario/observación,
    independientemente de si tiene valor numérico: 'Comentari X' nunca es un parámetro
    analítico cuantitativo, aunque el parser haya asignado un valor_num por error.
    """
    if not name:
        return False
    norm = normalize_name_key(name)
    return any(p in norm for p in COMMENT_NAME_PATTERNS)


def is_non_analytical_value(val: Any) -> bool:
    """True si el valor indica explícitamente que la prueba no se realizó o no procede."""
    if val is None:
        return True
    s = str(val).strip().lower()
    if not s or s in ("—", "-", "nan"):
        return True
    return any(p in s for p in NON_ANALYTICAL_PATTERNS)


def format_status(flag_calc: str | None, flag_pdf: str | None) -> str:
    """Etiqueta textual legible para el estado de rango de un parámetro."""
    flag = (flag_calc or "").strip().lower()
    pdf = (flag_pdf or "").strip().upper()
    if flag == "alto" or pdf in ("*", "H", ">", "HIGH", "ALT"):
        return "↑ Alto"
    if flag == "bajo" or pdf in ("L", "<", "LOW", "BAIX"):
        return "↓ Bajo"
    if flag in ("alto", "bajo") or (
        pdf and pdf not in ("NORMAL", "OK", "NEG", "NEGATIVO", "NEGATIU", "")
    ):
        return "⚠ Fuera de rango"
    return "Normal"


def diff_level(diff_pct: float | None) -> str:
    """Nivel de variación porcentual: 'high' (>=25%), 'moderate' (10-25%), 'low' (<10%), 'none'."""
    if diff_pct is None:
        return "none"
    pct = abs(diff_pct)
    if pct >= 25.0:
        return "high"
    if pct >= 10.0:
        return "moderate"
    return "low"


def format_diff(diff_num: float | None, diff_pct: float | None) -> str:
    """Formatea la variación numérica y porcentual: '+0.40 (+2.8%)' o '—'."""
    if diff_num is None:
        return "—"
    sign = "+" if diff_num > 0 else ""
    # Formatear el número sin ceros decimales innecesarios (hasta 3 decimales)
    num_str = f"{sign}{diff_num:.3f}".rstrip("0").rstrip(".")
    if num_str in ("+0", "-0", ""):
        num_str = "0"
    if diff_pct is not None:
        pct_sign = "+" if diff_pct > 0 else ""
        return f"{num_str} ({pct_sign}{diff_pct:.1f}%)"
    return num_str


def match_and_compare_results(
    current_results: list[dict[str, Any]],
    previous_results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Empareja los resultados del informe actual con los del informe anterior y calcula deltas.

    Preserva el orden exacto de los resultados del informe actual (`current_results`).
    Si no hay informe anterior, devuelve las filas actuales con los campos de variación en blanco.
    """
    # Mapeos del informe anterior para emparejamiento
    prev_by_canonical: dict[str, list[dict[str, Any]]] = {}
    prev_by_name: dict[str, list[dict[str, Any]]] = {}

    if previous_results:
        for r in previous_results:
            cid = r.get("canonical_id")
            if cid:
                prev_by_canonical.setdefault(cid, []).append(r)
            norm_name = normalize_name_key(r.get("raw_name"))
            if norm_name:
                prev_by_name.setdefault(norm_name, []).append(r)

    # Registro de elementos previos ya emparejados (por id en results) para no duplicar emparejamientos
    matched_prev_ids: set[int] = set()

    compared_rows: list[dict[str, Any]] = []

    for curr in current_results:
        cid = curr.get("canonical_id")
        norm_name = normalize_name_key(curr.get("raw_name"))
        prev_match: dict[str, Any] | None = None

        # 1. Intentar emparejar por canonical_id
        if cid and cid in prev_by_canonical:
            for candidate in prev_by_canonical[cid]:
                cand_id = candidate.get("id")
                if cand_id not in matched_prev_ids:
                    prev_match = candidate
                    if cand_id is not None:
                        matched_prev_ids.add(cand_id)
                    break

        # 2. Respaldo: emparejar por nombre normalizado
        if prev_match is None and norm_name and norm_name in prev_by_name:
            for candidate in prev_by_name[norm_name]:
                cand_id = candidate.get("id")
                if cand_id not in matched_prev_ids:
                    prev_match = candidate
                    if cand_id is not None:
                        matched_prev_ids.add(cand_id)
                    break

        # Extracción de valores actuales
        curr_val_raw = curr.get("value_raw") or ""
        curr_val_num = curr.get("value_num")

        # Omitir comentarios, notas u observaciones de texto que no son parámetros analíticos
        if is_comment_or_note(curr.get("raw_name"), curr_val_num):
            continue

        # Comprobar si el resultado no es analítico en el informe actual y en el anterior
        curr_is_empty = is_non_analytical_value(curr_val_raw) and curr_val_num is None
        prev_is_empty = prev_match is None or (
            is_non_analytical_value(prev_match.get("value_raw"))
            and prev_match.get("value_num") is None
        )

        # Si ni el informe actual ni el anterior tienen un valor analítico real, omitir el parámetro
        if curr_is_empty and prev_is_empty:
            continue

        curr_flag_calc = curr.get("flag_calc")
        curr_flag_pdf = curr.get("flag_pdf")
        curr_status = format_status(curr_flag_calc, curr_flag_pdf)

        ref_text = curr.get("ref_text")
        if not ref_text:
            low, high = curr.get("ref_low"), curr.get("ref_high")
            if low is not None and high is not None:
                ref_text = f"{low:g} – {high:g}"
            elif low is not None:
                ref_text = f"≥ {low:g}"
            elif high is not None:
                ref_text = f"≤ {high:g}"
            else:
                ref_text = ""

        row: dict[str, Any] = {
            "id": curr.get("id"),
            "section": curr.get("section") or "General",
            "test_group": curr.get("test_group"),
            "raw_name": curr.get("raw_name") or "",
            "canonical_id": cid,
            "value_raw": curr_val_raw,
            "value_num": curr_val_num,
            "unit": curr.get("unit") or "",
            "ref_text": ref_text,
            "flag_calc": curr_flag_calc,
            "flag_pdf": curr_flag_pdf,
            "status": curr_status,
            "prev_result": prev_match,
            "prev_value_raw": prev_match.get("value_raw") if prev_match else "",
            "prev_value_num": prev_match.get("value_num") if prev_match else None,
            "prev_status": format_status(prev_match.get("flag_calc"), prev_match.get("flag_pdf"))
            if prev_match
            else "",
            "diff_num": None,
            "diff_pct": None,
            "diff_level": "none",
            "trend": "",
            "range_alert": ALERT_NORMAL,
        }

        # Cálculos de variación si existe valor previo
        if prev_match:
            prev_num = prev_match.get("value_num")
            if curr_val_num is not None and prev_num is not None:
                d_num = round(curr_val_num - prev_num, 4)
                row["diff_num"] = d_num
                if prev_num != 0:
                    pct = round((d_num / abs(prev_num)) * 100, 1)
                    row["diff_pct"] = pct
                    row["diff_level"] = diff_level(pct)

                if d_num > 0.00001:
                    row["trend"] = ARROW_UP
                elif d_num < -0.00001:
                    row["trend"] = ARROW_DOWN
                else:
                    row["trend"] = ARROW_STABLE

            # Alertas de cambio de rango
            curr_flag = (curr_flag_calc or "").strip().lower()
            prev_flag = (prev_match.get("flag_calc") or "").strip().lower()

            # Banderas PDF como respaldo
            curr_pdf_out = bool(curr_flag_pdf)
            prev_pdf_out = bool(prev_match.get("flag_pdf"))

            curr_is_out = curr_flag in ("alto", "bajo") or curr_pdf_out
            prev_is_out = prev_flag in ("alto", "bajo") or prev_pdf_out

            if not prev_is_out and curr_is_out:
                if curr_flag == "alto":
                    row["range_alert"] = ALERT_ENTERED_HIGH
                elif curr_flag == "bajo":
                    row["range_alert"] = ALERT_ENTERED_LOW
                else:
                    row["range_alert"] = ALERT_ENTERED_OUT
            elif prev_is_out and not curr_is_out:
                row["range_alert"] = ALERT_NORMALIZED
            elif prev_is_out and curr_is_out:
                if curr_flag == "alto" and prev_flag == "alto":
                    row["range_alert"] = ALERT_STILL_HIGH
                elif curr_flag == "bajo" and prev_flag == "bajo":
                    row["range_alert"] = ALERT_STILL_LOW
                elif curr_flag and prev_flag and curr_flag != prev_flag:
                    row["range_alert"] = ALERT_CHANGED
                else:
                    row["range_alert"] = ALERT_STILL_OUT

        compared_rows.append(row)

    return compared_rows


def group_results_by_section(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Agrupa las filas comparadas por sección conservando el orden de aparición original."""
    sections: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        sec = r.get("section") or "General"
        sections.setdefault(sec, []).append(r)
    return sections


def build_comparison_summary(comparison_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Genera un resumen estadístico de la analítica y sus variaciones."""
    total = len(comparison_rows)
    fuera_rango = sum(
        1 for r in comparison_rows if r.get("status") in ("↑ Alto", "↓ Bajo", "⚠ Fuera de rango")
    )
    normalizados = sum(1 for r in comparison_rows if r.get("range_alert") == ALERT_NORMALIZED)
    nuevos_fuera = sum(
        1
        for r in comparison_rows
        if r.get("range_alert") in (ALERT_ENTERED_HIGH, ALERT_ENTERED_LOW, ALERT_ENTERED_OUT)
    )
    al_alza = sum(1 for r in comparison_rows if r.get("trend") == ARROW_UP)
    a_la_baja = sum(1 for r in comparison_rows if r.get("trend") == ARROW_DOWN)
    estables = sum(1 for r in comparison_rows if r.get("trend") == ARROW_STABLE)

    return {
        "total": total,
        "fuera_rango": fuera_rango,
        "normalizados": normalizados,
        "nuevos_fuera": nuevos_fuera,
        "al_alza": al_alza,
        "a_la_baja": a_la_baja,
        "estables": estables,
    }
