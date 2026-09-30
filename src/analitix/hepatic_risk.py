# ---------------------------------------------------------------------------
# Script: hepatic_risk.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-18
# ---------------------------------------------------------------------------
"""Función e índices hepáticos orientativos.

Fórmulas y puntos de corte citados junto a la constante/función que los usa
(nunca de memoria, mismo criterio que `lipid_risk.py`) — ver
`docs/referencias_medicas/referencias_hepatico.md` para el detalle completo
con DOI/PMID. Como el resto de la app, esto es **apoyo informativo y de
seguimiento, nunca un diagnóstico**: ningún índice de este módulo sustituye
una prueba de imagen, una biopsia o la valoración de un hepatólogo.

AST/ALT deben venir en U/L (o UI/L, equivalente) y las plaquetas en
x10^3/µL (numéricamente igual a las 10⁹/L de las fórmulas) — si un
resultado viene en otra unidad se descarta ese punto en vez de calcular con
cifras no comparables, mismo criterio que `lipid_risk._mg_dl`.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from analitix.pdf_parser import compute_flag
from analitix.repository import get_merged_series, get_patient_birth_date
from analitix.textutils import is_count_1e9_l

AST_IDS = ("aspartat_aminotranferasa_ast_serum",)
ALT_IDS = ("alanina_aminotransferasa_alt_serum",)
PLAQUETES_IDS = ("plaquetes",)

# Ratio De Ritis: De Ritis F, Coltorti M, Giusti G, 1957 (Minerva Medica);
# cita verificada vía una revisión histórica (PMC, 2024):
# https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11319523/. Solo se marca
# "alto" (⚠) por encima de 2 (patrón sugestivo de daño hepático alcohólico):
# un ratio < 1 es un hallazgo común (hígado graso, hepatitis viral aguda),
# no una alarma por sí solo, así que no se trata como "fuera de rango" en
# los gráficos/listas — ver `idx_de_ritis.txt` para la interpretación
# completa de ambos extremos.
DE_RITIS_HIGH = 2.0

# APRI: Wai CT, Greenson JK, Fontana RJ, et al. Hepatology.
# 2003;38(2):518-526. doi:10.1053/jhep.2003.50346. PMID 12883497.
# https://pubmed.ncbi.nlm.nih.gov/12883497/. AST-ULN = límite superior
# normal de AST, valor de referencia típico de laboratorio (no un dato por
# paciente). Puntos de corte "clásicos" del estudio original, los más
# citados en revisiones posteriores — a diferencia de FIB-4, no hay un
# único conjunto "vigente" (ver `idx_apri.txt`/`referencias_hepatico.md`
# para la variabilidad según etiología/objetivo).
APRI_AST_ULN = 40.0
APRI_HIGH = 1.5

# FIB-4: Sterling RK et al. Hepatology. 2006;43(6):1317-1325.
# doi:10.1002/hep.21178. PMID 16729309 (validación original, VIH/VHC; da
# 1.45/3.25). Se usan en su lugar los puntos de corte de la guía AASLD 2023
# (más recientes, pensados para cribado general de hígado graso en vez de
# una coinfección específica): Rinella ME et al. Hepatology.
# 2023;77(5):1797-1835. doi:10.1097/HEP.0000000000000323.
# https://pmc.ncbi.nlm.nih.gov/articles/PMC10735173/. Los dos conjuntos de
# puntos de corte no son intercambiables — ver `idx_fib4.txt` para el
# detalle de por qué se elige AASLD 2023 aquí.
FIB4_HIGH = 2.67


def _u_l(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de `row` si su unidad es U/L o UI/L (equivalentes;
    alguna plantilla añade una nota de temperatura, p. ej. "UI/l 37C")."""
    if row is None:
        return None
    unit = (row.get("unit") or "").strip().lower().replace(" ", "")
    if not (unit.startswith("u/l") or unit.startswith("ui/l")):
        return None
    return row.get("value_num")


def _plaquetes_1e9_l(row: Optional[dict[str, Any]]) -> Optional[float]:
    """Valor numérico de `row` (plaquetas) si su unidad es x10^3 por
    microlitro (numéricamente igual a 10⁹/L, la unidad de las fórmulas). Se
    acepta cualquier variante que empiece por "x10^3": la extracción de
    alguna plantilla trunca el sufijo de unidad (p. ej. "x10^3_u/mc" en vez
    de "x10^3_u/mcL", visto en PDF reales), y no hay ninguna otra magnitud
    con ese mismo prefijo que pueda confundirse con un recuento de
    plaquetas."""
    if row is None or not is_count_1e9_l(row.get("unit")):
        return None
    return row.get("value_num")


def de_ritis_ratio(ast: Optional[float], alt: Optional[float]) -> Optional[float]:
    """Ratio AST/ALT (índice De Ritis)."""
    if ast is None or alt is None or alt == 0:
        return None
    return ast / alt


def apri(ast: Optional[float], plaquetes: Optional[float]) -> Optional[float]:
    """APRI: (AST / AST-ULN) * 100 / plaquetas."""
    if ast is None or plaquetes is None or plaquetes == 0:
        return None
    return (ast / APRI_AST_ULN) * 100.0 / plaquetes


def fib4(age: Optional[float], ast: Optional[float], plaquetes: Optional[float], alt: Optional[float]) -> Optional[float]:
    """FIB-4: edad * AST / (plaquetas * raíz(ALT))."""
    if age is None or ast is None or plaquetes is None or alt is None or alt <= 0 or plaquetes == 0:
        return None
    return age * ast / (plaquetes * (alt ** 0.5))


def _age_at(birth_date: Optional[str], fecha: str) -> Optional[int]:
    """Edad en años cumplidos en `fecha` a partir de `birth_date`
    ("AAAA-MM-DD"); `None` si no se conoce la fecha de nacimiento."""
    if not birth_date:
        return None
    nacimiento = dt.date.fromisoformat(birth_date[:10])
    referencia = dt.date.fromisoformat(fecha[:10])
    years = referencia.year - nacimiento.year
    if (referencia.month, referencia.day) < (nacimiento.month, nacimiento.day):
        years -= 1
    return years


def _index_point(fecha: str, value: float, ref_high: Optional[float], raw_name: str) -> dict[str, Any]:
    """Fila con la misma forma que `repository.get_series`, para reutilizar
    `charts.evolution_figure`/`comparison_figure` sin cambios."""
    return {
        "fecha": fecha,
        "value_num": value,
        "unit": "",
        "ref_low": None,
        "ref_high": ref_high,
        "flag_calc": compute_flag(value, None, ref_high),
        "raw_name": raw_name,
    }


def get_hepatic_index_series(con, patient_id: int) -> dict[str, list[dict[str, Any]]]:
    """Serie temporal (una fecha = un informe) de los índices hepáticos
    calculables a partir de lo ya almacenado, en el mismo formato que
    `repository.get_series`. Devuelve solo las claves de índice que tengan
    al menos un punto calculable — FIB-4 no aparecerá si el paciente no
    tiene fecha de nacimiento conocida."""
    ast_by_date = get_merged_series(con, AST_IDS, patient_id)
    alt_by_date = get_merged_series(con, ALT_IDS, patient_id)
    plaq_by_date = get_merged_series(con, PLAQUETES_IDS, patient_id)
    birth_date = get_patient_birth_date(con, patient_id)

    series: dict[str, list[dict[str, Any]]] = {"idx_de_ritis": [], "idx_apri": [], "idx_fib4": []}
    fechas = sorted(set(ast_by_date) | set(alt_by_date) | set(plaq_by_date))
    for fecha in fechas:
        ast = _u_l(ast_by_date.get(fecha))
        alt = _u_l(alt_by_date.get(fecha))
        plaquetes = _plaquetes_1e9_l(plaq_by_date.get(fecha))

        dr = de_ritis_ratio(ast, alt)
        if dr is not None:
            series["idx_de_ritis"].append(_index_point(fecha, dr, DE_RITIS_HIGH, "Ratio AST/ALT (De Ritis)"))
        a = apri(ast, plaquetes)
        if a is not None:
            series["idx_apri"].append(_index_point(fecha, a, APRI_HIGH, "APRI"))
        edad = _age_at(birth_date, fecha)
        f = fib4(edad, ast, plaquetes, alt)
        if f is not None:
            series["idx_fib4"].append(_index_point(fecha, f, FIB4_HIGH, "FIB-4"))

    return {key: points for key, points in series.items() if points}


# Etiqueta legible de cada índice sintético, para la lista de selección de
# la pestaña "Salud hepática" (gui.py). El texto largo con las citas
# completas vive en `data/descripciones/idx_*.txt` (mismo patrón que
# `lipid_risk.INDEX_LABELS`).
INDEX_LABELS = {
    "idx_de_ritis": "Ratio AST/ALT (índice De Ritis)",
    "idx_apri": "APRI (fibrosis hepática)",
    "idx_fib4": "FIB-4 (fibrosis hepática)",
}


def get_latest_hepatic_summary(con, patient_id: int) -> Optional[dict[str, Any]]:
    """Último informe con AST y ALT en U/L, con los índices calculables ese
    mismo día (FIB-4 solo si además hay plaquetas y fecha de nacimiento
    conocida). `None` si el paciente no tiene ningún informe utilizable."""
    ast_by_date = get_merged_series(con, AST_IDS, patient_id)
    alt_by_date = get_merged_series(con, ALT_IDS, patient_id)
    if not ast_by_date or not alt_by_date:
        return None
    fechas_comunes = sorted(set(ast_by_date) & set(alt_by_date))
    if not fechas_comunes:
        return None
    fecha = fechas_comunes[-1]
    plaq_by_date = get_merged_series(con, PLAQUETES_IDS, patient_id)
    birth_date = get_patient_birth_date(con, patient_id)

    ast = _u_l(ast_by_date.get(fecha))
    alt = _u_l(alt_by_date.get(fecha))
    plaquetes = _plaquetes_1e9_l(plaq_by_date.get(fecha))
    edad = _age_at(birth_date, fecha)

    return {
        "fecha": fecha,
        "ast": ast,
        "alt": alt,
        "plaquetes": plaquetes,
        "edad": edad,
        "de_ritis": de_ritis_ratio(ast, alt),
        "apri": apri(ast, plaquetes),
        "fib4": fib4(edad, ast, plaquetes, alt),
    }
