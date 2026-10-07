# ---------------------------------------------------------------------------
# Script: charts.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-10-06
# ---------------------------------------------------------------------------
"""Construcción de gráficos de evolución, comparativas y mapa de calor con matplotlib."""
from __future__ import annotations

import datetime as dt
import textwrap
from typing import Any, Optional

import matplotlib.dates as mdates
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, to_rgba
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# Paleta apta para daltonismo (2026-10-06): colores de Okabe & Ito, "Color
# Universal Design" (2002, https://jfly.uni-koeln.de/color/), distinguibles
# con deuteranopía, protanopía y tritanopía. Sin la pareja verde/rojo ni
# rojo/naranja: alto = bermellón, bajo = azul (misma polaridad que el mapa
# de calor). El color nunca va solo: alto/bajo llevan también ▲/▼ y texto.
COLOR_NORMAL = "#009E73"  # verde azulado
COLOR_ALTO = "#D55E00"    # bermellón
COLOR_BAJO = "#0072B2"    # azul
COLOR_TREND = "#555555"
# Cambio brusco dentro de rango (pestaña Resumen y exportación a PDF,
# `gui.CAMBIO_BRUSCO_PCT`) — no es un color de estado clínico como los de
# arriba, solo distingue visualmente ese caso de "alto"/"bajo"/"normal".
# "Wine" de la paleta "muted" de Paul Tol (también apta para daltonismo,
# https://personal.sron.nl/~pault/): el púrpura de Okabe-Ito no llega al
# contraste 4.5:1 como texto sobre blanco.
COLOR_BRUSCO = "#882255"
# Símbolo que acompaña al color de alto/bajo (Evolución, Resumen, PDF).
SIMBOLO_ESTADO = {"alto": "▲", "bajo": "▼"}

# Desviación "leve": fuera del rango por menos de este múltiplo de su ancho
# (`range_width`; con un único límite, de su valor). El punto se rellena con
# el mismo color, más claro, y conserva el contorno del color pleno; a
# partir de aquí, color pleno. Cambia la claridad, no el tono: se sigue
# distinguiendo con daltonismo y ▲/▼ no cambia. Para distinguir desviaciones
# leves de graves (Zikmund-Fisher et al., JAMIA 2017;24(3):520-528,
# doi:10.1093/jamia/ocw169). Elección de interfaz, no un umbral clínico.
DESVIACION_LEVE = 0.25
# El mismo umbral da la palabra del gráfico de posición (`deviation_label`):
# "ligeramente" por debajo de DESVIACION_LEVE, "muy" a partir de DESVIACION_GRANDE.
DESVIACION_GRANDE = 1.0
ETIQUETA_OBJETIVO = "Objetivo indicado por su médico"


def _tint(color: str, amount: float = 0.55) -> tuple:
    """El mismo color mezclado con blanco (`amount` = proporción de blanco)."""
    r, g, b, _ = to_rgba(color)
    return (r + (1 - r) * amount, g + (1 - g) * amount, b + (1 - b) * amount, 1.0)


def _point_style(s: dict[str, Any], base_color: str) -> tuple:
    """(relleno, contorno) del punto: color de su estado, más claro si la
    desviación es leve (`DESVIACION_LEVE`)."""
    color = {"alto": COLOR_ALTO, "bajo": COLOR_BAJO}.get(s.get("flag_calc"), base_color)
    if s.get("flag_calc") in ("alto", "bajo"):
        d = range_distance(s["value_num"], s.get("ref_low"), s.get("ref_high"))
        if d is not None and abs(d) < DESVIACION_LEVE:
            return _tint(color), color
    return color, color


def apply_target(series: list[dict[str, Any]], target: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """La serie medida contra el objetivo indicado por el médico (`targets`,
    `repository.get_target`) en vez de contra el rango de cada informe: el
    objetivo sustituye al rango, no se añade (Scherer et al., J Med Internet
    Res 2018;20(10):e11027, doi:10.2196/11027: mostrar solo el objetivo se
    entendió mejor que añadirlo junto al rango estándar). Sin objetivo,
    devuelve la serie tal cual."""
    if not target:
        return series
    from analitix.pdf_parser import compute_flag  # import local: charts no depende del parser

    low, high = target.get("low"), target.get("high")
    return [{**s, "ref_low": low, "ref_high": high, "flag_calc": compute_flag(s["value_num"], low, high),
             "objetivo": True, "objetivo_nota": target.get("note")} for s in series]

# Colores base de cada panel de la comparativa (paneles separados: solo
# decorativos, pero sin coincidir con el azul de "bajo").
COMPARISON_COLORS = [COLOR_NORMAL, "#CC79A7"]

MAX_COMPARISON_TESTS = 2

# Puntos mínimos para calcular una recta de tendencia; con menos, una regresión
# lineal no es fiable y no se dibuja.
MIN_POINTS_FOR_TREND = 3
TREND_PROJECTION_DAYS = 90
# Para dar una tendencia por demostrada hacen falta, además de un IC que
# excluya el 0 (`_fit_trend`), al menos 5 analíticas en al menos 2 años: con
# menos, la pendiente de una serie corta e irregular es poco estable.
# Elección prudente de interfaz, no un umbral clínico.
MIN_POINTS_CONFIRM_TREND = 5
MIN_DAYS_CONFIRM_TREND = 2 * 365
SIN_TENDENCIA = "sin tendencia demostrable"
POCOS_DATOS_TENDENCIA = "pocos datos para confirmarla"
# Filtrado glomerular estimado: la guía KDIGO define "progresión rápida" de
# la enfermedad renal crónica como un descenso sostenido de más de 5
# mL/min/1,73 m² al año (KDIGO 2012 Clinical Practice Guideline for the
# Evaluation and Management of CKD, cap. 1 "Definition and classification of
# CKD", Kidney Int Suppl 2013;3(1):19-62, doi:10.1038/kisup.2012.64; lo
# mantiene la actualización KDIGO 2024). Es el único umbral de velocidad de
# cambio con respaldo de guía entre las pruebas de la app; las series que lo
# usan llevan `kdigo_fg=True` (gui._evolution_figure).
KDIGO_RAPID_DECLINE_PER_YEAR = 5.0

# Analíticas recomendadas para que un gráfico de evolución sea
# representativo (valor por defecto del ajuste "min_points_evolucion" de
# Configuración); por debajo se dibuja con aviso y con 1 no se dibuja (ver
# `data_sufficiency`). Elección de interfaz, no un umbral clínico.
DEFAULT_MIN_POINTS = 4

# Margen vertical extra (proporción del rango de datos) para que las
# etiquetas de los valores fuera de rango —dibujadas con un desplazamiento
# fijo en píxeles por encima/debajo del punto— no queden pegadas al borde
# del área de datos ni se solapen con la leyenda.
Y_MARGIN_RATIO = 0.15
# Ancho máximo, en caracteres, de cada línea del recuadro bajo el gráfico.
INFO_BOX_WIDTH = 100


# Forma del punto por laboratorio (Evolución, Comparativa y los gráficos de
# los paneles). Orden fijo y nunca reciclado: si alguna vez hubiera más
# laboratorios que formas, los sobrantes comparten la última ("x") en vez de
# inventar formas nuevas.
LAB_MARKERS = ("o", "s", "^", "D", "v", "P", "X")
LAB_UNKNOWN = "Laboratorio desconocido"
COLOR_INK_SECONDARY = "#52514e"


def _labs_in_order(series: list[dict[str, Any]]) -> list[str]:
    """Laboratorios de la serie en orden de primera aparición (informes
    importados antes de guardar el laboratorio -> `LAB_UNKNOWN`)."""
    seen: list[str] = []
    for s in series:
        lab = s.get("lab") or LAB_UNKNOWN
        if lab not in seen:
            seen.append(lab)
    return seen


def _markers_for(labs: list[str]) -> list[str]:
    return [LAB_MARKERS[min(i, len(LAB_MARKERS) - 1)] for i in range(len(labs))]


def _parse_fecha(fecha: str) -> dt.datetime:
    fecha = fecha.split(" ")[0] if len(fecha) > 10 else fecha
    try:
        return dt.datetime.strptime(fecha[:10], "%Y-%m-%d")
    except ValueError:
        return dt.datetime.min


def _fit_trend(fechas: list[dt.datetime], valores: list[float]) -> Optional[tuple[float, float, Any, float, float]]:
    """Pendiente robusta de Theil-Sen (valor ~ fecha) con su intervalo de
    confianza del 95 %: (pendiente, ordenada, x, IC inferior, IC superior),
    pendientes por día. `None` con menos de `MIN_POINTS_FOR_TREND` puntos.

    La pendiente es la mediana de las pendientes entre todos los pares de
    puntos, y el IC sale de la distribución de la τ de Kendall (Sen PK,
    "Estimates of the regression coefficient based on Kendall's tau", J Am
    Stat Assoc 1968;63(324):1379-89, doi:10.1080/01621459.1968.10480934):
    con varianza n(n-1)(2n+5)/18 (sin corrección por empates, algo más
    conservador), se toman las pendientes ordenadas de posiciones
    (N ∓ 1,96·σ)/2. Frente a la recta de mínimos cuadrados, un único valor
    atípico apenas la mueve, y el IC dice si el cambio es demostrable (si
    incluye 0, no lo es). Ordenada de Conover: mediana(y) − pendiente ·
    mediana(x)."""
    if len(fechas) < MIN_POINTS_FOR_TREND:
        return None
    x = np.asarray(mdates.date2num(fechas), dtype=float)
    y = np.asarray(valores, dtype=float)
    i, j = np.triu_indices(len(x), 1)
    dx = x[j] - x[i]
    validos = dx != 0  # dos analíticas el mismo día no dan pendiente
    pendientes = np.sort((y[j] - y[i])[validos] / dx[validos])
    if not len(pendientes):
        return None
    slope = float(np.median(pendientes))
    intercept = float(np.median(y) - slope * np.median(x))
    n, total = len(x), len(pendientes)
    margen = 1.959964 * np.sqrt(n * (n - 1) * (2 * n + 5) / 18)
    bajo = pendientes[max(int(round((total - margen) / 2)) - 1, 0)]
    alto = pendientes[min(int(round((total + margen) / 2)), total - 1)]
    return slope, intercept, x, float(bajo), float(alto)


def _draw_trend_lines(ax, fit: Optional[tuple[float, float, Any]]) -> None:
    """Dibuja la recta de tendencia ajustada por `_fit_trend` y su proyección
    a `TREND_PROJECTION_DAYS` días vista (sin texto, ver `_trend_text`)."""
    if fit is None:
        return
    slope, intercept, x = fit[:3]

    x_fit = np.array([x[0], x[-1]])
    ax.plot(mdates.num2date(x_fit), slope * x_fit + intercept, linestyle=":", color=COLOR_TREND, linewidth=1.3, zorder=0)

    x_proj = np.array([x[-1], x[-1] + TREND_PROJECTION_DAYS])
    y_proj = slope * x_proj + intercept
    ax.plot(mdates.num2date(x_proj), y_proj, linestyle=":", color=COLOR_TREND, linewidth=1.3, alpha=0.5, zorder=0)


def _trend_direction(
    fit: Optional[tuple[float, float, Any]],
    valores: list[float],
    ref_low: Optional[float],
    ref_high: Optional[float],
) -> Optional[tuple[str, str, float, float]]:
    """Flecha + palabra + pendiente + `span` (rango usado como referencia
    de magnitud, ver abajo) a partir del ajuste de `_fit_trend`, o `None`
    si no hay suficientes puntos (ver `MIN_POINTS_FOR_TREND`). Compartido
    por `_trend_text` (texto bajo el gráfico de Evolución) y `trend_arrow`
    (columna "Tendencia" de la pestaña Resumen, gui.py) para no mantener
    el umbral de "estable" en dos sitios."""
    if fit is None:
        return None
    slope, intercept, x, ic_bajo, ic_alto = fit
    span = (ref_high - ref_low) if (ref_low is not None and ref_high is not None and ref_high > ref_low) else None
    if span is None:
        span = (max(valores) - min(valores)) or abs(valores[-1]) or 1.0
    # Con pocas analíticas o poco tiempo, ni siquiera un IC que excluya el 0
    # es fiable para hablar de tendencia (≥ 5 analíticas en ≥ 2 años).
    if len(x) < MIN_POINTS_CONFIRM_TREND or x[-1] - x[0] < MIN_DAYS_CONFIRM_TREND:
        return "→", POCOS_DATOS_TENDENCIA, slope, span
    # Si el IC del 95 % de la pendiente de Theil-Sen incluye el 0, el cambio
    # no es demostrable con estos datos (ver `_fit_trend`).
    if ic_bajo <= 0 <= ic_alto:
        return "→", SIN_TENDENCIA, slope, span

    # Umbral de "estable": un cambio, a lo largo de todo el periodo observado,
    # menor al 5% del rango de referencia (o del propio rango de valores si no
    # hay rango de referencia) no se considera una tendencia real. El mismo
    # `span` sirve de vara de medir para la magnitud (leve/brusca) de una
    # tendencia real: cuánto rango normal se recorre por año.
    change_over_period = slope * (x[-1] - x[0])
    if abs(change_over_period) < 0.05 * span:
        return "→", "estable", slope, span
    if change_over_period > 0:
        return "↑", "subiendo", slope, span
    return "↓", "bajando", slope, span


def _trend_text(
    fit: Optional[tuple[float, float, Any]],
    valores: list[float],
    ref_low: Optional[float],
    ref_high: Optional[float],
) -> Optional[str]:
    """Texto "↑ Tendencia: subiendo (...)" a partir del ajuste de
    `_fit_trend`, o `None` si no hay suficientes puntos para uno (ver
    `MIN_POINTS_FOR_TREND`)."""
    direction = _trend_direction(fit, valores, ref_low, ref_high)
    if direction is None:
        return None
    arrow, palabra, slope, _span = direction
    _, intercept, x, ic_bajo, ic_alto = fit
    if palabra == POCOS_DATOS_TENDENCIA:
        return (f"{arrow} Tendencia: {palabra} (hacen falta ≥ {MIN_POINTS_CONFIRM_TREND} analíticas "
                f"en ≥ {MIN_DAYS_CONFIRM_TREND // 365} años)")
    ritmo = f"~{slope * 365.25:+.2g}/año (IC 95 %: {ic_bajo * 365.25:+.2g} a {ic_alto * 365.25:+.2g})"
    if palabra == SIN_TENDENCIA:
        return f"{arrow} Tendencia: {palabra}, ritmo {ritmo}"
    proyeccion = slope * (x[-1] + TREND_PROJECTION_DAYS) + intercept
    return f"{arrow} Tendencia: {palabra} {ritmo} · proy. 3 meses: {proyeccion:.3g}"


def _kdigo_note(series: list[dict[str, Any]], fit) -> Optional[str]:
    """Nota de la guía KDIGO para el filtrado glomerular (`kdigo_fg`) cuando
    el descenso es demostrable y supera `KDIGO_RAPID_DECLINE_PER_YEAR`."""
    if not fit or not series or not series[0].get("kdigo_fg"):
        return None
    direccion = _trend_direction(fit, [s["value_num"] for s in series], None, None)
    _slope, _intercept, _x, _ic_bajo, ic_alto = fit
    if (direccion and direccion[1] == "bajando" and fit[0] * 365.25 < -KDIGO_RAPID_DECLINE_PER_YEAR
            and ic_alto < 0):
        return (f"La guía KDIGO llama «progresión rápida» a un descenso sostenido de más de "
                f"{KDIGO_RAPID_DECLINE_PER_YEAR:g} al año: coméntalo con tu médico.")
    return None


def trend_arrow(series: list[dict[str, Any]], ref_low: Optional[float], ref_high: Optional[float]) -> Optional[str]:
    """Flecha (↑/→/↓) de la tendencia de toda la serie, con la magnitud
    anual en subida/bajada (p. ej. "↑ +38%/año") — para columnas de tabla
    (pestaña Resumen, gui.py) en vez del gráfico completo. La magnitud es
    el cambio anualizado (`pendiente × 365.25`) como % del `span` que ya
    decide "estable" (rango de referencia, o rango de valores si no hay
    rango) — así un +100%/año significa "recorre todo el rango normal en
    un año" (tendencia fuerte) y un +10%/año, una décima parte (tendencia
    leve), comparable entre parámetros con periodos observados de
    distinta duración. Sin magnitud si está "estable" (la flecha ya lo
    dice). `series` es la salida tal cual de `repository.get_series`
    (dicts con `fecha`/`value_num`). `None` con menos de
    `MIN_POINTS_FOR_TREND` puntos."""
    fechas = [_parse_fecha(s["fecha"]) for s in series]
    valores = [s["value_num"] for s in series]
    direction = _trend_direction(_fit_trend(fechas, valores), valores, ref_low, ref_high)
    if direction is None or direction[1] == POCOS_DATOS_TENDENCIA:
        return None
    arrow, _palabra, slope, span = direction
    if arrow == "→":
        return arrow
    magnitud_pct_anual = slope * 365.25 / span * 100
    return f"{arrow} {magnitud_pct_anual:+.0f}%/año"


def _pct_change_text(valores: list[float]) -> Optional[str]:
    """Variación porcentual del último valor respecto al anterior y respecto
    al primero de la serie — la tendencia ya dice hacia dónde va el valor a
    largo plazo, pero no si el último salto en concreto es grande o
    pequeño en términos relativos. `None` con menos de 2 puntos, o si el
    valor de referencia de una de las dos comparaciones es 0 (división por
    cero: se omite solo esa comparación, no las dos)."""
    if len(valores) < 2:
        return None
    partes = []
    if valores[-2] != 0:
        ultimo_pct = (valores[-1] - valores[-2]) / valores[-2] * 100
        partes.append(f"último cambio: {ultimo_pct:+.1f}% vs. anterior")
    if valores[0] != 0:
        total_pct = (valores[-1] - valores[0]) / valores[0] * 100
        partes.append(f"variación del periodo: {total_pct:+.1f}%")
    return " · ".join(partes) if partes else None


# Tiempo en rango por interpolación lineal (Rosendaal FR, Cannegieter SC,
# van der Meer FJ, Briët E, "A method to determine the optimal intensity of
# oral anticoagulant therapy", Thromb Haemost 1993;69(3):236-9, PMID 8470047):
# entre dos analíticas consecutivas se supone que el valor cambia en línea
# recta, y se cuenta la fracción de días dentro del rango. Es el método de
# referencia del "tiempo en rango terapéutico" del INR, pensado justamente
# para mediciones a intervalos irregulares; el mismo concepto que el "time
# in range" de la glucosa continua (Battelino T et al., Diabetes Care
# 2019;42(8):1593-1603, doi:10.2337/dci19-0028). No se interpola en huecos
# de más de `TIR_MAX_GAP_DAYS` (no se sabe qué pasó en medio) y hace falta
# cubrir al menos `TIR_MIN_DAYS` días. Elecciones de interfaz, no clínicas.
TIR_MAX_GAP_DAYS = 365
TIR_MIN_DAYS = 365
_SIN_LIMITE = 1e12


def _normalized_point(s: dict[str, Any]) -> Optional[tuple[str, float, float, float]]:
    """(tipo de rango, valor normalizado, límite inferior, límite superior)
    en la misma escala para los dos extremos de un tramo: con dos límites,
    0 = inferior y 1 = superior; con uno solo, el valor dividido por él."""
    low, high, v = s.get("ref_low"), s.get("ref_high"), s.get("value_num")
    if v is None:
        return None
    if low is not None and high is not None and high > low:
        return "ambos", (v - low) / (high - low), 0.0, 1.0
    if high:
        return "superior", v / high, -_SIN_LIMITE, 1.0
    if low:
        return "inferior", v / low, 1.0, _SIN_LIMITE
    return None


def _fraction_inside(p0: float, p1: float, a: float, b: float) -> float:
    """Fracción de un tramo recto de p0 a p1 que cae dentro de [a, b]."""
    if p0 == p1:
        return 1.0 if a <= p0 <= b else 0.0
    t_a, t_b = (a - p0) / (p1 - p0), (b - p0) / (p1 - p0)
    return max(0.0, min(1.0, max(t_a, t_b)) - max(0.0, min(t_a, t_b)))


def time_in_range(series: list[dict[str, Any]]) -> Optional[tuple[float, int]]:
    """(% del tiempo dentro del rango, nº de huecos de más de
    `TIR_MAX_GAP_DAYS` que no se han contado) de la serie, con el rango de
    cada analítica (o el objetivo del médico, `apply_target`). `None` si los
    tramos contados no llegan a `TIR_MIN_DAYS` días."""
    dentro = total = 0.0
    huecos = 0
    for s0, s1 in zip(series, series[1:]):
        dias = (_parse_fecha(s1["fecha"]) - _parse_fecha(s0["fecha"])).days
        if dias <= 0:
            continue
        if dias > TIR_MAX_GAP_DAYS:
            huecos += 1
            continue
        n0, n1 = _normalized_point(s0), _normalized_point(s1)
        if not n0 or not n1 or n0[0] != n1[0]:
            continue  # sin rango, o con rangos de distinto tipo: no comparables
        dentro += dias * _fraction_inside(n0[1], n1[1], n0[2], n0[3])
        total += dias
    if total < TIR_MIN_DAYS:
        return None
    return dentro / total * 100, huecos


def series_summary(series: list[dict[str, Any]]) -> Optional[str]:
    """Resumen en lenguaje llano de la serie, descriptivo y nunca causal:
    "Dentro del rango en 9 de 10 analíticas; la última (2026-01-01), un 8 %
    por encima del límite superior." Los estudios con pacientes encuentran
    que una frase así ayuda a entender el resultado tanto o más que el
    propio gráfico (Morrow et al., J Exp Psychol Appl 2019;25(1):41-61,
    doi:10.1037/xap0000203; Shaffer et al., JAMIA Open 2026;9(2):ooag034,
    doi:10.1093/jamiaopen/ooag034). Cuenta solo los puntos con rango de
    referencia (el estado de cada uno es su `flag_calc`, calculado contra
    el rango de su propio informe); `None` si ninguno lo tiene."""
    con_rango = [s for s in series if s.get("ref_low") is not None or s.get("ref_high") is not None]
    if not con_rango:
        return None
    dentro = sum(1 for s in con_rango if s.get("flag_calc") not in ("alto", "bajo"))
    que = "del objetivo indicado por su médico" if series[0].get("objetivo") else "del rango"
    texto = f"Dentro {que} en {dentro} de {len(con_rango)} analíticas"
    tir = time_in_range(series)
    if tir:
        pct, huecos = tir
        texto += f" (~{pct:.0f} % del tiempo{', sin contar huecos de más de un año' if huecos else ''})"
    ultima = series[-1]
    fecha = (ultima.get("fecha") or "")[:10]
    valor, flag = ultima["value_num"], ultima.get("flag_calc")
    limite = ultima.get("ref_high") if flag == "alto" else ultima.get("ref_low") if flag == "bajo" else None
    if limite:
        pct = abs(valor - limite) / abs(limite) * 100
        lado = "por encima del límite superior" if flag == "alto" else "por debajo del límite inferior"
        texto += f"; la última ({fecha}), un {pct:.0f} % {lado} ({limite:g})"
    elif flag in ("alto", "bajo"):
        texto += f"; la última ({fecha}), fuera del rango"
    elif ultima.get("ref_low") is not None or ultima.get("ref_high") is not None:
        texto += f"; la última ({fecha}), dentro"
    texto += "."
    if series[0].get("objetivo"):
        # Línea aparte con el objetivo y la nota que le haya puesto la
        # persona (quién y cuándo se lo indicó), recortada para no ensanchar
        # el recuadro.
        lo, hi = ultima.get("ref_low"), ultima.get("ref_high")
        objetivo = (f"entre {lo:g} y {hi:g}" if lo is not None and hi is not None
                    else f"< {hi:g}" if hi is not None else f"> {lo:g}")
        unidad = next((s.get("unit") for s in series if s.get("unit")), "")
        nota = (series[0].get("objetivo_nota") or "").strip()
        if len(nota) > 60:
            nota = nota[:59] + "…"
        texto += f"\n{ETIQUETA_OBJETIVO}: {objetivo} {unidad}".rstrip() + (f" · {nota}" if nota else "")
    return texto


def _draw_info_box(
    ax,
    fit: Optional[tuple[float, float, Any]],
    valores: list[float],
    ref_low: Optional[float],
    ref_high: Optional[float],
    summary: Optional[str] = None,
    extra: Optional[str] = None,
) -> None:
    """Recuadro de texto bajo el eje con el resumen en texto de la serie
    (`series_summary`), la tendencia (si hay suficientes puntos) y la
    variación porcentual (si hay al menos 2) en líneas separadas. Anclado a
    `ax` (no a la figura), para que funcione igual en Evolución como en
    cada panel de la Comparativa; `annotation_clip=False` evita que se
    recorte al quedar fuera del área de datos."""
    lineas = [t for t in (summary, _trend_text(fit, valores, ref_low, ref_high), _pct_change_text(valores), extra)
              if t]
    if not lineas:
        return
    # Líneas largas partidas: si no, `tight_layout` estrecha todo el gráfico
    # para hacer sitio al recuadro.
    lineas = [textwrap.fill(parte, INFO_BOX_WIDTH) for linea in lineas for parte in linea.split("\n")]
    ax.analitix_info_lines = sum(linea.count("\n") + 1 for linea in lineas)  # ver `evolution_figure`
    ax.annotate(
        "\n".join(lineas),
        xy=(0.5, 0), xycoords="axes fraction",
        xytext=(0, -48), textcoords="offset points",
        ha="center", va="top", fontsize=8, color="#333333",
        bbox=dict(boxstyle="round", fc="white", ec="#cccccc", alpha=0.9),
        annotation_clip=False,
    )


def _apply_y_margin(ax, y_values: list[float]) -> None:
    """Amplía los límites del eje Y con un margen extra (`Y_MARGIN_RATIO`)
    sobre el autoescalado por defecto de matplotlib, que deja muy poco aire
    arriba/abajo — insuficiente para las etiquetas de los valores fuera de
    rango, dibujadas con un desplazamiento fijo en píxeles."""
    if not y_values:
        return
    data_min, data_max = min(y_values), max(y_values)
    span = (data_max - data_min) or abs(data_max) or 1.0
    margin = span * Y_MARGIN_RATIO
    ax.set_ylim(data_min - margin, data_max + margin)


def data_sufficiency(n_points: int, min_points: int = DEFAULT_MIN_POINTS) -> str:
    """Control común de "pocos datos" para cualquier gráfico de evolución
    (Evolución, Comparativa, paneles clínicos, PDF): "sin_datos" (0),
    "un_punto" (1: no se dibuja, no hay evolución que mostrar), "pocos"
    (de 2 a `min_points` − 1: se dibuja con aviso) o "suficiente".
    `min_points` es el umbral configurable de Configuración (mínimo 2)."""
    if n_points == 0:
        return "sin_datos"
    if n_points == 1:
        return "un_punto"
    return "pocos" if n_points < max(2, min_points) else "suficiente"


def _draw_single_point(ax, s: dict[str, Any]) -> None:
    """Con un único valor no se dibuja un gráfico (un punto suelto se lee
    como si hubiera una evolución): se muestra el valor como texto."""
    rango = ""
    if s.get("ref_low") is not None and s.get("ref_high") is not None:
        rango = f"\nRango de referencia: {s['ref_low']:g} – {s['ref_high']:g}"
    ax.text(
        0.5, 0.5,
        f"Solo hay 1 analítica con este parámetro ({(s.get('fecha') or '')[:10]}):\n"
        f"{s['value_num']:g} {s.get('unit') or ''}".rstrip() + rango
        + "\n\nHacen falta al menos 2 para ver una evolución.",
        transform=ax.transAxes, ha="center", va="center", fontsize=10, color=COLOR_INK_SECONDARY,
    )
    ax.set_xticks([])
    ax.set_yticks([])


def _draw_few_points_warning(ax, n_points: int, min_points: int) -> None:
    ax.text(
        0.01, 0.98,
        f"⚠ Solo {n_points} analíticas (mínimo recomendado: {min_points}): evolución poco representativa",
        transform=ax.transAxes, ha="left", va="top", fontsize=8, color=COLOR_BRUSCO,
        bbox=dict(boxstyle="round", fc="white", ec="#e1e0d9", alpha=0.9), zorder=5,
    )


def _plot_series_on_ax(
    ax, series: list[dict[str, Any]], label: str, base_color: str = COLOR_NORMAL,
    min_points: int = DEFAULT_MIN_POINTS,
) -> list:
    """Dibuja una serie sobre `ax` (línea, banda/límites de referencia, puntos
    coloreados según estén dentro o fuera de rango). Devuelve los handles de
    leyenda propios de esta serie. Aplica el control de pocos datos
    (`data_sufficiency`): sin gráfico con 1 valor, aviso por debajo de
    `min_points`."""
    suficiencia = data_sufficiency(len(series), min_points)
    if suficiencia == "sin_datos":
        ax.set_title(f"{label} (sin datos)")
        return []
    if suficiencia == "un_punto":
        _draw_single_point(ax, series[0])
        return []
    if suficiencia == "pocos":
        _draw_few_points_warning(ax, len(series), min_points)

    fechas = [_parse_fecha(s["fecha"]) for s in series]
    valores = [s["value_num"] for s in series]
    fit = _fit_trend(fechas, valores)
    y_extent = list(valores)

    ref_low = [s["ref_low"] for s in series if s["ref_low"] is not None]
    ref_high = [s["ref_high"] for s in series if s["ref_high"] is not None]
    handles = []
    if ref_low and ref_high:
        low_vals = [s["ref_low"] if s["ref_low"] is not None else min(ref_low) for s in series]
        high_vals = [s["ref_high"] if s["ref_high"] is not None else max(ref_high) for s in series]
        band_fechas, band_low, band_high = fechas, low_vals, high_vals
        if fit is not None:
            # La línea/banda de referencia se extiende hasta el final de la
            # proyección de tendencia, para no "cortarse" antes de que
            # termine el área visible del gráfico.
            proj_date = fechas[-1] + dt.timedelta(days=TREND_PROJECTION_DAYS)
            band_fechas = fechas + [proj_date]
            band_low = low_vals + [low_vals[-1]]
            band_high = high_vals + [high_vals[-1]]
        ax.fill_between(band_fechas, band_low, band_high, color=base_color, alpha=0.08)
        (h_low,) = ax.plot(band_fechas, band_low, linestyle="--", linewidth=1, color=base_color, alpha=0.6)
        (h_high,) = ax.plot(band_fechas, band_high, linestyle="--", linewidth=1, color=base_color, alpha=0.6)
        h_low.set_label(ETIQUETA_OBJETIVO if series[0].get("objetivo") else "Rango de referencia")
        handles.append(h_low)
        y_extent.extend(low_vals)
        y_extent.extend(high_vals)
    elif ref_low or ref_high:
        # Un solo límite ("< 130", "> 40"; típico del LDL o de un objetivo
        # del médico): solo su línea, sin banda, porque el otro lado no tiene
        # tope. Antes no se dibujaba nada.
        key, limits = ("ref_high", ref_high) if ref_high else ("ref_low", ref_low)
        limit_vals = [s[key] if s[key] is not None else limits[-1] for s in series]
        limit_fechas = fechas
        if fit is not None:
            limit_fechas = fechas + [fechas[-1] + dt.timedelta(days=TREND_PROJECTION_DAYS)]
            limit_vals = limit_vals + [limit_vals[-1]]
        (h_limit,) = ax.plot(limit_fechas, limit_vals, linestyle="--", linewidth=1, color=base_color, alpha=0.8)
        nombre = ETIQUETA_OBJETIVO if series[0].get("objetivo") else "Límite de referencia"
        h_limit.set_label(f"{nombre} ({'<' if key == 'ref_high' else '>'} {limit_vals[-1]:g})")
        handles.append(h_limit)
        y_extent.extend(limit_vals)

    (h_line,) = ax.plot(fechas, valores, color=base_color, linewidth=1.5, zorder=1)
    h_line.set_label(label)
    handles.append(h_line)

    estilos = [_point_style(s, base_color) for s in series]
    colors = [relleno for relleno, _ in estilos]
    edges = [contorno for _, contorno in estilos]
    # El color del punto ya dice su estado (alto/bajo/normal); el
    # laboratorio de origen va en la FORMA del punto, para no mezclar dos
    # significados en el color. Solo si la serie viene de más de un
    # laboratorio: un salto justo donde cambia la forma suele ser cambio de
    # método/laboratorio (o una unidad/alias mal normalizados), no del
    # paciente.
    labs = _labs_in_order(series)
    if len(labs) >= 2:
        for lab, marker in zip(labs, _markers_for(labs)):
            idx = [i for i, s in enumerate(series) if (s.get("lab") or LAB_UNKNOWN) == lab]
            scatter = ax.scatter(
                [fechas[i] for i in idx], [valores[i] for i in idx], c=[colors[i] for i in idx],
                marker=marker, s=50, zorder=2, edgecolors=[edges[i] for i in idx], linewidths=1.2,
            )
            # Datos para el tooltip al pasar el cursor (ver gui._attach_hover).
            scatter.analitix_series = [series[i] for i in idx]
            (h_lab,) = ax.plot([], [], linestyle="none", marker=marker, markersize=7, color=COLOR_INK_SECONDARY)
            h_lab.set_label(lab)
            handles.append(h_lab)
    else:
        scatter = ax.scatter(fechas, valores, c=colors, zorder=2, s=40, edgecolors=edges, linewidths=1.2)
        # Datos para el tooltip al pasar el cursor (ver gui._attach_hover).
        scatter.analitix_series = series

    # Último valor destacado (anillo + etiqueta): el estado actual es lo que
    # más se busca y no debe perderse entre el histórico ni la tendencia
    # (recomendación de Zikmund-Fisher, AHRQ 2017, no revisada por pares:
    # elección de interfaz, no un criterio clínico).
    ultimo = series[-1]
    color_ultimo = {"alto": COLOR_ALTO, "bajo": COLOR_BAJO}.get(ultimo["flag_calc"], COLOR_INK_SECONDARY)
    ax.scatter([fechas[-1]], [valores[-1]], s=170, facecolors="none", edgecolors=color_ultimo,
               linewidths=1.6, zorder=3)
    simbolo = SIMBOLO_ESTADO.get(ultimo["flag_calc"])
    # Al lado contrario de las etiquetas de los anteriores fuera de rango
    # (encima si alto, debajo si bajo), para no solaparse con ellas.
    xytext, ha, va = {"alto": ((0, -12), "center", "top"),
                      "bajo": ((0, 12), "center", "bottom")}.get(ultimo["flag_calc"], ((-10, 10), "right", "bottom"))
    ax.annotate(
        f"Último: {simbolo + ' ' if simbolo else ''}{valores[-1]:g}",
        (fechas[-1], valores[-1]), textcoords="offset points", xytext=xytext, ha=ha, va=va,
        fontsize=8, fontweight="bold", color=color_ultimo, zorder=4,
        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8),
    )

    for fecha, valor, s in zip(fechas[:-1], valores[:-1], series[:-1]):  # el último ya lleva etiqueta
        if s["flag_calc"] not in ("alto", "bajo"):
            continue
        alto = s["flag_calc"] == "alto"
        # ▲/▼ además del color (paleta apta para daltonismo): la forma del
        # punto ya está ocupada por el laboratorio, así que va en la etiqueta.
        ax.annotate(
            f"{SIMBOLO_ESTADO[s['flag_calc']]} {valor:g}",
            (fecha, valor),
            textcoords="offset points",
            xytext=(0, 8 if alto else -10),
            ha="center",
            va="bottom" if alto else "top",
            fontsize=8,
            fontweight="bold",
            color=COLOR_ALTO if alto else COLOR_BAJO,
        )

    _draw_trend_lines(ax, fit)
    _draw_info_box(
        ax, fit, valores, ref_low[-1] if ref_low else None, ref_high[-1] if ref_high else None,
        summary=series_summary(series), extra=_kdigo_note(series, fit),
    )
    _apply_y_margin(ax, y_extent)

    unit = next((s["unit"] for s in series if s.get("unit")), "")
    ax.set_ylabel(unit)
    return handles


def _draw_rcv_band(ax, series: list[dict[str, Any]], rcv: dict[str, Any]) -> None:
    """Banda de variación esperable (RCV, `rcv.classify_change`) en la fecha
    del último punto, centrada en el valor ANTERIOR: si el último punto cae
    dentro, el cambio cabe en la variación biológica + analítica esperable;
    si cae fuera, es probablemente real (no "patológico"). Con laboratorios
    distintos no se dibuja banda, solo se indica en la leyenda."""
    if rcv["estado"] == "otro_lab":
        (h,) = ax.plot([], [], linestyle="none")
        h.set_label("RCV no aplicable: el último valor es de otro laboratorio")
        return
    anterior = series[-2]["value_num"]
    bajo = anterior * (1 + rcv["rcv_bajada"] / 100)
    alto = anterior * (1 + rcv["rcv_subida"] / 100)
    x = _parse_fecha(series[-1]["fecha"])
    ax.errorbar(
        [x], [anterior], yerr=[[anterior - bajo], [alto - anterior]], fmt="none", ecolor=COLOR_INK_SECONDARY,
        elinewidth=6, capsize=0, alpha=0.25, zorder=1,
        label=f"Variación esperable desde el anterior (RCV {rcv['rcv_bajada']:+.0f}% / {rcv['rcv_subida']:+.0f}%)",
    )
    ymin, ymax = ax.get_ylim()
    ax.set_ylim(min(ymin, bajo), max(ymax, alto))


COLOR_PERSONAL = "#6b46c1"  # rango personal: distinto del verde/azul del rango del laboratorio


def _draw_personal_band(ax, series: list[dict[str, Any]], pr: dict[str, Any]) -> None:
    """Banda rayada del rango personal (`rcv.personal_range`) a lo ancho del
    periodo: más estrecha que la del laboratorio, porque mide cuánto
    varías TÚ. Salirse de ella no significa enfermedad si sigues dentro
    del rango del laboratorio."""
    fechas = [_parse_fecha(series[0]["fecha"]), _parse_fecha(series[-1]["fecha"])]
    varios = " · mezcla laboratorios" if pr["labs"] > 1 else ""
    ax.fill_between(
        fechas, [pr["bajo"]] * 2, [pr["alto"]] * 2, facecolor="none", edgecolor=COLOR_PERSONAL,
        hatch="///", linewidth=0.8, alpha=0.45, zorder=0,
        label=f"Tu rango personal {pr['bajo']:.3g}–{pr['alto']:.3g} (n={pr['n']}){varios}",
    )
    ymin, ymax = ax.get_ylim()
    ax.set_ylim(min(ymin, pr["bajo"]), max(ymax, pr["alto"]))


def evolution_figure(
    series: list[dict[str, Any]], title: str, min_points: int = DEFAULT_MIN_POINTS,
    rcv: Optional[dict[str, Any]] = None, personal: Optional[dict[str, Any]] = None,
) -> Figure:
    """Gráfico de evolución de una prueba en el tiempo, con las líneas de
    mínimo/máximo de referencia y los valores fuera de rango resaltados.
    `rcv` (opcional, `rcv.classify_change` de los dos últimos valores):
    añade la banda de variación esperable (`_draw_rcv_band`). `personal`
    (opcional, `rcv.personal_range`): añade la banda del rango personal
    (`_draw_personal_band`)."""
    fig = Figure(figsize=(8, 4.5), dpi=100)
    ax = fig.add_subplot(111)
    handles = _plot_series_on_ax(ax, series, title, min_points=min_points)
    if handles and personal:
        _draw_personal_band(ax, series, personal)
    if handles and rcv and len(series) >= 2:
        _draw_rcv_band(ax, series, rcv)
    ax.set_title(title)
    ax.tick_params(axis="x", rotation=30)
    if handles:
        ax.legend(fontsize=7)
    fig.tight_layout()
    # Deja sitio bajo el eje para el recuadro de tendencia/variación (hasta
    # dos líneas, ver `_draw_info_box`) además de las fechas rotadas; ambos
    # se dibujan fuera del área de datos. Con objetivo del médico o nota de
    # KDIGO pueden ser 4-5 líneas: el margen crece con ellas.
    fig.subplots_adjust(bottom=max(0.34, 0.16 + 0.05 * getattr(ax, "analitix_info_lines", 0)))
    return fig


def comparison_figure(
    series_by_test: dict[str, list[dict[str, Any]]], min_points: int = DEFAULT_MIN_POINTS
) -> Figure:
    """Compara hasta dos pruebas mediante "small multiples": un panel por
    prueba, cada uno con su propio eje Y, apilados y compartiendo el eje X
    (mismas fechas alineadas verticalmente). Evita el eje Y doble, que
    inventa una relación visual arbitraria entre dos escalas distintas."""
    items = list(series_by_test.items())[:MAX_COMPARISON_TESTS]
    n = max(1, len(items))

    fig = Figure(figsize=(8, 3.6 * n), dpi=100)
    axes = fig.subplots(n, 1, sharex=True, squeeze=False)

    for i, (label, series) in enumerate(items):
        ax = axes[i][0]
        color = COMPARISON_COLORS[i % len(COMPARISON_COLORS)]
        handles = _plot_series_on_ax(ax, series, label, base_color=color, min_points=min_points)
        ax.set_title(label)
        if handles:
            ax.legend(handles=handles, fontsize=7, loc="best")

    for row in axes:
        row[0].label_outer()
    axes[-1][0].tick_params(axis="x", rotation=30, labelbottom=True)
    fig.tight_layout()
    # Sitio para el recuadro de tendencia/variación de cada panel (hasta dos
    # líneas, se dibuja debajo de cada eje) y, en el último, también para las
    # fechas rotadas. `hspace` reserva ese mismo hueco entre paneles
    # intermedios: 0.8 es lo justo para las tres líneas (resumen en texto,
    # tendencia y variación) más el título del panel siguiente sin dejar un
    # espacio en blanco excesivo entre paneles.
    fig.subplots_adjust(bottom=0.34 / n, hspace=0.8)
    return fig


# -- Mapa de calor del historial ------------------------------------------
# Escala divergente (azul = por debajo del rango, gris neutro = dentro, rojo
# = por encima), una intensidad por lado. Codifica polaridad + distancia al
# rango, no estado clínico: por eso no reutiliza COLOR_ALTO/COLOR_BAJO de
# los puntos de Evolución, aunque comparte su polaridad (azul = bajo, rojo
# = alto). Azul↔rojo ya es apto para daltonismo.
HEATMAP_CMAP = LinearSegmentedColormap.from_list(
    "analitix_rango",
    [(0.0, "#184f95"), (0.35, "#9ec5f4"), (0.5, "#f0efec"), (0.65, "#f4b4b3"), (1.0, "#a3282a")],
)
HEATMAP_SURFACE = "#fcfcfb"      # casilla sin analítica ese día
HEATMAP_NO_RANGE = "#d9d8d2"     # valor medido pero sin rango de referencia
HEATMAP_INK = "#0b0b0b"
# Distancia fuera del rango, en fracciones del ancho del rango, a partir de
# la cual la casilla ya tiene el color más intenso; cualquier valor fuera de
# rango empieza en `HEATMAP_MIN_INTENSITY` para que nunca se confunda con el
# gris de "dentro del rango". Elección de lectura, no un umbral clínico.
HEATMAP_FULL_AT = 0.5
HEATMAP_MIN_INTENSITY = 0.3
# Con más columnas que esto no caben los valores escritos dentro de las
# casillas fuera de rango (quedan en el tooltip).
HEATMAP_MAX_LABELED_COLUMNS = 24


def range_position(value: Optional[float], ref_low: Optional[float], ref_high: Optional[float]) -> Optional[float]:
    """Posición de `value` respecto a su rango de referencia, en [-1, 1]: 0
    dentro del rango; negativo por debajo y positivo por encima, con
    magnitud `HEATMAP_MIN_INTENSITY`..1 según lo lejos que quede (1 = a
    `HEATMAP_FULL_AT` anchos de rango o más). Con un único límite ("< 200",
    "> 40") la distancia se mide en fracciones de ese límite. `None` si no
    hay valor o no hay ningún límite. Al depender solo del rango de cada
    informe, no importa la unidad (PCR en mg/L o mg/dL da lo mismo)."""
    distance = range_distance(value, ref_low, ref_high)
    if distance is None:
        return None
    if distance == 0:
        return 0.0
    intensity = HEATMAP_MIN_INTENSITY + (1 - HEATMAP_MIN_INTENSITY) * min(abs(distance) / HEATMAP_FULL_AT, 1.0)
    return -intensity if distance < 0 else intensity


def range_width(ref_low: Optional[float], ref_high: Optional[float]) -> Optional[float]:
    """Vara de medir de un rango: su ancho si tiene los dos límites; con un
    único límite ("< 200", "> 40"), el valor de ese límite. `None` si no hay
    ningún límite."""
    if ref_low is not None and ref_high is not None and ref_high > ref_low:
        return ref_high - ref_low
    bound = ref_high if ref_high is not None else ref_low
    return None if bound is None else (abs(bound) or 1.0)


def range_distance(value: Optional[float], ref_low: Optional[float], ref_high: Optional[float]) -> Optional[float]:
    """Distancia de `value` a su rango, en anchos de rango (`range_width`):
    0 dentro, negativa por debajo, positiva por encima. `None` sin valor o
    sin ningún límite. Compartida por el mapa de calor (`range_position`) y
    "Qué ha cambiado" (`change_status`)."""
    width = range_width(ref_low, ref_high)
    if value is None or width is None:
        return None
    if ref_low is not None and value < ref_low:
        return -(ref_low - value) / width
    if ref_high is not None and value > ref_high:
        return (value - ref_high) / width
    return 0.0


def _ink_for(rgba) -> str:
    """Color de texto que contrasta con el de la casilla: blanco sobre
    colores oscuros, casi negro sobre claros (luminancia relativa WCAG)."""
    def canal(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(float(c)) for c in rgba[:3])
    return "white" if 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.35 else HEATMAP_INK


def heatmap_figure(rows: list[tuple[str, list[dict[str, Any]]]], title: str) -> Figure:
    """Mapa de calor del historial: una fila por parámetro, una columna por
    fecha de analítica, color según la posición del valor respecto a su
    rango (`range_position`). `rows` son pares (etiqueta, serie) con la
    forma de `repository.get_series`; si un parámetro tiene dos valores el
    mismo día, cuenta el último. Guarda en `ax.analitix_heatmap` lo que
    necesita el tooltip de `gui.py` (fila/columna -> punto)."""
    rows = [(label, series) for label, series in rows if series]
    dates = sorted({s["fecha"][:10] for _, series in rows for s in series})
    n_rows, n_cols = max(len(rows), 1), max(len(dates), 1)
    col_of = {d: j for j, d in enumerate(dates)}

    rgba = np.empty((n_rows, n_cols, 4))
    rgba[:, :] = to_rgba(HEATMAP_SURFACE)
    cells: dict[tuple[int, int], dict[str, Any]] = {}
    positions: dict[tuple[int, int], Optional[float]] = {}
    for i, (_label, series) in enumerate(rows):
        for s in series:
            j = col_of[s["fecha"][:10]]
            cells[(i, j)] = s
            positions[(i, j)] = range_position(s["value_num"], s.get("ref_low"), s.get("ref_high"))
    for (i, j), pos in positions.items():
        rgba[i, j] = to_rgba(HEATMAP_NO_RANGE) if pos is None else HEATMAP_CMAP((pos + 1) / 2)

    width = max(8.0, min(16.0, 3.2 + 0.34 * n_cols))
    height = max(3.4, 0.3 * n_rows + 2.4)
    fig = Figure(figsize=(width, height), dpi=100)
    ax = fig.add_subplot(111)
    ax.imshow(rgba, aspect="auto", interpolation="nearest")

    # Separación de 2 px del color de fondo entre casillas.
    ax.set_xticks(np.arange(-0.5, n_cols, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_rows, 1), minor=True)
    ax.grid(which="minor", color=HEATMAP_SURFACE, linewidth=2)
    ax.tick_params(which="minor", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([label if len(label) <= 40 else label[:39] + "…" for label, _ in rows], fontsize=8)
    step = max(1, int(np.ceil(n_cols / 40)))
    ax.set_xticks(range(0, len(dates), step))
    ax.set_xticklabels([f"{d[8:10]}/{d[5:7]}/{d[2:4]}" for d in dates[::step]], rotation=90, fontsize=7)
    ax.tick_params(axis="both", length=0, colors="#52514e")

    # Etiquetas selectivas: el valor de las casillas fuera de rango. Con
    # muchas columnas no caben todas: solo los extremos de cada fila (el
    # valor más alto por encima del rango y el más bajo por debajo), para ver
    # hasta dónde ha llegado cada parámetro.
    if n_cols <= HEATMAP_MAX_LABELED_COLUMNS:
        etiquetadas = [k for k, pos in positions.items() if pos]
    else:
        etiquetadas = []
        for i in range(len(rows)):
            fuera = [(k, cells[k]["value_num"]) for k, pos in positions.items() if k[0] == i and pos]
            altos = [kv for kv in fuera if positions[kv[0]] > 0]
            bajos = [kv for kv in fuera if positions[kv[0]] < 0]
            if altos:
                etiquetadas.append(max(altos, key=lambda kv: kv[1])[0])
            if bajos:
                etiquetadas.append(min(bajos, key=lambda kv: kv[1])[0])
    for i, j in etiquetadas:
        ax.text(j, i, f"{cells[(i, j)]['value_num']:g}", ha="center", va="center", fontsize=6.5,
                color=_ink_for(rgba[i, j]), weight="bold")
    for (i, j), pos in positions.items():
        if pos is None:
            ax.plot(j, i, marker="o", markersize=2.5, color="#898781", linestyle="none")

    ax.set_title(title, fontsize=11, loc="left")
    legend = [
        Patch(facecolor=HEATMAP_CMAP(0.0), label="Muy bajo"),
        Patch(facecolor=HEATMAP_CMAP(0.35), label="Bajo"),
        Patch(facecolor=HEATMAP_CMAP(0.5), edgecolor="#c3c2b7", label="En rango"),
        Patch(facecolor=HEATMAP_CMAP(0.65), label="Alto"),
        Patch(facecolor=HEATMAP_CMAP(1.0), label="Muy alto"),
        Patch(facecolor=HEATMAP_NO_RANGE, label="Sin rango"),
        Patch(facecolor=HEATMAP_SURFACE, edgecolor="#c3c2b7", label="Sin analítica"),
    ]
    fig.legend(handles=legend, loc="lower center", ncol=len(legend), fontsize=7, frameon=False)
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    # Al pasarla a A4 (`export._fit_page_a4`) se recalculan los márgenes con
    # este mismo `rect`: las etiquetas largas de las filas no se cortan.
    fig.analitix_tight_rect = (0, 0.1, 1, 1)
    ax.analitix_heatmap = {"rows": [label for label, _ in rows], "dates": dates, "cells": cells}
    return fig


# -- "Qué ha cambiado": último informe frente al anterior ------------------
# Colores de estado (paleta de estado, reservada: no se usa para nada más en
# este gráfico) y siempre acompañados de símbolo + etiqueta, nunca solo color.
# Misma paleta apta para daltonismo que los puntos de Evolución. "✗" y no
# "▲" para empeora: ▲ ya significa "alto", y alejarse del rango también
# puede ser bajar.
CHANGE_WORSE = COLOR_ALTO     # se aleja del rango o sale de él
CHANGE_BETTER = COLOR_NORMAL  # se acerca al rango o vuelve a él
CHANGE_NEUTRAL = "#b9b8b0"    # dentro del rango antes y ahora
CHANGE_SYMBOL = {"empeora": "✗", "mejora": "✓", "igual": ""}
# Opacidad de las barras cuyo cambio cabe en la variación esperable (RCV,
# `rcv.py`): se ven, pero dejan destacar los cambios probablemente reales.
RCV_ESPERABLE_ALPHA = 0.35
# Diferencia de distancia al rango (en anchos) por debajo de la cual no se
# considera que se haya acercado ni alejado (evita colorear por redondeos).
CHANGE_EPSILON = 0.01


def change_status(previous: float, value: float, ref_low: Optional[float],
                  ref_high: Optional[float]) -> Optional[tuple[float, str]]:
    """(cambio en anchos de rango, estado) entre el valor anterior y el
    actual, ambos medidos contra el rango del informe actual. Estado:
    "empeora" (se aleja del rango o sale de él), "mejora" (se acerca o
    vuelve a él) o "igual" (dentro antes y ahora, o misma distancia). `None`
    si no hay rango con el que medir."""
    width = range_width(ref_low, ref_high)
    if width is None:
        return None
    before = abs(range_distance(previous, ref_low, ref_high))
    after = abs(range_distance(value, ref_low, ref_high))
    if after > before + CHANGE_EPSILON:
        estado = "empeora"
    elif after < before - CHANGE_EPSILON:
        estado = "mejora"
    else:
        estado = "igual"
    return (value - previous) / width, estado


def changes_figure(rows: list[dict[str, Any]], title: str) -> Figure:
    """Barras divergentes "Qué ha cambiado": una barra horizontal por
    parámetro con el cambio respecto al informe anterior en anchos del rango
    de referencia (comparable entre parámetros de escalas distintas; el %
    va en el tooltip), ordenadas de mayor a menor cambio, color según se
    acerque o se aleje del rango. `rows`: dicts con `label`, `value`,
    `previous`, `unit`, `ref_low`, `ref_high` (y opcionalmente `pct` y
    `rcv`, el resultado de `rcv.classify_change`: si el cambio cabe en la
    variación esperable, la barra se dibuja atenuada, conservando el color
    de si se acerca o se aleja del rango); los que no tienen anterior o
    rango se omiten. Guarda en `ax.analitix_changes` las filas en el orden
    dibujado, para el tooltip."""
    items = []
    unchanged = 0
    for r in rows:
        if r.get("previous") is None or r.get("value") is None:
            continue
        status = change_status(r["previous"], r["value"], r.get("ref_low"), r.get("ref_high"))
        if status is None:
            continue
        if abs(status[0]) < CHANGE_EPSILON and status[1] == "igual":
            unchanged += 1  # sin barra visible: solo ocuparía sitio
            continue
        items.append({**r, "delta": status[0], "estado": status[1]})
    items.sort(key=lambda r: abs(r["delta"]))  # el mayor cambio, arriba

    n = max(len(items), 1)
    fig = Figure(figsize=(9, max(3.2, 0.32 * n + 1.9)), dpi=100)
    ax = fig.add_subplot(111)
    colors = {"empeora": CHANGE_WORSE, "mejora": CHANGE_BETTER, "igual": CHANGE_NEUTRAL}
    y = np.arange(len(items))
    esperable = [(r.get("rcv") or {}).get("estado") == "esperable" for r in items]
    ax.barh(
        y, [r["delta"] for r in items], height=0.62, zorder=2,
        color=[to_rgba(colors[r["estado"]], RCV_ESPERABLE_ALPHA if e else 1.0) for r, e in zip(items, esperable)],
    )
    ax.axvline(0, color="#c3c2b7", linewidth=1, zorder=1)
    ax.set_yticks(y)
    ax.set_yticklabels([r["label"] if len(r["label"]) <= 40 else r["label"][:39] + "…" for r in items], fontsize=8)
    ax.set_ylim(-0.6, n - 0.4)

    # Margen a los dos lados para las etiquetas "anterior → actual".
    extent = max((abs(r["delta"]) for r in items), default=1.0) or 1.0
    ax.set_xlim(-extent * 1.45, extent * 1.45)
    for yi, r in zip(y, items):
        if r["estado"] == "igual":
            continue
        texto = f"{CHANGE_SYMBOL[r['estado']]} {r['previous']:g} → {r['value']:g}"
        right = r["delta"] >= 0
        ax.annotate(texto, (r["delta"], yi), xytext=(4 if right else -4, 0), textcoords="offset points",
                    ha="left" if right else "right", va="center", fontsize=7, color="#0b0b0b")

    ax.grid(axis="x", color="#e1e0d9", linewidth=0.8, zorder=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="both", colors="#52514e", length=0)
    ax.set_xlabel("Cambio respecto al informe anterior (1 = el ancho del rango de referencia)", fontsize=8,
                  color="#52514e")
    ax.set_title(title, fontsize=11, loc="left", pad=34)  # leyenda en 2 filas: cabe también en un A4 vertical
    legend = [
        Patch(facecolor=CHANGE_WORSE, label="✗ Se aleja del rango o sale de él"),
        Patch(facecolor=CHANGE_BETTER, label="✓ Se acerca al rango o vuelve a él"),
        Patch(facecolor=CHANGE_NEUTRAL, label="Dentro del rango antes y ahora"),
    ]
    if any(esperable):
        legend.append(Patch(facecolor=to_rgba(CHANGE_NEUTRAL, RCV_ESPERABLE_ALPHA),
                            label="Atenuada = dentro de la variación esperable (RCV)"))
    # Leyenda arriba, junto al título: con muchas filas la figura es alta y
    # abajo quedaría lejos de lo que explica.
    ax.legend(handles=legend, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2,
              fontsize=7, frameon=False,
              borderaxespad=0.2)
    fig.tight_layout()
    fig.analitix_tight_rect = (0, 0, 1, 1)  # ver heatmap_figure
    ax.analitix_changes = items
    ax.analitix_changes_unchanged = unchanged
    return fig


# -- Posición dentro del rango (gráfico de bala) ----------------------------
# Una fila por parámetro del último informe: la franja es su rango de
# referencia, el punto lleno el valor actual y el hueco el anterior, con una
# etiqueta verbal ("ligeramente alto"). Recta numérica con etiqueta verbal,
# sin marcar el centro del rango para no insinuar que es el valor óptimo
# (Zikmund-Fisher et al., JAMIA 2017;24(3):520-528, doi:10.1093/jamia/ocw169;
# barras horizontales más rápidas de leer que una tabla con muchos
# resultados: Brewer et al., Med Decis Making 2012;32(4):545-553,
# doi:10.1177/0272989X12441395).
POSITION_X_MIN, POSITION_X_MAX = -0.8, 1.8  # en anchos de rango; fuera, el punto se queda en el borde


def deviation_label(distance: float) -> str:
    """Palabra para la distancia al rango (`range_distance`, en anchos)."""
    if distance == 0:
        return "dentro del rango"
    lado = "alto" if distance > 0 else "bajo"
    if abs(distance) < DESVIACION_LEVE:
        return f"ligeramente {lado}"
    return f"muy {lado}" if abs(distance) >= DESVIACION_GRANDE else lado


def position_figure(rows: list[dict[str, Any]], title: str) -> Figure:
    """Gráfico de posición dentro del rango. `rows`: dicts con `label`,
    `value`, `previous` (o `None`), `unit`, `ref_low`, `ref_high`. Con solo
    límite superior ("< 200"), la escala empieza en 0; con solo límite
    inferior no hay escala y se omite (cuántos, en
    `ax.analitix_position_skipped`). Ordenado del más alejado del rango al
    más cercano."""
    items, skipped = [], 0
    for r in rows:
        low, high = r.get("ref_low"), r.get("ref_high")
        base = 0.0 if low is None else low
        if r.get("value") is None or high is None or high <= base:
            skipped += 1
            continue
        width = high - base
        d = range_distance(r["value"], low, high)
        items.append({**r, "distance": d, "pos": (r["value"] - base) / width,
                      "prev_pos": None if r.get("previous") is None else (r["previous"] - base) / width})
    items.sort(key=lambda r: (-abs(r["distance"]), r["label"]))

    n = max(len(items), 1)
    fig = Figure(figsize=(10, max(3.0, 0.34 * n + 1.6)), dpi=100)
    ax = fig.add_subplot(111)
    for i, r in enumerate(items):
        y = n - 1 - i
        ax.barh(y, 1, left=0, height=0.4, color=_tint(COLOR_NORMAL, 0.75), zorder=1)
        if r["prev_pos"] is not None:
            ax.plot(min(max(r["prev_pos"], POSITION_X_MIN), POSITION_X_MAX), y, marker="o", mfc="white",
                    mec=COLOR_INK_SECONDARY, ms=6, zorder=2, linestyle="none")
        flag = "alto" if r["distance"] > 0 else "bajo" if r["distance"] < 0 else None
        relleno, contorno = _point_style(
            {"flag_calc": flag, "value_num": r["value"], "ref_low": r["ref_low"], "ref_high": r["ref_high"]},
            COLOR_NORMAL,
        )
        x = min(max(r["pos"], POSITION_X_MIN), POSITION_X_MAX)
        marker = ">" if r["pos"] > POSITION_X_MAX else "<" if r["pos"] < POSITION_X_MIN else "o"
        ax.scatter([x], [y], s=70, c=[relleno], edgecolors=[contorno], linewidths=1.4, marker=marker, zorder=3)
        simbolo = SIMBOLO_ESTADO.get(flag, "")
        texto = f"{simbolo + ' ' if simbolo else ''}{deviation_label(r['distance'])} · {r['value']:g} {r.get('unit') or ''}"
        ax.text(POSITION_X_MAX + 0.08, y, texto.rstrip(), va="center", fontsize=8,
                color=contorno if flag else COLOR_INK_SECONDARY)
    ax.set_yticks(range(n))
    ax.set_yticklabels([r["label"] if len(r["label"]) <= 40 else r["label"][:39] + "…" for r in reversed(items)],
                       fontsize=8)
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlim(POSITION_X_MIN, POSITION_X_MAX + 1.6)
    ax.set_xticks([0, 1], ["límite inferior", "límite superior"], fontsize=7, color=COLOR_INK_SECONDARY)
    ax.tick_params(axis="both", length=0)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.set_title(title, fontsize=11, loc="left", pad=30)
    legend = [
        Patch(facecolor=_tint(COLOR_NORMAL, 0.75), label="Rango de referencia del laboratorio"),
        Line2D([], [], marker="o", linestyle="none", mfc=COLOR_ALTO, mec=COLOR_ALTO, label="Último valor"),
        Line2D([], [], marker="o", linestyle="none", mfc=_tint(COLOR_ALTO), mec=COLOR_ALTO,
               label="Más claro = desviación leve"),
        Line2D([], [], marker="o", linestyle="none", mfc="white", mec=COLOR_INK_SECONDARY, label="Valor anterior"),
    ]
    ax.legend(handles=legend, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=4, fontsize=7, frameon=False,
              borderaxespad=0.2)
    fig.tight_layout()
    fig.analitix_tight_rect = (0, 0, 1, 1)  # ver heatmap_figure
    ax.analitix_positions = items
    ax.analitix_position_skipped = skipped
    return fig
