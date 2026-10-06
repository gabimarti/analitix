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
from typing import Any, Optional

import matplotlib.dates as mdates
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, to_rgba
from matplotlib.figure import Figure
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

# Colores base de cada panel de la comparativa (paneles separados: solo
# decorativos, pero sin coincidir con el azul de "bajo").
COMPARISON_COLORS = [COLOR_NORMAL, "#CC79A7"]

MAX_COMPARISON_TESTS = 2

# Puntos mínimos para calcular una recta de tendencia; con menos, una regresión
# lineal no es fiable y no se dibuja.
MIN_POINTS_FOR_TREND = 3
TREND_PROJECTION_DAYS = 90

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


def _fit_trend(fechas: list[dt.datetime], valores: list[float]) -> Optional[tuple[float, float, Any]]:
    """Ajuste de regresión lineal simple (valor ~ fecha). `None` si hay menos
    de `MIN_POINTS_FOR_TREND` puntos (con tan pocos, una regresión no es
    fiable)."""
    if len(fechas) < MIN_POINTS_FOR_TREND:
        return None
    x = mdates.date2num(fechas)
    slope, intercept = np.polyfit(x, valores, 1)
    return slope, intercept, x


def _draw_trend_lines(ax, fit: Optional[tuple[float, float, Any]]) -> None:
    """Dibuja la recta de tendencia ajustada por `_fit_trend` y su proyección
    a `TREND_PROJECTION_DAYS` días vista (sin texto, ver `_trend_text`)."""
    if fit is None:
        return
    slope, intercept, x = fit

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
    slope, intercept, x = fit

    # Umbral de "estable": un cambio, a lo largo de todo el periodo observado,
    # menor al 5% del rango de referencia (o del propio rango de valores si no
    # hay rango de referencia) no se considera una tendencia real. El mismo
    # `span` sirve de vara de medir para la magnitud (leve/brusca) de una
    # tendencia real: cuánto rango normal se recorre por año.
    span = (ref_high - ref_low) if (ref_low is not None and ref_high is not None and ref_high > ref_low) else None
    if span is None:
        span = (max(valores) - min(valores)) or abs(valores[-1]) or 1.0
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
    _, intercept, x = fit
    x_proj_end = x[-1] + TREND_PROJECTION_DAYS
    rate_per_year = slope * 365.25
    proyeccion = slope * x_proj_end + intercept
    return f"{arrow} Tendencia: {palabra} (~{rate_per_year:+.2g}/año) · proy. 3 meses: {proyeccion:.3g}"


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
    if direction is None:
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
    texto = f"Dentro del rango en {dentro} de {len(con_rango)} analíticas"
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
    return texto + "."


def _draw_info_box(
    ax,
    fit: Optional[tuple[float, float, Any]],
    valores: list[float],
    ref_low: Optional[float],
    ref_high: Optional[float],
    summary: Optional[str] = None,
) -> None:
    """Recuadro de texto bajo el eje con el resumen en texto de la serie
    (`series_summary`), la tendencia (si hay suficientes puntos) y la
    variación porcentual (si hay al menos 2) en líneas separadas. Anclado a
    `ax` (no a la figura), para que funcione igual en Evolución como en
    cada panel de la Comparativa; `annotation_clip=False` evita que se
    recorte al quedar fuera del área de datos."""
    lineas = [t for t in (summary, _trend_text(fit, valores, ref_low, ref_high), _pct_change_text(valores)) if t]
    if not lineas:
        return
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
        h_low.set_label("Rango de referencia")
        handles.append(h_low)
        y_extent.extend(low_vals)
        y_extent.extend(high_vals)

    (h_line,) = ax.plot(fechas, valores, color=base_color, linewidth=1.5, zorder=1)
    h_line.set_label(label)
    handles.append(h_line)

    colors = [
        COLOR_ALTO if s["flag_calc"] == "alto" else COLOR_BAJO if s["flag_calc"] == "bajo" else base_color
        for s in series
    ]
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
                marker=marker, s=50, zorder=2, edgecolors="white", linewidths=1,
            )
            # Datos para el tooltip al pasar el cursor (ver gui._attach_hover).
            scatter.analitix_series = [series[i] for i in idx]
            (h_lab,) = ax.plot([], [], linestyle="none", marker=marker, markersize=7, color=COLOR_INK_SECONDARY)
            h_lab.set_label(lab)
            handles.append(h_lab)
    else:
        scatter = ax.scatter(fechas, valores, c=colors, zorder=2, s=40)
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
        summary=series_summary(series),
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
    # se dibujan fuera del área de datos.
    fig.subplots_adjust(bottom=0.34)
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
