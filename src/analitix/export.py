# ---------------------------------------------------------------------------
# Script: export.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-09-30
# ---------------------------------------------------------------------------
"""Exportación de resultados a Excel, CSV y PDF."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import matplotlib.image as mpimg
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure

from analitix.charts import COLOR_ALTO, COLOR_BAJO, COLOR_BRUSCO, evolution_figure
from analitix.config import LOGO_PATH
from analitix.pdf_parser import NUMERIC_TOKEN_RE

# Excel/LibreOffice interpretan una celda de texto como fórmula si empieza por
# uno de estos caracteres (inyección de fórmulas CSV/Excel, CWE-1236). Los
# valores de texto (nombre de prueba, unidad, etc.) vienen de PDF de
# terceros o de la pestaña "Entrada manual", así que no son de confianza.
# Se aplica a todas las columnas de texto, `value_raw` incluida: aunque suele
# ser un número, el parser guarda ahí texto libre del PDF cuando el valor no
# es numérico (p. ej. lo que sigue al código LOINC), y antes quedaba sin
# neutralizar.
_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _defuse_formula(value: Any) -> Any:
    # Un número tal cual ("-1.5", "+2") no se reescribe: no es fórmula y
    # Excel lo sigue leyendo como número.
    if (
        isinstance(value, str)
        and value.startswith(_FORMULA_TRIGGER_CHARS)
        and not NUMERIC_TOKEN_RE.fullmatch(value)
    ):
        return "'" + value
    return value


def to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for col in df.columns:
        # `is_string_dtype` (en vez de comparar contra `object`) porque
        # pandas 3 usa por defecto `StringDtype`, no el `object` clásico.
        if pd.api.types.is_string_dtype(df[col]):
            df[col] = df[col].map(_defuse_formula)
    return df


def export_csv(rows: list[dict[str, Any]], path: Path) -> None:
    to_dataframe(rows).to_csv(path, index=False, encoding="utf-8-sig")


def export_excel(rows: list[dict[str, Any]], path: Path, sheet_name: str = "Resultados") -> None:
    df = to_dataframe(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        worksheet = writer.sheets[sheet_name]
        for i, col in enumerate(df.columns, start=1):
            max_len = df[col].astype(str).str.len().max()
            # Una columna enteramente `None` (p. ej. `section`/`test_group`
            # en una analítica de "Entrada manual") da `max_len = nan`; `nan`
            # es "truthy" en Python, así que `nan or 10` no cae al valor por
            # defecto y `int(nan)` revienta — de ahí el `pd.isna` explícito.
            base_len = 10 if pd.isna(max_len) else int(max_len)
            width = max(10, min(40, base_len + 2))
            worksheet.column_dimensions[worksheet.cell(row=1, column=i).column_letter].width = width


# Exportación de un informe PDF de seguimiento, implementada 2026-09-21 con
# `matplotlib.backends.backend_pdf.PdfPages` — matplotlib ya es dependencia
# dura del proyecto (`charts.py`), no hace falta ninguna librería nueva de
# generación de PDF. Se usa "(*)" en vez de un emoji como marca de cambio
# brusco: a diferencia de la pestaña Resumen (Tkinter + Segoe UI Emoji), el
# backend PDF de matplotlib no garantiza tener una fuente con glifos de
# emoji en color.
_ESTADO_TEXTO = {"alto": "Alto", "bajo": "Bajo"}
_ESTADO_COLOR = {"alto": COLOR_ALTO, "bajo": COLOR_BAJO}
_PDF_DISCLAIMER = (
    "Apoyo informativo y de seguimiento, generado automáticamente por Analitix a partir de "
    "los informes de laboratorio importados — nunca un diagnóstico. La interpretación clínica "
    "final es siempre del médico."
)


def _add_footer(fig: Figure, tipo_informe: str, pagina: int) -> None:
    """Pie de página (tipo de informe a la izquierda, nº de página a la
    derecha) en todas las páginas del PDF, incluida la portada."""
    fig.text(0.06, 0.02, tipo_informe, fontsize=8, color="#777777")
    fig.text(0.94, 0.02, f"Página {pagina}", fontsize=8, color="#777777", ha="right")


def _cover_page(patient_name: str, tipo_informe: str, fecha: str) -> Figure:
    """Portada: logo de Analitix, nombre del paciente, tipo de informe y
    fecha — sin ninguna tabla (eso empieza en la página siguiente)."""
    fig = Figure(figsize=(8.27, 11.69), dpi=100)  # A4 vertical
    try:
        logo = mpimg.imread(str(LOGO_PATH))
        ax_logo = fig.add_axes((0.32, 0.62, 0.36, 0.22))
        ax_logo.imshow(logo)
        ax_logo.axis("off")
    except OSError:
        pass  # sin el fichero de logo no se bloquea la generación del informe
    fig.text(0.5, 0.56, "Informe de seguimiento", fontsize=20, weight="bold", ha="center")
    fig.text(0.5, 0.50, tipo_informe, fontsize=14, ha="center", color="#555555")
    fig.text(0.5, 0.44, f"Paciente: {patient_name}", fontsize=12, ha="center")
    fig.text(
        0.5, 0.40, f"Último informe: {fecha[:10]}  ·  Generado: {dt.date.today().isoformat()}",
        fontsize=10, ha="center", color="#555555",
    )
    fig.text(0.5, 0.1, _PDF_DISCLAIMER, fontsize=8, color="#555555", ha="center", wrap=True)
    return fig


def _table_page(fecha: str, filas: list[dict[str, Any]], cambio_brusco_pct: float, subtitulo: str) -> Figure:
    """Una página A4 con la tabla de `filas` (mismas columnas/colores que
    la pestaña Resumen de `gui.py`)."""
    fig = Figure(figsize=(8.27, 11.69), dpi=100)  # A4 vertical
    fig.text(0.06, 0.95, subtitulo, fontsize=14, weight="bold")
    fig.text(0.06, 0.925, f"Último informe: {fecha[:10]}", fontsize=9, color="#555555")

    ax = fig.add_axes((0.06, 0.08, 0.88, 0.82))
    ax.axis("off")
    if not filas:
        ax.text(0.5, 0.95, "Sin parámetros en esta categoría.", ha="center", va="top", fontsize=10,
                 transform=ax.transAxes)
    else:
        columnas = ["Parámetro", "Valor", "Referencia", "Estado", "Variación"]
        filas_texto = []
        for f in filas:
            ref_low, ref_high = f["ref_low"], f["ref_high"]
            referencia = f"{ref_low:g} - {ref_high:g}" if ref_low is not None and ref_high is not None else "-"
            estado = _ESTADO_TEXTO.get(f["flag_calc"], "Normal")
            variacion = "-" if f["pct"] is None else f"{f['pct']:+.1f}%{' (*)' if f['brusco'] else ''}"
            filas_texto.append(
                [f["raw_name"], f"{f['value_num']:g} {f['unit'] or ''}".strip(), referencia, estado, variacion]
            )
        tabla = ax.table(cellText=filas_texto, colLabels=columnas, loc="upper center", cellLoc="left")
        tabla.auto_set_font_size(False)
        tabla.set_fontsize(8)
        tabla.scale(1, 1.4)
        for row, f in enumerate(filas, start=1):
            color = _ESTADO_COLOR.get(f["flag_calc"]) or (COLOR_BRUSCO if f["brusco"] else None)
            if color:
                tabla[(row, 3)].get_text().set_color(color)
                tabla[(row, 3)].get_text().set_weight("bold")

    fig.text(
        0.06, 0.05, f"(*) cambio de {cambio_brusco_pct:g}% o más respecto al informe anterior, esté o no "
        "dentro de rango.",
        fontsize=7, color="#555555",
    )
    return fig


def export_pdf(
    patient_name: str,
    fecha: str,
    filas: list[dict[str, Any]],
    series_by_canonical_id: dict[str, list[dict[str, Any]]],
    labels: dict[str, str],
    cambio_brusco_pct: float,
    path: Path,
    *,
    tipo_informe: str,
) -> int:
    """Informe de seguimiento en PDF (ampliado 2026-09-21 en dos pasos:
    primero con dos tipos de informe — "completo"/"de alterados", ver
    `gui._export_pdf` para cómo se construyen `filas` en cada caso — y
    después con esta estructura de página fija para los dos, tras
    comprobar con una analítica real que ni siquiera la tabla de
    "alterados" cabía siempre en una sola página):

    1. Portada (`_cover_page`): logo, paciente, tipo de informe, fecha.
    2. Tabla de los parámetros de `filas` que están fuera de rango en el
       informe más reciente (`flag_calc in ("alto", "bajo")`).
    3. Tabla del resto de `filas` (dentro de rango, o sin `flag_calc`).
    4. Un gráfico de evolución (`charts.evolution_figure`) por cada
       parámetro de `filas` con **al menos 2 puntos** en
       `series_by_canonical_id` — nunca para los parámetros "normales"
       (el llamador ya decide qué incluir ahí) ni para uno con un único
       valor (no hay nada que mostrar como evolución).

    Todas las páginas llevan pie con `tipo_informe` a la izquierda y el
    nº de página a la derecha. Devuelve el nº de páginas de gráfico
    añadidas."""
    fuera_de_rango = [f for f in filas if f["flag_calc"] in ("alto", "bajo")]
    resto = [f for f in filas if f["flag_calc"] not in ("alto", "bajo")]

    paginas_graficos = 0
    pagina = 1
    with PdfPages(path) as pdf:
        for fig in (
            _cover_page(patient_name, tipo_informe, fecha),
            _table_page(fecha, fuera_de_rango, cambio_brusco_pct, "Parámetros alterados en la última analítica"),
            _table_page(fecha, resto, cambio_brusco_pct, "Resto de parámetros"),
        ):
            _add_footer(fig, tipo_informe, pagina)
            pdf.savefig(fig)
            pagina += 1

        for f in filas:
            series = series_by_canonical_id.get(f["canonical_id"])
            if not series or len(series) < 2:
                continue
            fig = evolution_figure(series, labels.get(f["canonical_id"], f["raw_name"]))
            _add_footer(fig, tipo_informe, pagina)
            pdf.savefig(fig)
            pagina += 1
            paginas_graficos += 1
    return paginas_graficos
