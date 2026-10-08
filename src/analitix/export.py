# ---------------------------------------------------------------------------
# Script: export.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-10-08
# ---------------------------------------------------------------------------
"""Exportación de resultados a Excel, CSV y PDF."""
from __future__ import annotations

import datetime as dt
import io
import textwrap
from pathlib import Path
from typing import Any, Callable, Optional

import matplotlib.image as mpimg
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure

from analitix import __version__, __version_date__
from analitix.charts import (
    COLOR_ALTO, COLOR_BAJO, COLOR_BRUSCO, DEFAULT_MIN_POINTS, data_sufficiency, evolution_figure,
)
from analitix.config import LOGO_PATH
from analitix.pdf_parser import NUMERIC_TOKEN_RE
from analitix.updates import REPO_URL

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
_ESTADO_TEXTO = {"alto": "▲ Alto", "bajo": "▼ Bajo"}  # ▲/▼ además del color (apto para daltonismo)
_ESTADO_COLOR = {"alto": COLOR_ALTO, "bajo": COLOR_BAJO}
_PDF_DISCLAIMER = (
    "Apoyo informativo y de seguimiento, generado automáticamente por Analitix a partir de "
    "los informes de laboratorio importados — nunca un diagnóstico. La interpretación clínica "
    "final es siempre del médico."
)


# Versión con la que se generó el informe, en la portada y en el pie de cada
# página, para saber de dónde sale cualquier página suelta.
_ANALITIX_VERSION = f"Analitix {__version__} ({__version_date__})"
_FOOTER_STRIP_IN = 0.4  # franja propia del pie en las páginas que no eran A4
# Tabla de parámetros: el nombre ocupa casi la mitad (antes las cinco
# columnas medían igual y el nombre se cortaba); el estado es una palabra.
_TABLE_COL_WIDTHS = (0.46, 0.15, 0.15, 0.09, 0.15)
_TABLE_NAME_MAX = 60  # caracteres que caben en esa columna a 8 pt
_A4_IN = (8.27, 11.69)


def _is_a4(fig: Figure) -> bool:
    ancho, alto = fig.get_size_inches()
    return sorted((round(ancho, 2), round(alto, 2))) == sorted(_A4_IN)


def _fit_page_a4(fig: Figure) -> None:
    """Toda página del PDF sale en tamaño A4, para imprimirla aprovechando
    la hoja: las figuras que no lo son (gráficos de evolución, mapa de
    calor, "Qué ha cambiado"...) pasan a A4 vertical si son más altas que
    anchas, o apaisado si no, ocupando todo el ancho. Como su contenido
    llega hasta el borde inferior (p. ej. la leyenda del mapa de calor),
    se reserva abajo una franja de `_FOOTER_STRIP_IN` para el pie y se
    comprime el resto en vertical (ejes, textos y leyendas de figura), para
    que el pie no se superponga a nada. Las páginas que ya son A4 (portada,
    tablas, textos) tienen su sitio para el pie y no se tocan."""
    if _is_a4(fig):
        return
    ancho, alto = fig.get_size_inches()
    nuevo_ancho, nuevo_alto = _A4_IN if alto > ancho else _A4_IN[::-1]
    escala, desplazamiento = 1 - _FOOTER_STRIP_IN / nuevo_alto, _FOOTER_STRIP_IN / nuevo_alto
    fig.set_size_inches(nuevo_ancho, nuevo_alto)
    rect = getattr(fig, "analitix_tight_rect", None)
    if rect is not None:
        # Figuras de altura variable ("Qué ha cambiado", mapa de calor): se
        # recalculan sus márgenes al tamaño A4 final, dentro del espacio que
        # deja libre el pie, en vez de comprimirlas (si no, las etiquetas
        # largas y la leyenda superior quedaban cortadas por el borde).
        x0, y0, x1, y1 = rect
        fig.tight_layout(rect=(x0, desplazamiento + y0 * escala, x1, desplazamiento + y1 * escala))
        for leyenda in fig.legends:
            leyenda.set_bbox_to_anchor((0, desplazamiento, 1, escala), transform=fig.transFigure)
        return
    for ax in fig.axes:
        pos = ax.get_position()
        ax.set_position((pos.x0, pos.y0 * escala + desplazamiento, pos.width, pos.height * escala))
    for texto in fig.texts:
        x, y = texto.get_position()
        texto.set_position((x, y * escala + desplazamiento))
    for leyenda in fig.legends:
        leyenda.set_bbox_to_anchor((0, desplazamiento, 1, escala), transform=fig.transFigure)


def _add_footer(fig: Figure, tipo_informe: str, pagina: int, total: int) -> None:
    """Pie de página en todas las páginas del PDF, incluida la portada, en
    una franja propia que no tapa el contenido, en una página A4
    (`_fit_page_a4`): tipo de informe a la izquierda y "Página n de N" a la
    derecha; debajo, centrada, la versión de Analitix (en su propia línea
    porque el tipo de informe puede ser largo, p. ej. con el filtro de
    laboratorios)."""
    _fit_page_a4(fig)
    alto = fig.get_size_inches()[1]
    y = 0.2 / alto  # a 0,2 pulgadas del borde inferior
    fig.text(0.06, y, tipo_informe, fontsize=8, color="#777777")
    fig.text(0.94, y, f"Página {pagina} de {total}", fontsize=8, color="#777777", ha="right")
    fig.text(0.5, 0.06 / alto, _ANALITIX_VERSION, fontsize=7, color="#777777", ha="center")


def _cover_page(patient_name: str, tipo_informe: str, fecha: str) -> Figure:
    """Portada: logo de Analitix, nombre del paciente, tipo de informe,
    fecha, versión de Analitix y URL del proyecto — sin ninguna tabla (eso
    empieza en la página siguiente)."""
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
        0.5, 0.40, f"Último informe de laboratorio: {fecha[:10]}  ·  Generado: {dt.date.today().isoformat()}",
        fontsize=10, ha="center", color="#555555",
    )
    fig.text(0.5, 0.20, f"Generado con {_ANALITIX_VERSION}", fontsize=9, ha="center", color="#555555")
    fig.text(0.5, 0.18, REPO_URL, fontsize=9, ha="center", color="#555555")
    fig.text(0.5, 0.1, _PDF_DISCLAIMER, fontsize=8, color="#555555", ha="center", wrap=True)
    return fig


def _table_page(fecha: str, filas: list[dict[str, Any]], cambio_brusco_pct: float, subtitulo: str) -> Figure:
    """Una página A4 con la tabla de `filas` (mismas columnas/colores que
    la pestaña Resumen de `gui.py`)."""
    fig = Figure(figsize=(8.27, 11.69), dpi=100)  # A4 vertical
    fig.text(0.06, 0.95, subtitulo, fontsize=14, weight="bold")
    fig.text(0.06, 0.925, f"Último informe de laboratorio: {fecha[:10]}", fontsize=9, color="#555555")

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
            nombre = f["raw_name"] or ""
            if len(nombre) > _TABLE_NAME_MAX:
                nombre = nombre[: _TABLE_NAME_MAX - 1] + "…"
            filas_texto.append(
                [nombre, f"{f['value_num']:g} {f['unit'] or ''}".strip(), referencia, estado, variacion]
            )
        tabla = ax.table(cellText=filas_texto, colLabels=columnas, loc="upper center", cellLoc="left",
                         colWidths=_TABLE_COL_WIDTHS)
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
    min_points: int = DEFAULT_MIN_POINTS,
    on_progress: Optional[Callable[[int, int], None]] = None,
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
       valor (no hay nada que mostrar como evolución). Con menos de
       `min_points` (el mismo ajuste de Configuración que la pantalla) el
       gráfico lleva el aviso de pocos datos de `charts.data_sufficiency`.

    Todas las páginas llevan pie (`_add_footer`). `on_progress(n, total)`
    se llama tras escribir cada página (barra de progreso de `gui.py`).
    Devuelve el nº de páginas de gráfico añadidas."""
    fuera_de_rango = [f for f in filas if f["flag_calc"] in ("alto", "bajo")]
    resto = [f for f in filas if f["flag_calc"] not in ("alto", "bajo")]
    # Se sabe de antemano qué gráficos habrá, para el "de N" del pie.
    graficos = []
    for f in filas:
        series = series_by_canonical_id.get(f["canonical_id"])
        if series and data_sufficiency(len(series), min_points) not in ("sin_datos", "un_punto"):
            graficos.append((f, series))
    total = 3 + len(graficos)

    pagina = 1
    with PdfPages(path) as pdf:
        for fig in (
            _cover_page(patient_name, tipo_informe, fecha),
            _table_page(fecha, fuera_de_rango, cambio_brusco_pct, "Parámetros alterados en la última analítica"),
            _table_page(fecha, resto, cambio_brusco_pct, "Resto de parámetros"),
        ):
            _add_footer(fig, tipo_informe, pagina, total)
            pdf.savefig(fig)
            if on_progress:
                on_progress(pagina, total)
            pagina += 1

        for f, series in graficos:
            fig = evolution_figure(series, labels.get(f["canonical_id"], f["raw_name"]), min_points)
            _add_footer(fig, tipo_informe, pagina, total)
            pdf.savefig(fig)
            if on_progress:
                on_progress(pagina, total)
            pagina += 1
    return len(graficos)


# -- Informe PDF personalizado (Exportar → "Informe PDF personalizado...") --
# El usuario elige las secciones en `gui._export_custom_pdf`, que construye
# las figuras; aquí solo se monta el documento: portada + páginas en el
# orden recibido + pie en todas, igual que `export_pdf`.

def table_page(fecha: str, filas: list[dict[str, Any]], cambio_brusco_pct: float, subtitulo: str) -> Figure:
    """Página de tabla (la misma de `export_pdf`), para el informe personalizado."""
    return _table_page(fecha, filas, cambio_brusco_pct, subtitulo)


def text_page(titulo: str, texto: str) -> Figure:
    """Página A4 con un título y un texto (p. ej. el resumen de un panel
    clínico tal como se ve en pantalla). El texto se ajusta a lo ancho y
    se corta al final de la página si no cabe; los resúmenes de los
    paneles caben de sobra. Guarda título y líneas en
    `fig.analitix_text`: con varios gráficos por página, `_flow_pages`
    pone el texto en el flujo y los gráficos siguen justo debajo."""
    fig = Figure(figsize=(8.27, 11.69), dpi=100)  # A4 vertical
    lineas = []
    for parrafo in texto.strip().splitlines():
        lineas.extend(textwrap.wrap(parrafo, width=_TEXT_PAGE_WIDTH) or [""])
    lineas = lineas[:_TEXT_PAGE_MAX_LINES]
    fig.analitix_text = (titulo, lineas)
    fig.text(0.06, 0.95, titulo, fontsize=14, weight="bold")
    fig.text(0.06, 0.95 - _TEXT_GAP_IN / 11.69, "\n".join(lineas), fontsize=9, va="top", linespacing=1.4)
    return fig


_TEXT_PAGE_WIDTH = 100
_TEXT_PAGE_MAX_LINES = 70
_TEXT_GAP_IN = 0.3  # de la línea base del título al principio del texto
_TEXT_LINE_IN = 9 * 1.4 / 72  # alto de cada línea de texto (9 pt, interlineado 1,4)


# Varios gráficos por página A4 vertical (informe personalizado): márgenes
# y resolución a la que se rasteriza cada gráfico (suficiente para imprimir).
_CHARTS_MARGIN_IN = 0.5
_CHARTS_BOTTOM_IN = _FOOTER_STRIP_IN + 0.25
_CHARTS_GAP_IN = 0.15
_CHARTS_DPI = 200
# Los gráficos se reducen como mucho a este tamaño para que quepan 2 o 3 por
# página; uno más alto (recuadro de notas largo, tensión arterial con dos
# ejes) ocupa más sitio en vez de quedar ilegible.
_CHARTS_MIN_SCALE = 0.75


def _is_chart(fig: Figure) -> bool:
    """Gráfico agrupable: ni página A4 propia (portada, tablas, textos) ni
    figura de altura variable ("Qué ha cambiado", mapa de calor), que
    siguen ocupando su página."""
    return not _is_a4(fig) and getattr(fig, "analitix_tight_rect", None) is None


def _flow_pages(paginas: list[Figure], por_pagina: int) -> list[Figure | list[tuple[str, Any, float]]]:
    """Con `por_pagina` 2 o 3, rellena páginas A4 verticales de arriba abajo
    con los textos (`text_page`) y gráficos seguidos de `paginas`: cada
    gráfico a todo el ancho útil y con alto 1/`por_pagina` del útil (sin
    bajar de `_CHARTS_MIN_SCALE` de su tamaño), y un texto con el alto que
    ocupa, así que los gráficos de un panel van justo debajo de su
    resumen. Cada página es una lista de bloques `(tipo, contenido, alto)`
    que `_flow_page` dibuja al escribirla (así la barra de progreso avanza
    también mientras se rasterizan). Las demás páginas (tablas, "Qué ha
    cambiado", mapa de calor) quedan igual y cortan el flujo. Con 1, todo
    queda igual."""
    if por_pagina <= 1:
        return paginas
    alto_util = _A4_IN[1] - _CHARTS_MARGIN_IN - _CHARTS_BOTTOM_IN
    franja = alto_util / por_pagina - _CHARTS_GAP_IN
    resultado, bloques, libre = [], [], alto_util

    def cierra() -> None:
        nonlocal bloques, libre
        if bloques:
            resultado.append(bloques)
        bloques, libre = [], alto_util

    def bloque_de(fig: Figure) -> Optional[tuple[str, Any, float]]:
        texto = getattr(fig, "analitix_text", None)
        if texto is not None:
            return "texto", texto, _TEXT_GAP_IN + len(texto[1]) * _TEXT_LINE_IN + 0.15
        if _is_chart(fig):
            alto = fig.get_size_inches()[1]
            return "grafico", fig, min(alto, max(franja, alto * _CHARTS_MIN_SCALE), alto_util)
        return None

    bloques_de = [bloque_de(fig) for fig in paginas]
    for i, (fig, bloque) in enumerate(zip(paginas, bloques_de)):
        if bloque is None or bloque[2] > alto_util:  # no fluye, o texto de más de una página
            cierra()
            resultado.append(fig)
            continue
        necesario = bloque[2]
        siguiente = bloques_de[i + 1] if i + 1 < len(paginas) else None
        if bloque[0] == "texto" and siguiente is not None and siguiente[0] == "grafico":
            # El resumen de un panel no se queda solo al pie de la página:
            # va con su primer gráfico.
            necesario = min(necesario + _CHARTS_GAP_IN + siguiente[2], alto_util)
        if necesario > libre:
            cierra()
        bloques.append(bloque)
        libre -= bloque[2] + _CHARTS_GAP_IN
    cierra()
    return resultado


def _flow_page(bloques: list[tuple[str, Any, float]]) -> Figure:
    """Dibuja una página de `_flow_pages`. Los gráficos se rehacen al ancho
    útil (se cambia el ancho de la figura, no se estira la imagen) y, si
    tienen que encoger, se dibujan más anchos y se reduce la imagen
    entera: nunca se deforman y todos ocupan el mismo ancho."""
    # ponytail: rasterizado (el texto de los gráficos no se puede seleccionar);
    # vectorial exigiría rehacer cada gráfico como subfigura.
    ancho_a4, alto_a4 = _A4_IN
    page = Figure(figsize=_A4_IN, dpi=100)
    ancho_util = ancho_a4 - 2 * _CHARTS_MARGIN_IN
    arriba = alto_a4 - _CHARTS_MARGIN_IN
    for tipo, contenido, alto in bloques:
        if tipo == "texto":
            titulo, lineas = contenido
            page.text(_CHARTS_MARGIN_IN / ancho_a4, (arriba - 0.2) / alto_a4, titulo, fontsize=14, weight="bold")
            page.text(_CHARTS_MARGIN_IN / ancho_a4, (arriba - 0.2 - _TEXT_GAP_IN) / alto_a4, "\n".join(lineas),
                      fontsize=9, va="top", linespacing=1.4)
        else:
            fig = contenido
            escala = alto / fig.get_size_inches()[1]
            fig.set_size_inches(ancho_util / escala, alto / escala)
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=_CHARTS_DPI * escala)
            buf.seek(0)
            ax = page.add_axes((_CHARTS_MARGIN_IN / ancho_a4, (arriba - alto) / alto_a4,
                                ancho_util / ancho_a4, alto / alto_a4))
            ax.imshow(mpimg.imread(buf), interpolation="none")
            ax.axis("off")
        arriba -= alto + _CHARTS_GAP_IN
    return page


def export_pages_pdf(patient_name: str, fecha: str, paginas: list[Figure], path: Path, *, tipo_informe: str,
                     graficos_por_pagina: int = 1,
                     on_progress: Optional[Callable[[int, int], None]] = None) -> int:
    """Escribe el informe personalizado: portada (`_cover_page`, con el
    aviso de que no es un diagnóstico) y después `paginas` en ese orden,
    todas con pie (`_add_footer`). Con `graficos_por_pagina` 2 o 3, los
    textos y gráficos seguidos llenan páginas A4 verticales, 2 o 3 gráficos
    por página a todo el ancho (`_flow_pages`); con 1, cada uno en su
    página (apaisada).
    `on_progress(n, total)` se llama tras escribir cada página. Devuelve el
    nº total de páginas."""
    paginas = _flow_pages(paginas, graficos_por_pagina)
    total = len(paginas) + 1
    with PdfPages(path) as pdf:
        for numero, fig in enumerate([_cover_page(patient_name, tipo_informe, fecha), *paginas], start=1):
            if isinstance(fig, list):
                fig = _flow_page(fig)
            _add_footer(fig, tipo_informe, numero, total)
            pdf.savefig(fig)
            if on_progress:
                on_progress(numero, total)
    return total
