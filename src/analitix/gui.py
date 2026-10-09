# ---------------------------------------------------------------------------
# Script: gui.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-10-06
# ---------------------------------------------------------------------------
"""Interfaz gráfica (Tkinter/ttkbootstrap) de Analitix."""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import re
import logging
import os
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

import mplcursors
import ttkbootstrap as ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from analitix.branding import load_logo_photo, set_app_icon
from analitix.calcium_risk import (
    INDEX_LABELS as CALCIUM_INDEX_LABELS,
    get_calcium_index_series,
    get_latest_calcium_summary,
)
from analitix.catalog import get_description
from analitix.charts import (
    COLOR_ALTO,
    COLOR_BAJO,
    COLOR_BRUSCO,
    DEFAULT_MIN_POINTS,
    LAB_UNKNOWN,
    MAX_COMPARISON_TESTS,
    apply_target,
    bp_figure,
    change_status,
    changes_figure,
    comparison_figure,
    data_sufficiency,
    evolution_figure,
    heatmap_figure,
    position_figure,
    trend_arrow,
)
from analitix import __version__
from analitix.blood_pressure import (
    ABSOLUTE_LIMITS as BP_ABSOLUTE_LIMITS,
    CSV_TEMPLATE as BP_CSV_TEMPLATE,
    DEFAULT_LIMITS as BP_DEFAULT_LIMITS,
    LIMIT_NAMES as BP_LIMIT_NAMES,
    PLACES as BP_PLACES,
    check_limits as check_bp_limits,
    read_csv as read_bp_csv,
    MEASUREMENT_GUIDE as BP_MEASUREMENT_GUIDE,
    bp_summary_text,
    period_stats as bp_period_stats,
    validate_reading,
)
from analitix.config import DB_PATH, FROZEN, PROJECT_ROOT, REPORTS_DIR, copy_home, set_installed_home_dir
from analitix.db import rekey
from analitix.export import export_csv, export_excel, export_pages_pdf, export_pdf, table_page, text_page
from analitix.glycemic_risk import (
    ADA_NORMAL_HIGH,
    ADA_DIABETES_LOW,
    INDEX_LABELS as GLYCEMIC_INDEX_LABELS,
    get_glucose_series,
    get_glycemic_index_series,
    get_latest_glycemic_summary,
)
from analitix.hemogram_risk import (
    INDEX_LABELS as HEMOGRAM_INDEX_LABELS,
    LYMPHOCYTOSIS_HIGH,
    get_hemogram_index_series,
    get_latest_hemogram_summary,
    get_sustained_lymphocytosis_alert,
)
from analitix.hepatic_risk import (
    INDEX_LABELS as HEPATIC_INDEX_LABELS,
    get_hepatic_index_series,
    get_latest_hepatic_summary,
)
from analitix.inflammation_risk import get_inflammation_series, get_latest_inflammation_summary
from analitix.ingest import ingest_folder, known_pdf_filenames
from analitix.iron_risk import (
    INDEX_LABELS as IRON_INDEX_LABELS,
    get_iron_index_series,
    get_latest_iron_summary,
)
from analitix.lipid_risk import INDEX_LABELS as LIPID_INDEX_LABELS, get_latest_lipid_summary, get_lipid_index_series
from analitix.renal_risk import (
    FG_IDS,
    INDEX_LABELS as RENAL_INDEX_LABELS,
    KDIGO_RISK_LABELS,
    get_latest_renal_summary,
    get_renal_index_series,
)
from analitix.repository import (
    EXPLORABLE_TABLES,
    SEX_OPTIONS,
    add_bp_reading,
    create_manual_report,
    delete_all_data,
    delete_bp_readings,
    delete_patient,
    delete_target,
    delete_reports,
    get_all_results,
    get_excluded_labs,
    get_latest_report_summary,
    get_merged_series,
    get_patient_sex,
    get_series,
    get_setting,
    get_target,
    get_stats,
    get_table_rows,
    list_canonical_groups,
    list_canonical_tests,
    list_files_needing_review,
    list_bp_readings,
    list_known_test_names,
    list_labs,
    list_orphan_reports,
    list_patient_reports,
    list_patients,
    merge_canonical_ids,
    merge_check,
    merge_patients,
    set_excluded_labs,
    set_setting,
    set_target,
    update_patient,
)
from analitix import (
    calcium_risk as _calcium,
    glycemic_risk as _glycemic,
    hemogram_risk as _hemogram,
    hepatic_risk as _hepatic,
    inflammation_risk as _inflammation,
    iron_risk as _iron,
    lipid_risk as _lipid,
    renal_risk as _renal,
    thyroid_risk as _thyroid,
    uric_acid_risk as _uric,
)
from analitix.rcv import classify_change, cusum_drift, cusum_note, personal_range
from analitix.textutils import strip_accents
from analitix.tyg_risk import INDEX_LABELS as TYG_INDEX_LABELS, get_tyg_series
from analitix.thyroid_risk import get_latest_thyroid_summary, get_thyroid_series
from analitix.updates import RELEASES_URL, REPO_URL, fetch_latest_release, is_newer
from analitix.uric_acid_risk import (
    INDEX_LABELS as URIC_ACID_INDEX_LABELS,
    URATE_LOWERING_TARGET,
    get_latest_uric_acid_summary,
    get_uric_acid_series,
)

logger = logging.getLogger("analitix.gui")


# Filas del mapa de calor por panel clínico: las mismas tuplas de
# `canonical_id` que usa cada panel, así el mapa enseña exactamente los datos
# con los que ese panel calcula (una fila por tupla, variantes ya fusionadas).
HEATMAP_OUT_OF_RANGE = "Parámetros alguna vez fuera de rango"
HEATMAP_ALL = "Todos los parámetros"
# Cada fila lleva un nombre fijo y legible, en vez del nombre crudo del
# último informe (que cambia de laboratorio a laboratorio: "San-Hematies,
# c. nom.", "Hematíes"...).
HEATMAP_SETS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "Panel: Riesgo cardiovascular": (
        ("Colesterol total", _lipid.TOTAL_IDS), ("Colesterol HDL", _lipid.HDL_IDS),
        ("Colesterol LDL", _lipid.LDL_IDS), ("Colesterol no HDL", _lipid.NON_HDL_IDS),
        ("Colesterol VLDL", _lipid.VLDL_IDS), ("Triglicéridos", _lipid.TG_IDS),
    ),
    "Panel: Salud hepática": (
        ("AST (GOT)", _hepatic.AST_IDS), ("ALT (GPT)", _hepatic.ALT_IDS), ("Plaquetas", _hepatic.PLAQUETES_IDS),
    ),
    "Panel: Función renal": (
        ("Filtrado glomerular", _renal.FG_IDS), ("Creatinina", _renal.CREATININA_IDS),
        ("Urea", _renal.UREA_IDS), ("Albúmina/creatinina (orina)", _renal.ACR_IDS),
    ),
    "Panel: Hemograma": (
        ("Hematíes", _hemogram.HEMATIES_IDS), ("VCM", _hemogram.VCM_IDS), ("RDW", _hemogram.RDW_IDS),
        ("Neutrófilos (absoluto)", _hemogram.NEUTROFILS_IDS), ("Linfocitos (absoluto)", _hemogram.LIMFOCITS_IDS),
        ("Monocitos (absoluto)", _hemogram.MONOCITS_IDS), ("Plaquetas", _hemogram.PLAQUETES_IDS),
    ),
    "Panel: Metabolismo del hierro": (
        ("Hierro", _iron.FERRO_IDS), ("Ferritina", _iron.FERRITINA_IDS),
        ("Transferrina", _iron.TRANSFERRINA_IDS), ("Saturación de transferrina", _iron.TSAT_IDS),
    ),
    "Panel: Inflamación": (("PCR", _inflammation.PCR_IDS), ("VSG", _inflammation.VSG_IDS)),
    "Panel: Ácido úrico": (("Ácido úrico", _uric.URIC_ACID_IDS),),
    "Panel: Calcio": (("Calcio", _calcium.CALCI_IDS), ("Albúmina", _calcium.ALBUMINA_IDS)),
    "Panel: Glucemia": (("Glucosa", _glycemic.GLUCOSA_IDS), ("HbA1c", _glycemic.HBA1C_IDS)),
    "Panel: Tiroides": (("TSH", _thyroid.TSH_IDS), ("T4 libre", _thyroid.T4L_IDS)),
}
# Con más filas que esto el mapa se muestra con barra de desplazamiento en
# vez de comprimir las casillas al alto de la ventana.
HEATMAP_SCROLL_ROWS = 16


def _format_range(item: dict) -> str:
    low, high = item.get("ref_low"), item.get("ref_high")
    if low is not None and high is not None:
        return f"{low:g} – {high:g}"
    if high is not None:
        return f"< {high:g}"
    if low is not None:
        return f"> {low:g}"
    return "sin rango"


def _rcv_tooltip(rcv: Optional[dict]) -> str:
    """Líneas del RCV (`rcv.classify_change`) para el tooltip de "Qué ha
    cambiado"; "" si no hay variación biológica para el parámetro."""
    if not rcv:
        return ""
    limites = f"RCV {rcv['rcv_bajada']:+.0f}% / {rcv['rcv_subida']:+.0f}%"
    texto = {
        "real": f"Cambio probablemente real (supera el {limites})",
        "esperable": f"Dentro de la variación esperable ({limites})",
        "otro_lab": "⚠ Laboratorios distintos: no se valora con el RCV",
    }[rcv["estado"]]
    nota = f"\n{rcv['nota']}" if rcv.get("nota") else ""
    return f"\n{texto}\nFuente: {rcv['fuente']}{nota}"


# Contacto preferente del proyecto ("Acerca de"): alias de correo propio del
# proyecto, que no expone ningún correo personal.
CONTACT_EMAIL = "contact@analitix.slmail.me"

# Paneles que se pueden incluir en el informe PDF personalizado: clave de sus
# atributos en `AnalitixApp` (`text_<clave>_summary`, `_<clave>_series`,
# `_<clave>_indices`) y nombre del menú Paneles clínicos.
PDF_PANELS = (
    ("lipid", "Riesgo cardiovascular"), ("hepatic", "Salud hepática"), ("renal", "Función renal"),
    ("hemogram", "Hemograma"), ("iron", "Metabolismo del hierro"), ("inflammation", "Inflamación"),
    ("uric_acid", "Ácido úrico"), ("calcio", "Calcio corregido"), ("glucemia", "Glucosa (eAG y TyG)"),
    ("thyroid", "Tiroides"),
)
# Máximo de parámetros por página en el PDF personalizado ("Qué ha cambiado"
# y mapa de calor): con más se reparten en varias páginas, cada una con su
# título "(1/2)", su leyenda y su eje, para que quepan legibles en un A4.
PDF_ROWS_PER_PAGE = 25

# Paneles sin lista de índices: su gráfico es el combinado (serie → nombre).
PDF_COMBINED_PANELS = {"inflammation": {"pcr": "PCR", "vsg": "VSG"}, "thyroid": {"tsh": "TSH", "t4l": "T4 libre"}}

def _pages_of(filas: list) -> list[tuple[list, str]]:
    """Reparte `filas` en trozos de `PDF_ROWS_PER_PAGE` para el PDF, con el
    sufijo de título de cada uno (" (1/2)"...; vacío si cabe en una)."""
    trozos = [filas[i:i + PDF_ROWS_PER_PAGE] for i in range(0, len(filas), PDF_ROWS_PER_PAGE)]
    if len(trozos) <= 1:
        return [(t, "") for t in trozos]
    return [(t, f" ({n}/{len(trozos)})") for n, t in enumerate(trozos, start=1)]


def _check_period(desde: str, hasta: str) -> tuple[str | None, str | None] | None:
    """(desde, hasta) de dos campos de fecha, `None` si los dos están
    vacíos, o `ValueError` si una fecha no es AAAA-MM-DD válida o están al
    revés."""
    desde, hasta = desde.strip() or None, hasta.strip() or None
    if desde is None and hasta is None:
        return None
    for fecha in (desde, hasta):
        if fecha is not None:
            try:
                dt.date.fromisoformat(fecha)
            except ValueError:
                raise ValueError(f"«{fecha}» no es una fecha válida") from None
    if desde and hasta and desde > hasta:
        raise ValueError("la fecha «desde» es posterior a «hasta»")
    return desde, hasta


def _same_size(figuras: list) -> list:
    """Las páginas de una misma sección repartida (`_pages_of`) toman el
    tamaño de la primera: así todas salen con la misma orientación A4 y la
    última, con menos filas, no cambia de vertical a apaisado."""
    for fig in figuras[1:]:
        fig.set_size_inches(*figuras[0].get_size_inches())
    return figuras


# Ayuda → documentación (rutas dentro del repositorio público, `REPO_URL`).
DOC_LINKS = (
    ("Manual de usuario", "blob/main/docs/MANUAL_USUARIO.md"),
    ("Documentación técnica", "blob/main/docs/DOCUMENTACION_TECNICA.md"),
    ("Referencias científicas", "tree/main/docs/referencias_medicas"),
    ("Registro de cambios", "blob/main/CHANGELOG.md"),
)


def _make_sortable(tree: ttk.Treeview, numeric_columns: set[str] = frozenset()) -> None:
    """Clic en la cabecera de una columna = ordenar por ella (otro clic
    invierte el orden, ▲/▼ en la cabecera). Texto sin distinguir
    mayúsculas ni acentos, para que las variantes de un mismo nombre queden
    juntas; `numeric_columns` se ordenan como número."""
    labels = {col: tree.heading(col, "text") for col in tree["columns"]}

    def _sort(col: str, reverse: bool) -> None:
        def key(iid: str):
            value = tree.set(iid, col)
            if col in numeric_columns:
                try:
                    return float(value)
                except ValueError:
                    return float("-inf")
            return strip_accents(str(value)).casefold()

        for index, iid in enumerate(sorted(tree.get_children(""), key=key, reverse=reverse)):
            tree.move(iid, "", index)
        for other, text in labels.items():
            arrow = (" ▼" if reverse else " ▲") if other == col else ""
            tree.heading(other, text=text + arrow)
        tree.heading(col, command=lambda: _sort(col, not reverse))
        state["last"] = (col, reverse)

    state: dict = {}
    for col in labels:
        tree.heading(col, command=lambda c=col: _sort(c, False))
    # Tras recargar las filas, `tree._resort()` reaplica el último orden elegido.
    tree._resort = lambda: _sort(*state["last"]) if "last" in state else None  # type: ignore[attr-defined]


def _smoking_summary(patient: dict) -> str:
    """Resumen de una línea del tabaquismo para la lista de pacientes."""
    parts = []
    if patient.get("smoker_current") == 1:
        parts.append("Fumador")
    if patient.get("smoker_former") == 1:
        desde, hasta = patient.get("smoker_former_from"), patient.get("smoker_former_to")
        periodo = f"{desde or '?'}-{hasta or '?'}" if desde or hasta else patient.get("smoker_former_period")
        parts.append(f"Exfumador ({periodo})" if periodo else "Exfumador")
    if not parts and (patient.get("smoker_current") == 0 or patient.get("smoker_former") == 0):
        parts.append("No fumador")
    return ", ".join(parts)

THEME = "flatly"
PAD = 12
# Ancho (en caracteres) de la lista de la columna izquierda de Análisis y
# Paneles clínicos: fija el ancho de toda la columna (ver `_list_column`).
LIST_COLUMN_CHARS = 38
# Casillas de las tablas con selección múltiple (ver `_checkbox_tree`).
CHECK_ON, CHECK_OFF = "☑", "☐"
# Texto de lo alguna vez fuera de rango y de lo secundario en las listas.
COLOR_ALTERADO, COLOR_GRIS = COLOR_ALTO, "#999999"

# Umbral de "cambio brusco" de la pestaña Resumen y la exportación a PDF
# ("±30%"). Elección de interfaz, no un punto de corte clínico — no
# necesita cita científica, a diferencia de los umbrales de los paneles
# clínicos. `COLOR_BRUSCO` vive en `charts.py` (reutilizado también por
# `export.export_pdf`).
CAMBIO_BRUSCO_PCT = 30.0

# Botones de periodo del panel de tensión arterial (días hacia atrás desde hoy).
BP_RANGOS = (("10d", "Últimos 10 días"), ("1m", "Último mes"), ("3m", "Últimos 3 meses"),
             ("1a", "Último año"), ("todo", "Todo"), ("intervalo", "Elegir intervalo de fechas"))
BP_RANGO_DIAS = {"10d": 10, "1m": 31, "3m": 92, "1a": 365}

# Aviso común de las pantallas de entrada manual (analíticas y tensión).
AVISO_ENTRADA_MANUAL = (
    "⚠ Los gráficos, cálculos e informes de Analitix se basan en los datos que introduces aquí. "
    "Revísalos antes de guardar: un valor mal escrito (por ejemplo 18 en vez de 180, o la unidad "
    "equivocada) daría gráficos, resúmenes e informes erróneos. La aplicación solo comprueba que los "
    "valores sean posibles, no que sean correctos."
)

# Años que muestran por defecto los gráficos de evolución (contados hacia
# atrás desde la última analítica de cada parámetro); el interruptor "Ver
# todo el histórico" los amplía. Elección de interfaz para que el estado
# actual no quede comprimido por valores muy antiguos (recomendación de
# Zikmund-Fisher, AHRQ 2017, no revisada por pares), no un criterio clínico.
HISTORY_YEARS = 5

STATS_LABELS = [
    ("num_patients", "Pacientes"),
    ("num_reports", "Informes importados"),
    ("num_results", "Registros (resultados)"),
    ("num_results_out_of_range", "Resultados fuera de rango"),
    ("fecha_min", "Informe más antiguo"),
    ("fecha_max", "Informe más reciente"),
    ("num_files_ok", "Ficheros importados sin error"),
    ("num_files_review", "Ficheros pendientes de revisión"),
    ("num_files_error", "Ficheros con error de importación"),
]


class AnalitixApp(ttk.Window):
    def __init__(self, con):
        super().__init__(title=f"Analitix {__version__} — análisis de informes de laboratorio", themename=THEME)
        self.con = con
        # +15% sobre el tamaño original (1100x700/900x600): con el tamaño
        # anterior, algunas etiquetas de los gráficos de Evolución/
        # Riesgo cardiovascular/Salud hepática/Función renal/Hemograma se
        # superponían o quedaban cortadas.
        self.geometry("1265x805")
        self.minsize(1035, 690)
        set_app_icon(self)

        self.patients: list[dict] = []
        # Paciente activo: el único con el que trabaja toda la app (Análisis,
        # Paneles clínicos, Exportar y Entrada manual). Se elige en el
        # diálogo "Seleccionar paciente activo" (al iniciar si hay varios, o
        # con Pacientes → Cambiar paciente activo...), que solo muestra el
        # nombre. Deliberadamente NO persiste entre sesiones (siempre None al
        # arrancar): así nunca se analizan ni se anotan datos de un paciente
        # que quedó elegido de la sesión anterior sin volver a confirmarlo.
        # La fila seleccionada en la tabla Pacientes solo sirve para ver/
        # editar/eliminar/fusionar fichas y no cambia el paciente activo.
        self.current_patient_id: int | None = None
        self._active_cursor = None
        # Creado aquí (antes de `_build_pages`) para poder mostrar el
        # paciente activo directamente en el contenido de las pestañas de
        # Análisis (Riesgo cardiovascular, Salud hepática), no solo en la
        # barra de estado inferior — un único `StringVar` mantiene todas
        # las etiquetas sincronizadas sin código duplicado, actualizado
        # desde `_update_status_patient`.
        self.status_var = tk.StringVar(value="Ningún paciente activo")
        self.reports_dir = Path(get_setting(self.con, "reports_dir", str(REPORTS_DIR)))
        # Variable compartida entre la pestaña Importar y Configuración → General
        # (misma carpeta, dos sitios desde donde cambiarla): un único StringVar
        # mantiene ambas etiquetas sincronizadas sin código duplicado.
        self.var_reports_dir = tk.StringVar(value=str(self.reports_dir))
        self.var_import_subfolders = tk.BooleanVar(value=get_setting(self.con, "import_subfolders", "1") == "1")
        self.min_points = int(get_setting(self.con, "min_points_evolucion", str(DEFAULT_MIN_POINTS)))
        # Rango personal (`rcv.personal_range`) en el gráfico de Evolución:
        # desactivado por defecto, se activa con su interruptor en esa pantalla.
        self.var_personal_range = tk.BooleanVar(value=get_setting(self.con, "personal_range", "0") == "1")
        self.var_full_history = tk.BooleanVar(value=get_setting(self.con, "full_history", "0") == "1")
        # Laboratorios excluidos de gráficos y paneles (Análisis → Laboratorios
        # incluidos...): se guardan en `settings` y se cargan en la tabla
        # temporal de la conexión que filtra las consultas (`repository`).
        set_excluded_labs(self.con, json.loads(get_setting(self.con, "excluded_labs", "[]")))

        self._build_menu()
        self._build_pages()
        self._build_statusbar()
        self._refresh_patients()
        self.after(100, self._prompt_active_patient_if_needed)
        if get_setting(self.con, "check_updates_on_start", "0") == "1":
            self.after(1000, lambda: self._check_updates(manual=False))

    # -- estructura general -------------------------------------------------
    def _build_menu(self) -> None:
        menubar = tk.Menu(self)

        archivo = tk.Menu(menubar, tearoff=0)
        archivo.add_command(label="Importar", command=lambda: self._show_page("importar"))
        archivo.add_command(label="Exportar", command=lambda: self._show_page("exportar"))
        archivo.add_separator()
        archivo.add_command(label="Salir", command=self.destroy)
        menubar.add_cascade(label="Archivo", menu=archivo)

        pacientes_menu = tk.Menu(menubar, tearoff=0)
        pacientes_menu.add_command(label="Cambiar paciente activo...", command=self._choose_active_patient)
        pacientes_menu.add_command(label="Pacientes", command=lambda: self._show_page("pacientes"))
        menubar.add_cascade(label="Pacientes", menu=pacientes_menu)

        # Datos que introduce la persona a mano (siempre para el paciente
        # activo), separados de Pacientes.
        entrada_menu = tk.Menu(menubar, tearoff=0)
        entrada_menu.add_command(label="Analíticas...", command=lambda: self._show_page("manual"))
        entrada_menu.add_command(label="Tensión arterial...", command=lambda: self._show_page("tension"))
        menubar.add_cascade(label="Entrada manual", menu=entrada_menu)

        analisis_menu = tk.Menu(menubar, tearoff=0)
        analisis_menu.add_command(label="Evolución", command=lambda: self._show_page("evolucion"))
        analisis_menu.add_command(label="Comparativa", command=lambda: self._show_page("comparativa"))
        analisis_menu.add_command(label="Resumen", command=lambda: self._show_page("resumen"))
        analisis_menu.add_command(label="Mapa de calor", command=lambda: self._show_page("mapa_calor"))
        analisis_menu.add_separator()
        analisis_menu.add_command(label="Laboratorios incluidos...", command=self._choose_labs)
        # Opción normal con texto que cambia, no `add_checkbutton`: en Windows
        # la marca ✔ de Tk se dibuja encima de la primera letra.
        analisis_menu.add_command(
            label=self._history_menu_label(),
            command=lambda: (self.var_full_history.set(not self.var_full_history.get()),
                             self._toggle_full_history()),
        )
        self._history_menu = (analisis_menu, analisis_menu.index("end"))
        menubar.add_cascade(label="Análisis", menu=analisis_menu)

        # Menú separado de "Análisis" (que son gráficos puros de uno o dos
        # parámetros elegidos a mano): estos paneles combinan varios
        # parámetros con una interpretación clínica propia (fórmulas,
        # umbrales citados, texto orientativo). Antes vivían todos dentro de
        # "Análisis"; separados para que ese menú no crezca sin límite cada
        # vez que se añade un panel nuevo, y para que quede claro de un
        # vistazo cuáles son informes "hechos" y cuáles gráficos a la carta.
        paneles_menu = tk.Menu(menubar, tearoff=0)
        paneles_menu.add_command(
            label="Riesgo cardiovascular", command=lambda: self._show_page("riesgo_cv")
        )
        paneles_menu.add_command(
            label="Salud hepática", command=lambda: self._show_page("salud_hepatica")
        )
        paneles_menu.add_command(
            label="Función renal", command=lambda: self._show_page("funcion_renal")
        )
        paneles_menu.add_command(
            label="Hemograma", command=lambda: self._show_page("hemograma")
        )
        paneles_menu.add_command(
            label="Metabolismo del hierro", command=lambda: self._show_page("hierro")
        )
        paneles_menu.add_command(
            label="Inflamación", command=lambda: self._show_page("inflamacion")
        )
        paneles_menu.add_command(
            label="Ácido úrico", command=lambda: self._show_page("acido_urico")
        )
        paneles_menu.add_command(
            label="Calcio corregido", command=lambda: self._show_page("calcio")
        )
        paneles_menu.add_command(
            label="Glucosa (eAG y TyG)", command=lambda: self._show_page("glucemia")
        )
        paneles_menu.add_command(
            label="Tiroides", command=lambda: self._show_page("tiroides")
        )
        paneles_menu.add_command(
            label="Tensión arterial", command=lambda: self._show_page("tension_panel")
        )
        menubar.add_cascade(label="Paneles clínicos", menu=paneles_menu)

        herramientas_menu = tk.Menu(menubar, tearoff=0)
        herramientas_menu.add_command(label="Explorador BD", command=lambda: self._show_page("explorador"))
        herramientas_menu.add_command(
            label="Normalizar pruebas", command=lambda: self._show_page("catalogo")
        )
        menubar.add_cascade(label="Herramientas", menu=herramientas_menu)

        menubar.add_command(label="Configuración", command=lambda: self._show_page("config"))

        ayuda_menu = tk.Menu(menubar, tearoff=0)
        # Documentación en línea (rama principal del repositorio público):
        # siempre la versión más reciente, con todas las fuentes citadas.
        for label, path in DOC_LINKS:
            ayuda_menu.add_command(label=label, command=lambda p=path: webbrowser.open(f"{REPO_URL}/{p}"))
        ayuda_menu.add_separator()
        ayuda_menu.add_command(
            label="Buscar actualizaciones...", command=lambda: self._check_updates(manual=True)
        )
        ayuda_menu.add_command(label="Acerca de...", command=self._show_about)
        menubar.add_cascade(label="Ayuda", menu=ayuda_menu)

        self.config(menu=menubar)

        # Entradas que operan sobre el paciente activo: sin paciente activo
        # (0 pacientes, o varios sin haber elegido ninguno) quedan
        # deshabilitadas para no mostrar/exportar datos de un paciente
        # elegido en silencio. "Entrada manual" no entra aquí porque su
        # pestaña se abre igual y deshabilita su propio formulario (ver
        # `_update_manual_tab_enabled`).
        # `entryconfigure` acepta la etiqueta de texto como índice (Tcl la
        # busca por coincidencia exacta), no hace falta guardar posiciones
        # numéricas.
        self._patient_required_menu_entries = (
            (archivo, "Exportar"),
            (analisis_menu, "Evolución"),
            (analisis_menu, "Comparativa"),
            (analisis_menu, "Resumen"),
            (analisis_menu, "Mapa de calor"),
            (paneles_menu, "Riesgo cardiovascular"),
            (paneles_menu, "Salud hepática"),
            (paneles_menu, "Función renal"),
            (paneles_menu, "Hemograma"),
            (paneles_menu, "Metabolismo del hierro"),
            (paneles_menu, "Inflamación"),
            (paneles_menu, "Ácido úrico"),
            (paneles_menu, "Calcio corregido"),
            (paneles_menu, "Glucosa (eAG y TyG)"),
            (paneles_menu, "Tiroides"),
        )

    def _show_about(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Acerca de Analitix")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.grab_set()

        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True)

        photo = load_logo_photo(220)
        logo_label = ttk.Label(body, image=photo)
        logo_label.image = photo
        logo_label.pack(padx=PAD * 2, pady=(PAD * 2, PAD))

        ttk.Label(body, text="Analitix", font=("Segoe UI", 16, "bold")).pack()
        ttk.Label(body, text=f"Versión {__version__}", bootstyle="secondary").pack()
        ttk.Label(
            body, text="Análisis de informes de laboratorio", bootstyle="secondary"
        ).pack(pady=(0, 10))
        ttk.Label(body, text="Autor: Gabriel Marti").pack()
        correo = ttk.Label(body, text=CONTACT_EMAIL, bootstyle="info", cursor="hand2")
        correo.pack()
        correo.bind("<Button-1>", lambda _e: webbrowser.open(f"mailto:{CONTACT_EMAIL}"))
        contacto = ttk.Label(
            body, text="github.com/gabimarti", bootstyle="info", cursor="hand2"
        )
        contacto.pack(pady=(0, PAD))
        contacto.bind("<Button-1>", lambda _e: webbrowser.open("https://github.com/gabimarti"))

        ttk.Button(body, text="Cerrar", command=dialog.destroy).pack(pady=(0, PAD * 2))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.wait_window(dialog)

    def _check_updates(self, manual: bool) -> None:
        # La consulta va en un hilo para no congelar la ventana mientras
        # espera la red (hasta `updates.TIMEOUT_S`); el hilo no toca Tk ni la
        # base de datos, y el resultado se recoge en el hilo principal con
        # `after`. Al iniciar solo se avisa si hay versión nueva; a mano
        # también se informa de "al día" o de que no se pudo comprobar.
        result: dict = {}

        def worker() -> None:
            try:
                result["release"] = fetch_latest_release()
            except Exception as exc:  # sin red, 404 (repositorio privado), JSON inesperado
                result["error"] = exc

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                self.after(200, poll)
                return
            if "error" in result:
                logger.info("No se pudo comprobar si hay versiones nuevas: %s", result["error"])
                if manual:
                    messagebox.showwarning(
                        "No se pudo comprobar",
                        f"No se pudo consultar {RELEASES_URL}.\n\nComprueba la conexión a internet.",
                        parent=self,
                    )
                return
            release = result["release"]
            if release and is_newer(release[0]):
                if messagebox.askyesno(
                    "Nueva versión disponible",
                    f"Hay una versión nueva de Analitix: {release[0]} (tienes la {__version__}).\n\n"
                    "¿Abrir la página de descarga en el navegador?",
                    parent=self,
                ):
                    webbrowser.open(release[1])
            elif manual:
                messagebox.showinfo(
                    "Analitix está al día", f"Tienes la última versión ({__version__}).", parent=self
                )

        poll()

    def _build_pages(self) -> None:
        self.content = ttk.Frame(self)
        self.content.pack(fill="both", expand=True, padx=PAD, pady=(PAD, 0))

        self.tab_importar = ttk.Frame(self.content)
        self.tab_pacientes = ttk.Frame(self.content)
        self.tab_manual = ttk.Frame(self.content)
        self.tab_tension = ttk.Frame(self.content)
        self.tab_evolucion = ttk.Frame(self.content)
        self.tab_comparativa = ttk.Frame(self.content)
        self.tab_resumen = ttk.Frame(self.content)
        self.tab_mapa_calor = ttk.Frame(self.content)
        self.tab_riesgo_cv = ttk.Frame(self.content)
        self.tab_salud_hepatica = ttk.Frame(self.content)
        self.tab_funcion_renal = ttk.Frame(self.content)
        self.tab_hemograma = ttk.Frame(self.content)
        self.tab_hierro = ttk.Frame(self.content)
        self.tab_inflamacion = ttk.Frame(self.content)
        self.tab_acido_urico = ttk.Frame(self.content)
        self.tab_calcio = ttk.Frame(self.content)
        self.tab_glucemia = ttk.Frame(self.content)
        self.tab_tiroides = ttk.Frame(self.content)
        self.tab_tension_panel = ttk.Frame(self.content)
        self.tab_exportar = ttk.Frame(self.content)
        self.tab_explorador = ttk.Frame(self.content)
        self.tab_catalogo = ttk.Frame(self.content)
        self.tab_config = ttk.Frame(self.content)

        self._pages: dict[str, ttk.Frame] = {
            "importar": self.tab_importar,
            "pacientes": self.tab_pacientes,
            "manual": self.tab_manual,
            "tension": self.tab_tension,
            "evolucion": self.tab_evolucion,
            "comparativa": self.tab_comparativa,
            "resumen": self.tab_resumen,
            "mapa_calor": self.tab_mapa_calor,
            "riesgo_cv": self.tab_riesgo_cv,
            "salud_hepatica": self.tab_salud_hepatica,
            "funcion_renal": self.tab_funcion_renal,
            "hemograma": self.tab_hemograma,
            "hierro": self.tab_hierro,
            "inflamacion": self.tab_inflamacion,
            "acido_urico": self.tab_acido_urico,
            "calcio": self.tab_calcio,
            "glucemia": self.tab_glucemia,
            "tiroides": self.tab_tiroides,
            "tension_panel": self.tab_tension_panel,
            "exportar": self.tab_exportar,
            "explorador": self.tab_explorador,
            "catalogo": self.tab_catalogo,
            "config": self.tab_config,
        }
        self._current_page_key: str | None = None

        # Pantalla de bienvenida: el logo, visible mientras no se ha elegido
        # ninguna opción del menú todavía.
        self._welcome_frame = ttk.Frame(self.content)
        welcome_photo = load_logo_photo(320)
        welcome_label = ttk.Label(self._welcome_frame, image=welcome_photo)
        welcome_label.image = welcome_photo
        welcome_label.place(relx=0.5, rely=0.5, anchor="center")
        self._welcome_frame.pack(fill="both", expand=True)

        # Mismo criterio que antes con las pestañas: estas páginas no se
        # muestran sin un paciente elegido explícitamente (ver `_build_menu`).
        self._patient_required_pages = (
            "evolucion", "comparativa", "resumen", "mapa_calor", "riesgo_cv", "salud_hepatica", "funcion_renal", "hemograma",
            "hierro", "inflamacion", "acido_urico", "calcio", "glucemia", "tiroides", "exportar",
        )

        self._build_tab_importar()
        self._build_tab_pacientes()
        self._build_tab_manual()
        self._build_tab_tension()
        self._build_tab_evolucion()
        self._build_tab_comparativa()
        self._build_tab_resumen()
        self._build_tab_mapa_calor()
        self._build_tab_riesgo_cv()
        self._build_tab_salud_hepatica()
        self._build_tab_funcion_renal()
        self._build_tab_hemograma()
        self._build_tab_hierro()
        self._build_tab_inflamacion()
        self._build_tab_acido_urico()
        self._build_tab_calcio()
        self._build_tab_glucemia()
        self._build_tab_tiroides()
        self._build_tab_tension_panel()
        self._build_tab_exportar()
        self._build_tab_explorador()
        self._build_tab_catalogo()
        self._build_tab_config()

    def _show_page(self, key: str) -> None:
        if self._current_page_key == key:
            return
        if self._current_page_key is None:
            self._welcome_frame.pack_forget()
        else:
            self._pages[self._current_page_key].pack_forget()
        self._pages[key].pack(fill="both", expand=True)
        self._current_page_key = key

    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self, bootstyle="secondary")
        bar.pack(fill="x", side="bottom")
        ttk.Label(bar, textvariable=self.status_var, bootstyle="inverse-secondary", padding=(PAD, 4)).pack(
            anchor="w"
        )

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    # -- Importar -------------------------------------------------------
    def _build_tab_importar(self) -> None:
        frame = self.tab_importar
        top = ttk.Frame(frame)
        top.pack(fill="x", padx=PAD, pady=PAD)
        ttk.Label(top, text="Carpeta actual:").pack(side="left")
        ttk.Label(top, textvariable=self.var_reports_dir, bootstyle="secondary").pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(
            top, text="Cambiar carpeta...", bootstyle="secondary-outline", command=self._change_reports_dir
        ).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            top, text="Incluir subcarpetas", variable=self.var_import_subfolders, bootstyle="round-toggle",
            command=lambda: set_setting(
                self.con, "import_subfolders", "1" if self.var_import_subfolders.get() else "0"
            ),
        ).pack(side="left", padx=(12, 0))
        self.btn_reimport_forced = ttk.Button(
            top, text="Reimportar todo (forzar)", bootstyle="warning-outline", command=self._run_ingest_forced
        )
        self.btn_reimport_forced.pack(side="right", padx=(0, 8))
        self.btn_import = ttk.Button(
            top, text="Buscar e importar informes nuevos", bootstyle="success", command=self._run_ingest
        )
        self.btn_import.pack(side="right")
        self._same_width(self.btn_import, self.btn_reimport_forced)

        progreso = ttk.Frame(frame)
        progreso.pack(fill="x", padx=PAD, pady=(0, PAD))
        self.var_progress_text = tk.StringVar(value="")
        ttk.Label(progreso, textvariable=self.var_progress_text, bootstyle="secondary").pack(anchor="w")
        self.progressbar = ttk.Progressbar(progreso, mode="determinate")
        self.progressbar.pack(fill="x", pady=(2, 0))

        self.log_text = tk.Text(frame, height=25, state="disabled", relief="flat", borderwidth=0)
        self.log_text.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self._style_plain_widget(self.log_text)

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    def _run_ingest_forced(self) -> None:
        if not messagebox.askyesno(
            "Reimportar todo",
            "Esto vuelve a analizar TODOS los PDF de la carpeta, incluidos los que ya estaban "
            "correctamente importados, y sustituye sus datos por los del nuevo análisis "
            "(útil tras una mejora del programa). No afecta a otros pacientes ni informes "
            "que no estén en la carpeta.\n\n¿Continuar?",
            parent=self,
        ):
            return
        self._run_ingest(force=True)

    def _on_ingest_progress(self, index: int, total: int, filename: str) -> None:
        self.progressbar.configure(maximum=max(total, 1), value=index)
        self.var_progress_text.set(f"Analizando {index}/{total}: {filename}")
        # `update_idletasks` (no `update`) repinta la ventana y procesa la cola
        # de eventos sin dar pie a que el usuario dispare otra acción a medias
        # de esta; así no da la sensación de que el programa se ha colgado.
        self.update_idletasks()

    def _run_ingest(self, force: bool = False) -> None:
        self.btn_import.configure(state="disabled")
        self.btn_reimport_forced.configure(state="disabled")
        self.var_progress_text.set("Preparando...")
        self.progressbar.configure(value=0)
        self.update_idletasks()
        try:
            result = ingest_folder(
                self.con, reports_dir=self.reports_dir, force=force, on_progress=self._on_ingest_progress,
                recursive=self.var_import_subfolders.get(),
            )
        finally:
            self.btn_import.configure(state="normal")
            self.btn_reimport_forced.configure(state="normal")
            self.var_progress_text.set("")
            self.progressbar.configure(value=0)
        self._log(f"Procesados: {len(result.processed)}")
        for name, format_name in result.processed:
            self._log(f"  + {name} ({format_name})")
        self._log(f"Ya estaban al día (omitidos): {len(result.skipped)}")
        if result.review:
            self._log(f"⚠ Para revisar: {len(result.review)}")
            for name, reason in result.review:
                self._log(f"  ⚠ {name}: {reason}")
        if result.errors:
            self._log(f"Errores: {len(result.errors)}")
            for name, err in result.errors:
                self._log(f"  ! {name}: {err}")
        self._refresh_patients()
        self._refresh_stats()
        aviso_revision = (
            f"\n\n⚠ {len(result.review)} informe(s) necesitan revisión manual "
            "(posible PDF de un formato no reconocido) — ver pestaña Configuración."
            if result.review
            else ""
        )
        messagebox.showinfo(
            "Importación completada",
            f"Nuevos: {len(result.processed)}\nOmitidos: {len(result.skipped)}\n"
            f"Errores: {len(result.errors)}{aviso_revision}",
            parent=self,
        )
        self._prompt_active_patient_if_needed()

    # -- Pacientes --------------------------------------------------------
    def _build_tab_pacientes(self) -> None:
        frame = self.tab_pacientes
        columns = ("activo", "full_name", "birth_date", "sex", "dni", "cip", "nhc", "nhc_alt", "tabaco", "num_reports")
        self.tree_patients = ttk.Treeview(
            frame, columns=columns, show="headings", selectmode="extended", bootstyle="primary"
        )
        for col, label, width in zip(
            columns,
            ("Activo", "Nombre", "Fecha nacimiento", "Sexo", "DNI", "CIP", "NHC", "NHC secundario", "Tabaco",
             "Informes"),
            (50, 240, 120, 70, 100, 130, 100, 110, 140, 70),
        ):
            self.tree_patients.heading(col, text=label)
            self.tree_patients.column(col, width=width, anchor="center" if col == "activo" else "w")
        self.tree_patients.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        self._checkbox_tree(self.tree_patients)

        def _abrir_ficha(event) -> None:
            # Doble clic: abre la ficha de esa fila, sea cual sea lo marcado.
            iid = self.tree_patients.identify_row(event.y)
            if iid:
                self.tree_patients.selection_set(iid)
                self._edit_selected_patient()

        self.tree_patients.bind("<Double-1>", _abrir_ficha)
        ttk.Label(
            frame,
            text="Aquí se ven y se editan las fichas de los pacientes. Seleccionar una fila no "
            "cambia el paciente activo (★), que es con el que trabaja toda la aplicación "
            "(análisis, paneles, exportar y entrada manual). Si el mismo paciente aparece en "
            "dos filas (p. ej. un PDF antiguo con el nombre abreviado), marca las dos casillas "
            "y fusiónalas.",
            bootstyle="secondary", wraplength=900,
        ).pack(anchor="w", padx=PAD)

        activo_frame = ttk.Frame(frame)
        activo_frame.pack(fill="x", padx=PAD, pady=(6, 0))
        self.label_active_patient = ttk.Label(activo_frame, text="Paciente activo: ninguno", bootstyle="info")
        self.label_active_patient.pack(side="left")
        ttk.Button(
            activo_frame, text="Cambiar paciente activo...", bootstyle="info",
            command=self._choose_active_patient,
        ).pack(side="left", padx=(18, 0))

        botones = ttk.Frame(frame)
        botones.pack(fill="x", padx=PAD, pady=(4, PAD))
        boton_editar = ttk.Button(
            botones, text="Editar ficha...", bootstyle="info-outline",
            command=self._edit_selected_patient,
        )
        boton_editar.pack(side="left", padx=(0, 8))
        boton_eliminar = ttk.Button(
            botones, text="Eliminar paciente seleccionado...", bootstyle="danger-outline",
            command=self._delete_selected_patient,
        )
        boton_eliminar.pack(side="left")
        boton_fusionar = ttk.Button(
            botones, text="Fusionar seleccionados...", bootstyle="primary",
            command=self._merge_selected_patients,
        )
        boton_fusionar.pack(side="left", padx=(8, 0))
        self._same_width(boton_editar, boton_eliminar, boton_fusionar)

    def _selected_patient(self) -> dict | None:
        """Ficha de la fila seleccionada en la tabla Pacientes (la primera si hay varias)."""
        selection = self.tree_patients.selection()
        if not selection:
            return None
        return next((p for p in self.patients if p["id"] == int(selection[0])), None)

    def _prompt_active_patient_if_needed(self) -> None:
        # Con un único paciente `_refresh_patients` ya lo activa sin preguntar.
        if self.current_patient_id is None and len(self.patients) > 1:
            self._choose_active_patient()

    def _choose_active_patient(self) -> None:
        if not self.patients:
            messagebox.showinfo(
                "Sin pacientes", "Todavía no hay pacientes: importa antes algún informe.", parent=self
            )
            return
        patient_id = self._ask_active_patient()
        if patient_id is not None:
            self.current_patient_id = patient_id
            self._refresh_patients()

    def _new_dialog(self, title: str, resizable: bool = False) -> tuple[tk.Toplevel, ttk.Frame]:
        """Ventana de diálogo modal homogénea (ver docs/GUIA_INTERFAZ.md):
        devuelve la ventana y un único `ttk.Frame` de cuerpo con `PAD` de
        margen, donde va TODO el contenido. Nada directamente sobre el
        `tk.Toplevel`: su fondo es el gris del sistema y los widgets ttk se
        verían como recuadros de otro color. Escape cierra (= Cancelar)."""
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.resizable(resizable, resizable)
        dialog.grab_set()
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        body = ttk.Frame(dialog, padding=PAD)
        body.pack(fill="both", expand=True)
        return dialog, body

    @contextlib.contextmanager
    def _progress(self, title: str, parent: tk.Misc | None = None):
        """Ventana de progreso modal para procesos de varios segundos (p. ej.
        generar un PDF), para que no parezca que la aplicación se ha colgado:
        texto del paso, barra y cursor de espera. Da una función
        `paso(texto, valor, total)` que actualiza la barra y repinta. Todo
        sigue en el hilo principal (como la importación): `update()` procesa
        los eventos pendientes, pero la ventana tiene el `grab`, así que el
        usuario no puede lanzar otra acción a medias, y no se puede cerrar."""
        ventana, body = self._new_dialog(title)
        ventana.unbind("<Escape>")
        ventana.protocol("WM_DELETE_WINDOW", lambda: None)
        texto = tk.StringVar(value="Preparando...")
        ttk.Label(body, textvariable=texto, width=48).pack(anchor="w")
        barra = ttk.Progressbar(body, mode="determinate", length=380)
        barra.pack(fill="x", pady=(6, 0))
        self._center_dialog(ventana)
        con_cursor = [w for w in (self, parent, ventana) if w is not None]
        for w in con_cursor:
            w.configure(cursor="watch")

        def paso(mensaje: str, valor: int, total: int) -> None:
            texto.set(mensaje)
            barra.configure(maximum=max(total, 1), value=valor)
            ventana.update()

        ventana.update()
        try:
            yield paso
        finally:
            for w in con_cursor[:-1]:
                if w.winfo_exists():
                    w.configure(cursor="")
            ventana.grab_release()
            ventana.destroy()
            if parent is not None and parent is not self and parent.winfo_exists():
                parent.grab_set()

    def _center_dialog(self, dialog: tk.Toplevel) -> None:
        """Centra el diálogo sobre la ventana principal (Tk lo abre en la
        esquina superior izquierda de la pantalla si no se le da posición).
        Llamar cuando ya tiene todo su contenido."""
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_reqwidth()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_reqheight()) // 3
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    @staticmethod
    def _same_width(*buttons) -> None:
        """Mismo ancho para un grupo de botones de una pantalla: el del texto
        más largo (en caracteres), ver docs/GUIA_INTERFAZ.md."""
        ancho = max(len(b.cget("text")) for b in buttons) + 2
        for b in buttons:
            b.configure(width=ancho)

    def _list_column(self, left: ttk.Frame, text: str, height: int, **opts) -> tk.Listbox:
        """Etiqueta + lista de la columna izquierda de Análisis y Paneles
        clínicos. La etiqueta se parte en líneas al ancho de la lista para no
        ensanchar la columna: así etiqueta, lista y botones quedan alineados a
        la izquierda y todas las columnas miden lo mismo (docs/GUIA_INTERFAZ.md)."""
        label = ttk.Label(left, text=text, justify="left")
        label.pack(anchor="w")
        lista = tk.Listbox(
            left, height=height, width=LIST_COLUMN_CHARS, exportselection=False, relief="flat", **opts
        )
        lista.pack(fill="y", expand=True, pady=(4, 0))
        self._style_plain_widget(lista)
        label.configure(wraplength=lista.winfo_reqwidth())
        return lista

    def _fixed_column(self, left: ttk.Frame) -> None:
        """Columna izquierda sin lista (solo botones): mismo ancho que las que
        tienen lista (`_list_column`), para que no cambie de una pantalla a otra."""
        probe = tk.Listbox(self, width=LIST_COLUMN_CHARS, relief="flat", highlightthickness=0)
        left.configure(width=probe.winfo_reqwidth())
        probe.destroy()
        left.pack_propagate(False)

    def _scrollable_frame(self, parent, height: int = 180) -> ttk.Frame:
        """Marco con barra de desplazamiento vertical para listas largas de
        casillas (más cómodo que una lista con Ctrl+clic, donde un clic sin
        Ctrl desmarca todo). Devuelve el marco interior donde poner los
        widgets. La rueda del ratón solo actúa con el puntero encima."""
        contenedor = ttk.Frame(parent)
        contenedor.pack(fill="both", expand=True)
        canvas = tk.Canvas(contenedor, height=height, highlightthickness=0, background=self.style.colors.bg)
        barra = ttk.Scrollbar(contenedor, orient="vertical", command=canvas.yview)
        interior = ttk.Frame(canvas)
        ventana = canvas.create_window((0, 0), window=interior, anchor="nw")
        canvas.configure(yscrollcommand=barra.set)
        interior.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(ventana, width=e.width))
        canvas.pack(side="left", fill="both", expand=True)
        barra.pack(side="left", fill="y")

        def _rueda(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _rueda))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        return interior

    def _checkbox_tree(self, tree: ttk.Treeview) -> None:
        """Tabla con casillas (☐/☑ en la primera columna): un clic marca o
        desmarca la fila sin Ctrl, en vez de la selección extendida, donde un
        clic sin Ctrl desmarca todo (docs/GUIA_INTERFAZ.md §8). La marca es la
        propia selección de la tabla, así que `tree.selection()` sigue dando
        las filas marcadas. Solo las filas de primer nivel tienen casilla.
        Después de rellenar la tabla, llama a `self._sync_checks(tree)`."""
        tree.configure(show="tree headings")
        tree.column("#0", width=48, minwidth=48, stretch=False)

        def _clic(event):
            if tree.identify_region(event.x, event.y) not in ("tree", "cell"):
                return None
            iid = tree.identify_row(event.y)
            if tree.get_children(iid) and "indicator" in tree.identify_element(event.x, event.y):
                tree.item(iid, open=not tree.item(iid, "open"))  # ▸ solo despliega, no toca las marcas
                return "break"
            tree.focus(iid)
            if not tree.parent(iid):
                tree.selection_toggle(iid)
            return "break"

        tree.bind("<Button-1>", _clic)
        tree.bind("<<TreeviewSelect>>", lambda _e: self._sync_checks(tree), add="+")

    @staticmethod
    def _sync_checks(tree: ttk.Treeview) -> None:
        """Pone ☑ en las filas marcadas (seleccionadas) y ☐ en el resto."""
        marcadas = set(tree.selection())
        for iid in tree.get_children():
            tree.item(iid, text=CHECK_ON if iid in marcadas else CHECK_OFF)

    def _ask_active_patient(self) -> int | None:
        """Diálogo modal que lista SOLO el nombre completo de cada paciente
        (sin fecha de nacimiento, DNI, NHC...: la ficha completa está en la
        pestaña Pacientes). Devuelve el id elegido o `None` si se cancela."""
        dialog, body = self._new_dialog("Seleccionar paciente activo")
        ttk.Label(body, text="¿Con qué paciente quieres trabajar?").pack(anchor="w", pady=(0, PAD))

        lista = ttk.Frame(body)
        lista.pack(fill="both", expand=True)
        listbox = tk.Listbox(
            lista, height=min(len(self.patients), 15), width=45, activestyle="none", exportselection=False
        )
        scroll = ttk.Scrollbar(lista, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        ids = [p["id"] for p in self.patients]
        for p in self.patients:
            listbox.insert("end", p["full_name"])
        index = ids.index(self.current_patient_id) if self.current_patient_id in ids else 0
        listbox.selection_set(index)
        listbox.see(index)
        listbox.focus_set()
        result: dict[str, int | None] = {"value": None}

        def _confirm(_event=None) -> None:
            selection = listbox.curselection()
            if selection:
                result["value"] = ids[selection[0]]
                dialog.destroy()

        listbox.bind("<Double-1>", _confirm)
        listbox.bind("<Return>", _confirm)
        botones = ttk.Frame(body)
        botones.pack(fill="x", pady=(PAD, 0))
        boton_cancelar = ttk.Button(botones, text="Cancelar", command=dialog.destroy)
        boton_cancelar.pack(side="right")
        boton_ok = ttk.Button(botones, text="Aceptar", bootstyle="primary", command=_confirm)
        boton_ok.pack(side="right", padx=(0, 8))
        self._same_width(boton_cancelar, boton_ok)
        self._center_dialog(dialog)
        self.wait_window(dialog)
        return result["value"]

    def _update_active_patient_display(self) -> None:
        patient = next((p for p in self.patients if p["id"] == self.current_patient_id), None)
        self.label_active_patient.configure(
            text=f"Paciente activo: {patient['full_name']}" if patient else "Paciente activo: ninguno"
        )
        self._refresh_manual_patient_label()
        self._refresh_tension_page()

    def _delete_selected_patient(self) -> None:
        patient = self._selected_patient()
        if patient is None:
            messagebox.showwarning("Sin paciente", "Selecciona antes un paciente.", parent=self)
            return
        nombre = patient["full_name"]
        if not messagebox.askyesno(
            "Eliminar paciente",
            f"¿Eliminar a «{nombre}» y TODOS sus informes y resultados? Esta acción no se puede deshacer.",
            parent=self,
        ):
            return
        # No se registra el nombre en el log (ver logging_setup.py: el log no
        # debe contener datos de pacientes), solo el id interno.
        logger.info("Eliminando paciente id=%s", patient["id"])
        delete_patient(self.con, patient["id"])
        # Si era el activo, `_refresh_patients` lo quita (ya no existe).
        self._refresh_patients()
        self._refresh_stats()
        messagebox.showinfo("Analitix", "Paciente eliminado.", parent=self)

    def _edit_selected_patient(self) -> None:
        """Ficha editable del paciente seleccionado: completar a mano lo que
        la importación no detectó (fecha de nacimiento, sexo, DNI, CIP,
        NHC...) y el tabaquismo, que ningún PDF trae."""
        patient = self._selected_patient()
        if patient is None:
            messagebox.showwarning("Sin paciente", "Selecciona antes un paciente.", parent=self)
            return
        dialog, outer = self._new_dialog("Ficha del paciente", resizable=True)
        form = ttk.Frame(outer)
        form.pack(fill="both", expand=True)

        yes_no = {None: "", 1: "Sí", 0: "No"}
        text_fields = (
            ("full_name", "Nombre"), ("birth_date", "Fecha nacimiento (AAAA-MM-DD)"),
            ("dni", "DNI"), ("cip", "CIP"), ("nhc", "NHC"), ("nhc_alt", "NHC secundario"),
        )
        vars_: dict[str, tk.StringVar] = {}
        row = 0
        for key, label in text_fields:
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            vars_[key] = tk.StringVar(value=patient[key] or "")
            ttk.Entry(form, textvariable=vars_[key], width=40).grid(row=row, column=1, sticky="we", pady=3)
            row += 1
        ttk.Label(form, text="Sexo").grid(row=row, column=0, sticky="w", pady=3)
        vars_["sex"] = tk.StringVar(value=patient["sex"] or "")
        ttk.Combobox(form, textvariable=vars_["sex"], values=["", *SEX_OPTIONS], state="readonly", width=12).grid(
            row=row, column=1, sticky="w", pady=3
        )
        row += 1

        ttk.Separator(form).grid(row=row, column=0, columnspan=2, sticky="we", pady=(10, 6))
        row += 1
        ttk.Label(form, text="Tabaquismo", bootstyle="info").grid(row=row, column=0, sticky="w")
        row += 1
        for key, label in (("smoker_current", "Fumador actual"), ("smoker_former", "Fumador anterior")):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            vars_[key] = tk.StringVar(value=yes_no[patient[key]])
            ttk.Combobox(form, textvariable=vars_[key], values=["", "Sí", "No"], state="readonly", width=12).grid(
                row=row, column=1, sticky="w", pady=3
            )
            row += 1
        former_widgets = []
        for key, label, width in (
            ("smoker_former_from", "  Desde año", 8), ("smoker_former_to", "  Hasta año", 8),
            ("smoker_former_period", "  Periodo (texto libre)", 40),
        ):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            value = patient[key]
            vars_[key] = tk.StringVar(value="" if value is None else str(value))
            entry = ttk.Entry(form, textvariable=vars_[key], width=width)
            entry.grid(row=row, column=1, sticky="w", pady=3)
            former_widgets.append(entry)
            row += 1
        ttk.Label(
            form, text="Indica los años o, si no los sabes, un periodo aproximado "
            "(p. ej. «unos 10 años, de joven»).", bootstyle="secondary", wraplength=420,
        ).grid(row=row, column=0, columnspan=2, sticky="w")

        def _sync_former_state(*_args) -> None:
            state = "normal" if vars_["smoker_former"].get() == "Sí" else "disabled"
            for entry in former_widgets:
                entry.configure(state=state)

        vars_["smoker_former"].trace_add("write", _sync_former_state)
        _sync_former_state()

        def _save() -> None:
            from_yes_no = {"": None, "Sí": 1, "No": 0}
            fields = {key: var.get() for key, var in vars_.items()}
            for key in ("smoker_current", "smoker_former"):
                fields[key] = from_yes_no[fields[key]]
            try:
                update_patient(self.con, patient["id"], fields)
            except ValueError as exc:
                messagebox.showerror("No se puede guardar", str(exc), parent=dialog)
                return
            # Solo el id interno en el log, nunca datos del paciente.
            logger.info("Ficha de paciente editada id=%s", patient["id"])
            dialog.destroy()
            self._refresh_patients()

        reports = list_patient_reports(self.con, patient["id"])
        informes = ttk.Labelframe(outer, text=f"Informes importados ({len(reports)})", padding=6)
        informes.pack(fill="both", expand=True, pady=(PAD, 0))
        columns = ("fecha", "lab", "source_file", "num_results", "file_md5")
        tree = ttk.Treeview(informes, columns=columns, show="headings", height=min(max(len(reports), 3), 10))
        for col, label, width, anchor in (
            ("fecha", "Fecha analítica", 110, "w"), ("lab", "Laboratorio", 120, "w"),
            ("source_file", "Fichero", 300, "w"),
            ("num_results", "Parámetros", 80, "center"), ("file_md5", "MD5", 260, "w"),
        ):
            tree.heading(col, text=label)
            tree.column(col, width=width, anchor=anchor)
        scroll = ttk.Scrollbar(informes, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for r in reports:
            tree.insert("", "end", values=(
                (r["fecha"] or "")[:10], r["lab"] or "—", r["source_file"], r["num_results"], r["file_md5"] or "—",
            ))

        botones = ttk.Frame(outer)
        botones.pack(fill="x", pady=(PAD, 0))
        boton_cancelar = ttk.Button(botones, text="Cancelar", command=dialog.destroy)
        boton_cancelar.pack(side="right")
        boton_ok = ttk.Button(botones, text="Guardar", bootstyle="primary", command=_save)
        boton_ok.pack(side="right", padx=(0, 8))
        self._same_width(boton_cancelar, boton_ok)
        self._center_dialog(dialog)
        self.wait_window(dialog)

    def _merge_selected_patients(self) -> None:
        selected_ids = [int(iid) for iid in self.tree_patients.selection()]
        if len(selected_ids) < 2:
            messagebox.showwarning(
                "Selecciona al menos 2", "Marca dos o más filas que sean el mismo "
                "paciente para fusionarlas.", parent=self,
            )
            return
        candidates = [p for p in self.patients if p["id"] in selected_ids]
        target_id = self._ask_patient_merge_target(candidates)
        if target_id is None:
            return
        logger.info("Fusionando pacientes id=%s en id=%s", selected_ids, target_id)
        moved = merge_patients(self.con, selected_ids, target_id)
        if self.current_patient_id in selected_ids:
            self.current_patient_id = target_id
        self._refresh_patients()
        self._refresh_stats()
        messagebox.showinfo(
            "Analitix", f"Pacientes fusionados: {moved} informe(s) reasignado(s).", parent=self
        )

    def _ask_patient_merge_target(self, candidates: list[dict]) -> int | None:
        """Diálogo modal para elegir, de entre los pacientes seleccionados
        para fusionar, cuál conserva su nombre/identidad; el resto se funde
        en él (su DNI/NHC se aprovechan si al destino le faltan). Devuelve
        `None` si se cancela."""
        dialog, body = self._new_dialog("Elegir paciente a conservar")
        ttk.Label(
            body,
            text="¿Cuál de estos es el paciente a conservar? El resto se fundirá en él (sus "
            "informes pasan a pertenecerle; el DNI/NHC que le falten se rellenan con los del "
            "resto si los tienen).",
            wraplength=520,
        ).pack(anchor="w", pady=(0, 6))
        default_id = max(candidates, key=lambda p: p["num_reports"])["id"]
        choice = tk.IntVar(value=default_id)
        for p in candidates:
            nhc_txt = p["nhc"] or "—"
            if p.get("nhc_alt"):
                nhc_txt += f" (además: {p['nhc_alt']})"
            etiqueta = (
                f"{p['full_name']}  (nac. {p['birth_date'] or '?'}, DNI {p['dni'] or '—'}, "
                f"NHC {nhc_txt}, {p['num_reports']} informe(s))"
            )
            ttk.Radiobutton(body, text=etiqueta, variable=choice, value=p["id"]).pack(
                anchor="w", padx=8, pady=2
            )
        result: dict[str, int | None] = {"value": None}

        def _confirm() -> None:
            result["value"] = choice.get()
            dialog.destroy()

        botones = ttk.Frame(body)
        botones.pack(fill="x", pady=(PAD, 0))
        boton_cancelar = ttk.Button(botones, text="Cancelar", command=dialog.destroy)
        boton_cancelar.pack(side="right")
        boton_ok = ttk.Button(botones, text="Fusionar", bootstyle="primary", command=_confirm)
        boton_ok.pack(side="right", padx=(0, 8))
        self._same_width(boton_cancelar, boton_ok)
        self._center_dialog(dialog)
        self.wait_window(dialog)
        return result["value"]

    def _refresh_patients(self) -> None:
        self.patients = list_patients(self.con)
        # El paciente eliminado o fusionado ya no existe: no dejamos la app
        # apuntando en silencio a un id que ya no es nadie.
        if self.current_patient_id is not None and not any(
            p["id"] == self.current_patient_id for p in self.patients
        ):
            self.current_patient_id = None
        # Con un único paciente no hay ambigüedad posible: es el activo sin
        # preguntar. Con varios, se elige en el diálogo de paciente activo.
        if self.current_patient_id is None and len(self.patients) == 1:
            self.current_patient_id = self.patients[0]["id"]
        self.tree_patients.delete(*self.tree_patients.get_children())
        for p in self.patients:
            self.tree_patients.insert(
                "", "end", iid=str(p["id"]),
                values=(
                    "★" if p["id"] == self.current_patient_id else "",
                    p["full_name"], p["birth_date"] or "", p["sex"] or "", p["dni"] or "", p["cip"] or "", p["nhc"] or "",
                    p["nhc_alt"] or "", _smoking_summary(p), p["num_reports"],
                ),
            )
        # La fila del activo queda preseleccionada, así "Editar ficha..." sin
        # tocar la tabla abre la suya.
        if self.current_patient_id is not None:
            self.tree_patients.selection_set(str(self.current_patient_id))
        self._sync_checks(self.tree_patients)
        self._refresh_test_lists()
        self._update_status_patient()
        self._update_patient_dependent_tabs()
        self._update_active_patient_display()

    def _update_patient_dependent_tabs(self) -> None:
        state = "normal" if self.current_patient_id is not None else "disabled"
        for menu, label in self._patient_required_menu_entries:
            menu.entryconfigure(label, state=state)
        if state == "disabled" and self._current_page_key in self._patient_required_pages:
            self._show_page("pacientes")

    def _update_status_patient(self) -> None:
        patient = next((p for p in self.patients if p["id"] == self.current_patient_id), None)
        texto = f"Paciente: {patient['full_name']}" if patient else "Ningún paciente activo"
        filtro = self._lab_filter_text()
        # El filtro se ve siempre (barra inferior y cabecera de cada panel):
        # que nunca se olvide que hay laboratorios fuera de los gráficos.
        self._set_status(f"{texto} · {filtro}" if filtro else texto)

    def _lab_filter_text(self) -> str:
        """"" sin filtro; si no, qué laboratorios se están usando."""
        excluidos = get_excluded_labs(self.con)
        if not excluidos:
            return ""
        nombre = lambda lab: lab or LAB_UNKNOWN  # noqa: E731
        incluidos = [nombre(l["lab"]) for l in list_labs(self.con) if l["lab"] not in excluidos]
        return f"Datos solo de: {', '.join(incluidos)}"

    def _choose_labs(self) -> None:
        """Análisis → Laboratorios incluidos...: elegir de qué laboratorios
        salen los datos de los gráficos, los paneles clínicos, el Resumen y
        el PDF (por defecto, todos). Métodos o rangos distintos entre
        centros pueden falsear una serie mezclada. No afecta a la
        exportación Excel/CSV ni al Explorador BD (datos en bruto)."""
        labs = list_labs(self.con)
        if not labs:
            messagebox.showinfo("Laboratorios", "Todavía no hay informes importados.", parent=self)
            return
        excluidos = get_excluded_labs(self.con)
        dialog, body = self._new_dialog("Laboratorios incluidos")
        ttk.Label(
            body,
            text="Datos de qué laboratorios se usan en gráficos, paneles clínicos, Resumen e informe PDF.\n"
            "Cada laboratorio puede usar métodos o rangos distintos: quedarse con uno (o con varios "
            "compatibles) da series más coherentes. La exportación Excel/CSV no se filtra.",
            wraplength=520, justify="left",
        ).pack(anchor="w", pady=(0, 6))
        variables = {}
        for l in labs:
            var = tk.BooleanVar(value=l["lab"] not in excluidos)
            variables[l["lab"]] = var
            ttk.Checkbutton(
                body, text=f"{l['lab'] or LAB_UNKNOWN} ({l['n']} informe{'s' if l['n'] != 1 else ''})",
                variable=var,
            ).pack(anchor="w", padx=8, pady=2)

        def _aceptar() -> None:
            nuevos = sorted(lab for lab, var in variables.items() if not var.get())
            if len(nuevos) == len(variables):
                messagebox.showwarning("Laboratorios", "Deja al menos un laboratorio marcado.", parent=dialog)
                return
            set_setting(self.con, "excluded_labs", json.dumps(nuevos, ensure_ascii=False))
            set_excluded_labs(self.con, nuevos)
            dialog.destroy()
            self._refresh_test_lists()
            self._update_status_patient()

        botones = ttk.Frame(body)
        botones.pack(fill="x", pady=(PAD, 0))
        ttk.Button(botones, text="Marcar todos", bootstyle="secondary-outline",
                   command=lambda: [v.set(True) for v in variables.values()]).pack(side="left")
        boton_cancelar = ttk.Button(botones, text="Cancelar", command=dialog.destroy)
        boton_cancelar.pack(side="right")
        boton_ok = ttk.Button(botones, text="Aceptar", bootstyle="primary", command=_aceptar)
        boton_ok.pack(side="right", padx=(0, 8))
        self._same_width(boton_cancelar, boton_ok)
        self._center_dialog(dialog)

    # -- Entrada manual -----------------------------------------------------
    def _build_tab_manual(self) -> None:
        frame = self.tab_manual
        ttk.Label(frame, text="Analíticas", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=PAD, pady=(PAD, 0))
        ttk.Label(frame, text=AVISO_ENTRADA_MANUAL, bootstyle="warning", wraplength=900, justify="left").pack(
            anchor="w", padx=PAD, pady=(6, 4))
        ttk.Label(
            frame,
            text="Para analíticas cuyo PDF no se ha podido interpretar (o que no vienen en PDF): "
            "añade una fila por cada determinación y guarda. Los datos se guardan siempre para "
            "el paciente activo — cámbialo con Pacientes → Cambiar paciente activo... si es otra persona.",
            bootstyle="secondary", wraplength=900,
        ).pack(anchor="w", padx=PAD, pady=(0, 6))

        cabecera = ttk.Frame(frame)
        cabecera.pack(fill="x", padx=PAD, pady=(0, 6))
        ttk.Label(cabecera, text="Paciente activo:").grid(row=0, column=0, sticky="w")
        self.label_manual_patient = ttk.Label(cabecera, text="ninguno", bootstyle="info")
        self.label_manual_patient.grid(row=0, column=1, sticky="w", padx=(6, 24))
        ttk.Label(cabecera, text="Fecha (AAAA-MM-DD):").grid(row=0, column=2, sticky="w")
        self.var_manual_fecha = tk.StringVar(value=dt.date.today().isoformat())
        entry_fecha = ttk.Entry(cabecera, textvariable=self.var_manual_fecha, width=14)
        entry_fecha.grid(row=0, column=3, sticky="w", padx=(6, 0))
        ttk.Label(cabecera, text="Notas (opcional):").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.var_manual_notas = tk.StringVar()
        entry_notas = ttk.Entry(cabecera, textvariable=self.var_manual_notas, width=80)
        entry_notas.grid(row=1, column=1, columnspan=3, sticky="we", padx=(6, 0), pady=(6, 0))

        fila = ttk.Labelframe(frame, text="Añadir determinación", padding=PAD)
        fila.pack(fill="x", padx=PAD, pady=6)
        ttk.Label(fila, text="Prueba:").grid(row=0, column=0, sticky="w")
        self.var_manual_nombre = tk.StringVar()
        self.combo_manual_nombre = ttk.Combobox(fila, textvariable=self.var_manual_nombre, width=32)
        self.combo_manual_nombre.grid(row=0, column=1, sticky="w", padx=(6, 18))
        ttk.Label(fila, text="Valor:").grid(row=0, column=2, sticky="w")
        self.var_manual_valor = tk.StringVar()
        entry_valor = ttk.Entry(fila, textvariable=self.var_manual_valor, width=10)
        entry_valor.grid(row=0, column=3, sticky="w", padx=(6, 18))
        ttk.Label(fila, text="Unidad:").grid(row=0, column=4, sticky="w")
        self.var_manual_unidad = tk.StringVar()
        entry_unidad = ttk.Entry(fila, textvariable=self.var_manual_unidad, width=10)
        entry_unidad.grid(row=0, column=5, sticky="w", padx=(6, 18))
        ttk.Label(fila, text="Rango bajo:").grid(row=0, column=6, sticky="w")
        self.var_manual_ref_low = tk.StringVar()
        entry_ref_low = ttk.Entry(fila, textvariable=self.var_manual_ref_low, width=8)
        entry_ref_low.grid(row=0, column=7, sticky="w", padx=(6, 18))
        ttk.Label(fila, text="Rango alto:").grid(row=0, column=8, sticky="w")
        self.var_manual_ref_high = tk.StringVar()
        entry_ref_high = ttk.Entry(fila, textvariable=self.var_manual_ref_high, width=8)
        entry_ref_high.grid(row=0, column=9, sticky="w", padx=(6, 18))
        self.btn_manual_add = ttk.Button(
            fila, text="Añadir a la lista", bootstyle="primary", command=self._add_manual_row
        )
        self.btn_manual_add.grid(row=0, column=10, sticky="w")

        columns = ("raw_name", "value", "unit", "ref_low", "ref_high")
        self.tree_manual = ttk.Treeview(frame, columns=columns, show="headings", height=10, bootstyle="primary")
        for col, label, width in zip(
            columns, ("Prueba", "Valor", "Unidad", "Rango bajo", "Rango alto"), (300, 90, 90, 90, 90)
        ):
            self.tree_manual.heading(col, text=label)
            self.tree_manual.column(col, width=width)
        self.tree_manual.pack(fill="both", expand=True, padx=PAD, pady=(0, 6))
        self._manual_entries: list[dict] = []

        botones = ttk.Frame(frame)
        botones.pack(fill="x", padx=PAD, pady=(0, PAD))
        ttk.Button(
            botones, text="Quitar fila seleccionada", bootstyle="danger-outline",
            command=self._remove_manual_row,
        ).pack(side="left")
        self.btn_manual_save = ttk.Button(
            botones, text="Guardar analítica", bootstyle="success", command=self._save_manual_report
        )
        self.btn_manual_save.pack(side="right")
        self.combo_manual_nombre["values"] = list_known_test_names(self.con)

        # Validación al teclear: números donde van números (con signo y coma
        # o punto decimal), fechas solo con cifras y guiones, y textos sin
        # caracteres de control y con longitud máxima.
        decimal = r"-?\d{0,7}(?:[.,]\d{0,6})?"
        for entrada, patron in (
            (entry_fecha, r"[\d-]{0,10}"), (entry_valor, decimal), (entry_ref_low, decimal),
            (entry_ref_high, decimal), (entry_unidad, r"[^\x00-\x1f\x7f]{0,20}"),
            (entry_notas, r"[^\x00-\x1f\x7f]{0,200}"), (self.combo_manual_nombre, r"[^\x00-\x1f\x7f]{0,80}"),
        ):
            self._restrict(entrada, patron)

        # Se deshabilitan hasta que haya un paciente activo (§2.2): sin esto,
        # se podía rellenar y "Añadir a la lista" sin ningún paciente
        # elegido, aunque luego "Guardar analítica" lo bloqueara — confuso,
        # porque parecía que se podían entrar datos sin paciente.
        self._manual_input_widgets = (
            self.combo_manual_nombre, entry_valor, entry_unidad, entry_ref_low, entry_ref_high,
            entry_notas, self.btn_manual_add,
        )
        self._update_manual_tab_enabled()

    def _refresh_manual_patient_label(self) -> None:
        patient = next((p for p in self.patients if p["id"] == self.current_patient_id), None)
        self.label_manual_patient.configure(text=patient["full_name"] if patient else "ninguno")
        self._update_manual_tab_enabled()

    def _update_manual_tab_enabled(self) -> None:
        state = "normal" if self.current_patient_id is not None else "disabled"
        for widget in self._manual_input_widgets:
            widget.configure(state=state)
        self.btn_manual_save.configure(state=state)

    def _parse_float_field(self, text: str) -> float | None:
        text = text.strip().replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _add_manual_row(self) -> None:
        nombre = self.var_manual_nombre.get().strip()
        if not nombre:
            messagebox.showwarning("Falta la prueba", "Escribe el nombre de la determinación.", parent=self)
            return
        valor_text = self.var_manual_valor.get().strip()
        valor = self._parse_float_field(valor_text)
        if valor is None:
            messagebox.showwarning("Valor no válido", "El valor debe ser un número.", parent=self)
            return
        ref_low_text = self.var_manual_ref_low.get().strip()
        ref_high_text = self.var_manual_ref_high.get().strip()
        ref_low = self._parse_float_field(ref_low_text)
        ref_high = self._parse_float_field(ref_high_text)
        if ref_low_text and ref_low is None or ref_high_text and ref_high is None:
            messagebox.showwarning("Rango no válido", "El rango de referencia debe ser numérico.", parent=self)
            return
        if ref_low is not None and ref_high is not None and ref_low > ref_high:
            messagebox.showwarning(
                "Rango no válido", "El rango bajo no puede ser mayor que el rango alto.", parent=self
            )
            return
        unidad = self.var_manual_unidad.get().strip() or None
        entry = {"raw_name": nombre, "value_num": valor, "unit": unidad, "ref_low": ref_low, "ref_high": ref_high}
        self._manual_entries.append(entry)
        self.tree_manual.insert(
            "", "end",
            values=(nombre, f"{valor:g}", unidad or "", "" if ref_low is None else f"{ref_low:g}",
                    "" if ref_high is None else f"{ref_high:g}"),
        )
        self.var_manual_nombre.set("")
        self.var_manual_valor.set("")
        self.var_manual_unidad.set("")
        self.var_manual_ref_low.set("")
        self.var_manual_ref_high.set("")
        self.combo_manual_nombre.focus_set()

    def _remove_manual_row(self) -> None:
        selection = self.tree_manual.selection()
        if not selection:
            return
        for iid in selection:
            index = self.tree_manual.index(iid)
            del self._manual_entries[index]
            self.tree_manual.delete(iid)

    def _save_manual_report(self) -> None:
        if self.current_patient_id is None:
            messagebox.showwarning(
                "Sin paciente activo",
                "No hay ningún paciente activo. Elígelo con Pacientes → Cambiar paciente "
                "activo... antes de guardar.",
                parent=self,
            )
            return
        fecha = self.var_manual_fecha.get().strip()
        try:
            dt.datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Fecha no válida", "La fecha debe tener el formato AAAA-MM-DD.", parent=self)
            return
        if not self._manual_entries:
            messagebox.showwarning(
                "Sin determinaciones", "Añade al menos una determinación a la lista.", parent=self
            )
            return
        notas = self.var_manual_notas.get().strip() or None
        create_manual_report(self.con, self.current_patient_id, fecha, self._manual_entries, notes=notas)
        logger.info(
            "Entrada manual guardada: paciente id=%s, fecha=%s, %d determinaciones, con notas=%s",
            self.current_patient_id, fecha, len(self._manual_entries), notas is not None,
        )
        n = len(self._manual_entries)
        self._manual_entries = []
        self.tree_manual.delete(*self.tree_manual.get_children())
        self.var_manual_notas.set("")
        self.combo_manual_nombre["values"] = list_known_test_names(self.con)
        self._refresh_test_lists()
        self._refresh_stats()
        messagebox.showinfo("Analitix", f"Analítica guardada con {n} determinación(es).", parent=self)

    # -- Validación al teclear (entradas manuales) --------------------------
    def _restrict(self, entry, patron: str) -> None:
        """Solo deja escribir en `entry` texto que encaje entero con `patron`
        (validación "key" de Tk): números donde van números, sin caracteres
        de control, con longitud máxima. Comprobar que el valor tiene
        sentido es cosa de quien guarda (p. ej. `validate_reading`)."""
        regla = re.compile(patron)
        entry.configure(validate="key", validatecommand=(self.register(lambda P: bool(regla.fullmatch(P))), "%P"))

    # -- Entrada manual: tensión arterial ---------------------------------
    def _build_tab_tension(self) -> None:
        """Registro de tensión arterial del paciente activo: entrada manual,
        importación CSV (`blood_pressure.read_csv`) y borrado. Las
        mediciones se validan con `blood_pressure.validate_reading`."""
        frame = self.tab_tension
        ttk.Label(frame, text="Tensión arterial", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=PAD, pady=(PAD, 0))
        ttk.Label(frame, text=AVISO_ENTRADA_MANUAL, bootstyle="warning", wraplength=900, justify="left").pack(
            anchor="w", padx=PAD, pady=(6, 4))
        ttk.Label(
            frame,
            text="Cada medición se guarda para el paciente activo (cámbialo con Pacientes → Cambiar paciente "
            "activo...). «Lugar» indica si la tomaste en casa o en la consulta: las guías usan umbrales "
            "distintos para cada caso. Para importar un CSV, guarda antes la plantilla para ver el formato "
            "(también se aceptan las exportaciones de Omron Connect y Withings).",
            bootstyle="secondary", wraplength=900, justify="left",
        ).pack(anchor="w", padx=PAD, pady=(0, 6))
        cabecera = ttk.Frame(frame)
        cabecera.pack(fill="x", padx=PAD)
        ttk.Label(cabecera, text="Paciente activo:").pack(side="left")
        self.label_tension_patient = ttk.Label(cabecera, text="ninguno", bootstyle="info")
        self.label_tension_patient.pack(side="left", padx=6)
        ttk.Button(cabecera, text="ℹ️ ¿Cómo medirla?", bootstyle="info",
                   command=lambda: self._show_disclaimer_popup("Cómo medir la tensión en casa", BP_MEASUREMENT_GUIDE)
                   ).pack(side="right")

        forma = ttk.Labelframe(frame, text="Añadir medición", padding=PAD)
        forma.pack(fill="x", padx=PAD, pady=6)
        ahora = dt.datetime.now()
        self.vars_tension = {
            "fecha": tk.StringVar(value=ahora.strftime("%Y-%m-%d")), "hora": tk.StringVar(value=ahora.strftime("%H:%M")),
            "sistolica": tk.StringVar(), "diastolica": tk.StringVar(), "pulso": tk.StringVar(),
            "lugar": tk.StringVar(value=BP_PLACES[0]), "nota": tk.StringVar(),
        }
        campos = (
            ("fecha", "Fecha (AAAA-MM-DD):", 12, r"[\d-]{0,10}"),
            ("hora", "Hora (HH:MM):", 7, r"[\d:]{0,5}"),
            ("sistolica", "Sistólica (alta):", 6, r"\d{0,3}"),
            ("diastolica", "Diastólica (baja):", 6, r"\d{0,3}"),
            ("pulso", "Pulso (opcional):", 6, r"\d{0,3}"),
        )
        self._tension_widgets = []
        for col, (clave, texto, ancho, patron) in enumerate(campos):
            ttk.Label(forma, text=texto).grid(row=0, column=2 * col, sticky="w")
            entrada = ttk.Entry(forma, textvariable=self.vars_tension[clave], width=ancho)
            self._restrict(entrada, patron)
            entrada.grid(row=0, column=2 * col + 1, sticky="w", padx=(6, 14))
            self._tension_widgets.append(entrada)
        ttk.Label(forma, text="Lugar:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        lugar = ttk.Combobox(forma, textvariable=self.vars_tension["lugar"], values=BP_PLACES, state="readonly", width=10)
        lugar.grid(row=1, column=1, sticky="w", padx=(6, 14), pady=(8, 0))
        ttk.Label(forma, text="Nota (opcional):").grid(row=1, column=2, sticky="w", pady=(8, 0))
        nota = ttk.Entry(forma, textvariable=self.vars_tension["nota"], width=50)
        self._restrict(nota, r"[^\x00-\x1f\x7f]{0,200}")
        nota.grid(row=1, column=3, columnspan=5, sticky="we", padx=(6, 14), pady=(8, 0))
        guardar = ttk.Button(forma, text="Guardar medición", bootstyle="success", command=self._save_bp)
        guardar.grid(row=1, column=8, columnspan=2, sticky="e", pady=(8, 0))
        self._tension_widgets += [lugar, nota, guardar]

        columnas = ("fecha_hora", "sistolica", "diastolica", "pulso", "lugar", "nota", "origen")
        tabla = ttk.Frame(frame)
        tabla.pack(fill="both", expand=True, padx=PAD, pady=(0, 6))
        self.tree_tension = ttk.Treeview(tabla, columns=columnas, show="headings", height=14, selectmode="extended")
        for col, texto, ancho in zip(columnas, ("Fecha y hora", "Sistólica", "Diastólica", "Pulso", "Lugar", "Nota", "Origen"),
                                     (140, 80, 80, 60, 80, 360, 70)):
            self.tree_tension.heading(col, text=texto)
            self.tree_tension.column(col, width=ancho, anchor="w" if col in ("fecha_hora", "nota") else "center")
        self._checkbox_tree(self.tree_tension)
        barra = ttk.Scrollbar(tabla, orient="vertical", command=self.tree_tension.yview)
        self.tree_tension.configure(yscrollcommand=barra.set)
        self.tree_tension.pack(side="left", fill="both", expand=True)
        barra.pack(side="left", fill="y")

        botones = ttk.Frame(frame)
        botones.pack(fill="x", padx=PAD, pady=(0, PAD))
        self.label_tension_count = ttk.Label(botones, text="", bootstyle="secondary")
        self.label_tension_count.pack(side="left")
        borrar = ttk.Button(botones, text="Borrar marcadas", bootstyle="danger-outline", command=self._delete_bp_selected)
        plantilla = ttk.Button(botones, text="Guardar plantilla CSV...", bootstyle="secondary-outline",
                               command=self._save_bp_template)
        importar = ttk.Button(botones, text="Importar CSV...", bootstyle="success", command=self._import_bp_csv)
        for boton in (importar, plantilla, borrar):
            boton.pack(side="right", padx=(8, 0))
        self._same_width(borrar, plantilla, importar)
        self._tension_widgets += [borrar, importar]
        self._refresh_tension_page()

    def _refresh_tension_page(self) -> None:
        if not hasattr(self, "tree_tension"):
            return
        patient = next((p for p in self.patients if p["id"] == self.current_patient_id), None)
        self.label_tension_patient.configure(text=patient["full_name"] if patient else "ninguno")
        estado = "normal" if self.current_patient_id is not None else "disabled"
        for widget in self._tension_widgets:
            widget.configure(state="readonly" if estado == "normal" and isinstance(widget, ttk.Combobox) else estado)
        self.tree_tension.delete(*self.tree_tension.get_children())
        lecturas = list_bp_readings(self.con, self.current_patient_id) if self.current_patient_id else []
        for r in reversed(lecturas):  # la más reciente arriba
            self.tree_tension.insert(
                "", "end", iid=str(r["id"]),
                values=(r["measured_at"], r["systolic"], r["diastolic"], r["pulse"] or "", r["place"], r["note"] or "",
                        r["source"]),
            )
        self._sync_checks(self.tree_tension)
        self.label_tension_count.configure(text=f"{len(lecturas)} mediciones")
        self._refresh_bp_panel()

    def _save_bp(self) -> None:
        if self.current_patient_id is None:
            messagebox.showwarning("Sin paciente", "Elige antes un paciente activo.", parent=self)
            return
        v = {k: var.get() for k, var in self.vars_tension.items()}
        try:
            lectura = validate_reading(f"{v['fecha']} {v['hora']}", v["sistolica"], v["diastolica"], v["pulso"],
                                       v["lugar"], v["nota"], limits=self._bp_limits())
        except ValueError as exc:
            messagebox.showwarning("Medición no válida", str(exc)[:1].upper() + str(exc)[1:] + ".", parent=self)
            return
        if not add_bp_reading(self.con, self.current_patient_id, lectura):
            messagebox.showwarning("Ya existe", f"Ya hay una medición guardada el {lectura['measured_at']}.", parent=self)
            return
        self.con.commit()
        for clave in ("sistolica", "diastolica", "pulso", "nota"):
            self.vars_tension[clave].set("")
        self._refresh_tension_page()

    def _import_bp_csv(self) -> None:
        if self.current_patient_id is None:
            messagebox.showwarning("Sin paciente", "Elige antes un paciente activo.", parent=self)
            return
        ruta = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("Texto", "*.txt")], parent=self)
        if not ruta:
            return
        try:
            lecturas, errores = read_bp_csv(Path(ruta), limits=self._bp_limits())
        except OSError as exc:
            messagebox.showerror("Importar CSV", f"No se pudo leer el fichero: {exc}", parent=self)
            return
        nuevas = sum(add_bp_reading(self.con, self.current_patient_id, r, source="csv") for r in lecturas)
        self.con.commit()
        # Sin valores en el registro: solo recuentos (datos de salud).
        logger.info("CSV de tensión: %d nuevas, %d repetidas, %d errores", nuevas, len(lecturas) - nuevas, len(errores))
        texto = f"{nuevas} mediciones importadas"
        if len(lecturas) > nuevas:
            texto += f", {len(lecturas) - nuevas} ya existían (no se duplican)"
        if errores:
            texto += f".\n\n{len(errores)} líneas con error (no importadas):\n" + "\n".join(errores[:12])
            if len(errores) > 12:
                texto += f"\n… y {len(errores) - 12} más."
        (messagebox.showwarning if errores else messagebox.showinfo)("Importar CSV", texto, parent=self)
        self._refresh_tension_page()

    def _save_bp_template(self) -> None:
        ruta = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="plantilla_tension_arterial.csv",
                                            filetypes=[("CSV", "*.csv")], parent=self)
        if ruta:
            # BOM UTF-8 para que Excel muestre bien los acentos.
            Path(ruta).write_text(BP_CSV_TEMPLATE, encoding="utf-8-sig")

    def _delete_bp_selected(self) -> None:
        marcadas = [int(iid) for iid in self.tree_tension.selection()]
        if not marcadas or self.current_patient_id is None:
            messagebox.showinfo("Borrar", "Marca antes las mediciones que quieras borrar.", parent=self)
            return
        if messagebox.askyesno("Borrar", f"¿Borrar {len(marcadas)} mediciones? No se puede deshacer.", parent=self):
            delete_bp_readings(self.con, self.current_patient_id, marcadas)
            self._refresh_tension_page()

    # -- Paneles clínicos: tensión arterial --------------------------------
    def _build_tab_tension_panel(self) -> None:
        """Resumen y gráfico de la tensión arterial del paciente activo (ver
        `blood_pressure.home_week_summary`/`bp_summary_text` y
        `charts.bp_figure` para las fuentes). Se rehace al cambiar de
        paciente y al añadir, importar o borrar mediciones."""
        frame = self.tab_tension_panel
        ttk.Label(frame, text="Tensión arterial", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=PAD, pady=(PAD, 0))
        ttk.Label(frame, textvariable=self.status_var, bootstyle="info").pack(anchor="w", padx=PAD, pady=(0, 2))
        self._build_disclaimer_button(
            frame, "Aviso — Tensión arterial",
            "⚠ Apoyo informativo y de seguimiento, nunca un diagnóstico: la interpretación clínica final es "
            "siempre del médico.\n"
            "Protocolo de automedida en casa: Stergiou GS, et al. \"2021 European Society of Hypertension "
            "practice guidelines for office and out-of-office blood pressure measurement.\" J Hypertens. "
            "2021;39(7):1293-1302 (recuadros 6 y 7: 7 días, al menos 3 con al menos 12 lecturas; se descarta "
            "el primer día y se promedian las demás; las lecturas sueltas tienen poca precisión diagnóstica).\n"
            "Categorías: McEvoy JW, et al. \"2024 ESC Guidelines for the management of elevated blood "
            "pressure and hypertension.\" Eur Heart J. 2024;45(38):3912-4018 (tabla 5: en casa, no elevada "
            "< 120/70, elevada 120/70 a < 135/85, hipertensión ≥ 135/85; en la consulta, hipertensión "
            "≥ 140/90). Solo se clasifica una media que cumple el protocolo. Más detalle en Ayuda → "
            "Referencias científicas (\"referencias_tension_arterial\").",
        )
        self.text_bp_summary = tk.Text(frame, height=5, wrap="word", relief="flat")
        self.text_bp_summary.pack(fill="x", padx=PAD, pady=(0, 4))
        self._style_plain_widget(self.text_bp_summary)
        self.text_bp_summary.configure(state="disabled")

        # Intervalo a ver y periodo de comparación (fechas AAAA-MM-DD; en
        # blanco = sin límite). Las medias son descriptivas, sin clasificar.
        # Periodo del gráfico: los cuatro primeros cuentan hacia atrás desde
        # hoy; "Todo" es la vista general (con la ventana de años) y "Elegir
        # intervalo" muestra los campos de fechas y la comparación.
        self.bp_rango = "todo"
        botones_rango = ttk.Frame(frame)
        botones_rango.pack(fill="x", padx=PAD, pady=(0, 4))
        self.botones_bp_rango = {}
        for clave, texto in BP_RANGOS:
            boton = ttk.Button(botones_rango, text=texto, command=lambda c=clave: self._set_bp_rango(c),
                               bootstyle="primary" if clave == "todo" else "secondary-outline")
            boton.pack(side="left", padx=(0, 6))
            self.botones_bp_rango[clave] = boton
        self._same_width(*self.botones_bp_rango.values())
        periodos = ttk.Frame(frame)
        self.frame_bp_fechas = periodos
        self._bp_fechas_antes = botones_rango
        self.vars_bp_periodo = {k: tk.StringVar() for k in ("desde", "hasta", "cmp_desde", "cmp_hasta")}
        for col, (clave, texto) in enumerate((("desde", "Intervalo: desde"), ("hasta", "hasta"),
                                              ("cmp_desde", "Comparar con: desde"), ("cmp_hasta", "hasta"))):
            ttk.Label(periodos, text=texto).grid(row=0, column=2 * col, sticky="w", padx=(0 if col == 0 else 10, 4))
            entrada = ttk.Entry(periodos, textvariable=self.vars_bp_periodo[clave], width=11)
            self._restrict(entrada, r"[\d-]{0,10}")
            entrada.grid(row=0, column=2 * col + 1, sticky="w")
        aplicar = ttk.Button(periodos, text="Aplicar", bootstyle="primary", command=self._refresh_bp_panel)
        aplicar.grid(row=0, column=8, padx=(12, 4))
        ttk.Label(periodos, text="Fechas AAAA-MM-DD; en blanco, sin límite. Las medias son de las mediciones "
                  "en casa y no se clasifican.", bootstyle="secondary").grid(row=1, column=0, columnspan=10,
                                                                              sticky="w", pady=(2, 0))
        columnas = ("periodo", "fechas", "n", "dias", "sistolica", "diastolica", "pulso")
        self.tree_bp_medias = ttk.Treeview(frame, columns=columnas, show="headings", height=3)
        for col, texto, ancho in zip(columnas, ("Periodo", "Fechas", "Mediciones", "Días", "Sistólica media",
                                                "Diastólica media", "Pulso medio"),
                                     (170, 200, 90, 60, 110, 110, 90)):
            self.tree_bp_medias.heading(col, text=texto)
            self.tree_bp_medias.column(col, width=ancho, anchor="w" if col in ("periodo", "fechas") else "center")
        self.tree_bp_medias.pack(fill="x", padx=PAD, pady=(0, 6))
        self.chart_canvas_tension = ttk.Frame(frame)
        self.chart_canvas_tension.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self._refresh_bp_panel()

    def _bp_readings_windowed(self) -> tuple[list[dict], int]:
        """Mediciones del paciente activo en la ventana de años de los
        gráficos (`_windowed`), y cuántas quedan fuera."""
        lecturas = list_bp_readings(self.con, self.current_patient_id) if self.current_patient_id else []
        en_ventana = self._windowed([{**r, "fecha": r["measured_at"]} for r in lecturas])
        return en_ventana, len(lecturas) - len(en_ventana)

    def _set_bp_rango(self, clave: str) -> None:
        """Botón de periodo del panel de tensión: resalta el elegido, muestra
        los campos de fechas solo con "Elegir intervalo" y redibuja."""
        self.bp_rango = clave
        for c, boton in self.botones_bp_rango.items():
            boton.configure(bootstyle="primary" if c == clave else "secondary-outline")
        if clave == "intervalo":
            self.frame_bp_fechas.pack(fill="x", padx=PAD, pady=(0, 4), after=self._bp_fechas_antes)
        else:
            self.frame_bp_fechas.pack_forget()
        self._refresh_bp_panel()

    def _bp_periodo(self, desde_clave: str, hasta_clave: str) -> tuple[str | None, str | None] | None:
        """(desde, hasta) del formulario (ver `_check_period`)."""
        return _check_period(*(self.vars_bp_periodo[k].get() for k in (desde_clave, hasta_clave)))

    def _refresh_bp_panel(self) -> None:
        if not hasattr(self, "text_bp_summary"):
            return
        dias = desde_eje = None
        intervalo = comparacion = None
        if self.bp_rango in BP_RANGO_DIAS:
            dias = BP_RANGO_DIAS[self.bp_rango]
            desde_eje = dt.date.today() - dt.timedelta(days=dias - 1)
            intervalo = (desde_eje.isoformat(), None)
        elif self.bp_rango == "intervalo":
            try:
                intervalo = self._bp_periodo("desde", "hasta")
                comparacion = self._bp_periodo("cmp_desde", "cmp_hasta")
            except ValueError as exc:
                messagebox.showwarning("Fechas no válidas", f"Revisa las fechas (AAAA-MM-DD): {exc}.", parent=self)
                return
        todas = list_bp_readings(self.con, self.current_patient_id) if self.current_patient_id else []
        self.tree_bp_medias.delete(*self.tree_bp_medias.get_children())
        for nombre, periodo in (("Todo el histórico", (None, None)), ("Periodo mostrado", intervalo),
                                ("Periodo de comparación", comparacion)):
            if periodo is None or (nombre == "Todo el histórico" and not todas):
                continue
            s = bp_period_stats(todas, *periodo)
            if s is None:
                self.tree_bp_medias.insert("", "end", values=(nombre, "sin mediciones en casa", "", "", "", "", ""))
                continue
            self.tree_bp_medias.insert("", "end", values=(
                nombre, f"{s['desde']} a {s['hasta']}", s["n"], s["dias"], f"{s['systolic']:.0f}",
                f"{s['diastolic']:.0f}", "" if s["pulse"] is None else f"{s['pulse']:.0f}"))
        if intervalo is not None:
            desde, hasta = intervalo
            lecturas = [r for r in todas if (desde is None or r["measured_at"][:10] >= desde)
                        and (hasta is None or r["measured_at"][:10] <= hasta)]
            ocultas = 0  # el intervalo manda sobre la ventana de años
        else:
            lecturas, ocultas = self._bp_readings_windowed()
        self.text_bp_summary.configure(state="normal")
        self.text_bp_summary.delete("1.0", "end")
        self.text_bp_summary.insert("1.0", bp_summary_text(lecturas))
        self.text_bp_summary.configure(state="disabled")
        for child in self.chart_canvas_tension.winfo_children():
            child.destroy()
        titulo = "Tensión arterial" if intervalo is None else (
            f"Tensión arterial · {intervalo[0] or 'inicio'} a {intervalo[1] or 'hoy'}")
        if lecturas or desde_eje is not None:
            self._embed_figure(self._mark_window(bp_figure(lecturas, titulo, dias=dias, desde=desde_eje), ocultas,
                                                 "mediciones"), self.chart_canvas_tension)

    # -- Evolución --------------------------------------------------------
    def _build_tab_evolucion(self) -> None:
        frame = self.tab_evolucion
        left = ttk.Frame(frame)
        left.pack(side="left", fill="y", padx=PAD, pady=PAD)
        self.list_tests_evolucion = self._list_column(left, "Prueba (⚠ = alguna vez fuera de rango):", height=28)
        ttk.Button(
            left, text="Ver evolución", bootstyle="primary", command=self._show_evolution
        ).pack(pady=(8, 4), fill="x")
        ttk.Button(
            left, text="ℹ️ ¿Qué es este parámetro?", bootstyle="info",
            command=lambda: self._show_test_info(self.list_tests_evolucion.curselection()),
        ).pack(fill="x")
        ttk.Button(
            left, text="🎯 Objetivo indicado por mi médico...", bootstyle="secondary-outline",
            command=self._edit_target,
        ).pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(
            left, text="Mostrar mi rango personal", variable=self.var_personal_range,
            command=self._toggle_personal_range, bootstyle="round-toggle",
        ).pack(anchor="w", pady=(10, 0))
        ttk.Checkbutton(
            left, text=f"Ver todo el histórico (si no, {HISTORY_YEARS} años)", variable=self.var_full_history,
            command=self._toggle_full_history, bootstyle="round-toggle",
        ).pack(anchor="w", pady=(6, 0))

        self.chart_frame_evolucion = ttk.Frame(frame)
        self.chart_frame_evolucion.pack(side="left", fill="both", expand=True, padx=PAD, pady=PAD)
        self.chart_canvas_evolucion = ttk.Frame(self.chart_frame_evolucion)
        self.chart_canvas_evolucion.pack(fill="both", expand=True)

    def _show_evolution(self) -> None:
        selection = self.list_tests_evolucion.curselection()
        if not selection or self.current_patient_id is None:
            return
        canonical_id, label = self._evolution_tests[selection[0]]
        if canonical_id is None:
            return
        series = get_series(self.con, canonical_id, self.current_patient_id)
        fig = self._evolution_figure(series, label, canonical_id, with_personal=True)
        self._embed_figure(fig, self.chart_canvas_evolucion)

    def _edit_target(self) -> None:
        """Objetivo indicado por el médico para la prueba elegida en
        Evolución (tabla `targets`). Solo lo introduce la persona, copiándolo
        de lo que le haya indicado su médico; Analitix nunca lo propone ni lo
        calcula. En los gráficos sustituye al rango del laboratorio."""
        selection = self.list_tests_evolucion.curselection()
        if self.current_patient_id is None or not selection or self._evolution_tests[selection[0]][0] is None:
            messagebox.showinfo("Objetivo", "Elige antes una prueba de la lista.", parent=self)
            return
        canonical_id, label = self._evolution_tests[selection[0]]
        actual = get_target(self.con, self.current_patient_id, canonical_id) or {}
        unidad = next((s.get("unit") for s in get_series(self.con, canonical_id, self.current_patient_id)
                       if s.get("unit")), "")
        dialog, body = self._new_dialog("Objetivo indicado por mi médico")
        ttk.Label(body, text=label, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(
            body,
            text="Rellénalo solo si tu médico te ha indicado un objetivo concreto para esta prueba "
            "(por ejemplo, «LDL por debajo de 100 mg/dL»). Analitix nunca propone ni calcula "
            "objetivos: copia aquí el que te hayan dado, con las mismas unidades que el informe.\n\n"
            "Mientras exista, los gráficos de esta prueba muestran tu objetivo en lugar del rango del "
            "laboratorio, con la etiqueta «Objetivo indicado por su médico», y marcan ▲/▼ respecto a "
            "él. La tabla del Resumen y los informes PDF completo y de alterados siguen usando el "
            "rango del laboratorio. Deja vacío el límite que no te hayan indicado.",
            wraplength=480, justify="left",
        ).pack(anchor="w", pady=(4, 8))
        campos = ttk.Frame(body)
        campos.pack(anchor="w")
        valores = {}
        # Máximo arriba y mínimo abajo, como en un gráfico.
        for fila, (clave, texto) in enumerate((("high", "Máximo:"), ("low", "Mínimo:"))):
            ttk.Label(campos, text=texto).grid(row=fila, column=0, sticky="w", pady=2)
            entrada = ttk.Entry(campos, width=12)
            if actual.get(clave) is not None:
                entrada.insert(0, f"{actual[clave]:g}")
            entrada.grid(row=fila, column=1, sticky="w", padx=6, pady=2)
            ttk.Label(campos, text=unidad, bootstyle="secondary").grid(row=fila, column=2, sticky="w")
            valores[clave] = entrada
        ttk.Label(campos, text="Nota (opcional):").grid(row=2, column=0, sticky="w", pady=2)
        nota = ttk.Entry(campos, width=36)
        nota.insert(0, actual.get("note") or "")
        nota.grid(row=2, column=1, columnspan=2, sticky="w", padx=6, pady=2)
        if actual.get("set_on"):
            ttk.Label(body, text=f"Guardado el {actual['set_on']}.", bootstyle="secondary").pack(anchor="w", pady=(4, 0))

        def _redibujar() -> None:
            dialog.destroy()
            if self.list_tests_evolucion.curselection():
                self._show_evolution()

        def _guardar() -> None:
            textos = {k: e.get().strip() for k, e in valores.items()}
            numeros = {k: self._parse_float_field(t) for k, t in textos.items()}
            if any(textos[k] and numeros[k] is None for k in textos):
                messagebox.showwarning("Objetivo", "Escribe los límites como números (p. ej. 100 o 4,5).", parent=dialog)
                return
            try:
                set_target(self.con, self.current_patient_id, canonical_id, numeros["low"], numeros["high"],
                           nota.get().strip())
            except ValueError as exc:
                messagebox.showwarning("Objetivo", str(exc), parent=dialog)
                return
            _redibujar()

        def _quitar() -> None:
            delete_target(self.con, self.current_patient_id, canonical_id)
            _redibujar()

        botones = ttk.Frame(body)
        botones.pack(fill="x", pady=(PAD, 0))
        if actual:
            ttk.Button(botones, text="Quitar objetivo", bootstyle="danger-outline", command=_quitar).pack(side="left")
        boton_cancelar = ttk.Button(botones, text="Cancelar", command=dialog.destroy)
        boton_cancelar.pack(side="right")
        boton_ok = ttk.Button(botones, text="Guardar", bootstyle="primary", command=_guardar)
        boton_ok.pack(side="right", padx=(0, 8))
        self._same_width(boton_cancelar, boton_ok)
        self._center_dialog(dialog)

    def _show_test_info(self, selection: tuple[int, ...], tests: list | None = None) -> None:
        """Diálogo con la descripción en lenguaje llano de uno o varios
        parámetros seleccionados (ver `data/descripciones/`, §2.4/2.5 y §3.1
        del manual de usuario). Si a alguno todavía no le hemos hecho ficha,
        se indica igualmente cómo añadirla. `tests` permite reutilizar este
        diálogo con otra lista alineada índice a índice con `selection`
        (por defecto `self._evolution_tests`, usada por Evolución/
        Comparativa); la pestaña "Riesgo cardiovascular" le pasa
        `self._lipid_indices`."""
        tests = tests if tests is not None else self._evolution_tests
        candidatos = [tests[i] for i in selection if tests[i][0] is not None]
        if not candidatos:
            messagebox.showwarning(
                "Sin selección", "Selecciona antes uno o varios parámetros en la lista.", parent=self
            )
            return
        dialog, outer = self._new_dialog(
            "Acerca de este parámetro" if len(candidatos) == 1 else "Acerca de estos parámetros", resizable=True
        )

        # Ancho acotado a la pantalla (con un tope de 96 caracteres, cómodo
        # en pantallas normales/grandes) — estimación gruesa de ~9 px por
        # carácter a la fuente por defecto, suficiente para no desbordar en
        # pantallas pequeñas.
        max_width_chars = max(60, int(self.winfo_screenwidth() * 0.85 / 9))
        width = min(96, max_width_chars)

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True, pady=(0, 4))
        text = tk.Text(body, width=width, wrap="word", relief="flat")
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        for canonical_id, label in candidatos:
            descripcion = get_description(canonical_id)
            text.insert("end", f"{label}\n", "titulo")
            text.insert("end", (descripcion or "Todavía no hay una ficha para este parámetro.") + "\n\n")
        text.tag_configure("titulo", font=("Segoe UI", 10, "bold"))
        text.configure(state="disabled")
        self._style_plain_widget(text)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="left", fill="y")

        # Alto ajustado al contenido real, no a una heurística fija por nº
        # de parámetros seleccionados (que se quedaba corta con las fichas
        # largas de lenguaje llano + técnico, dejando el texto cortado sin
        # redimensionar la ventana a mano): tras fijar el ancho de arriba,
        # se mide cuántas líneas visuales ocupa ya el texto envuelto
        # (`count(..., "displaylines")`) y se usa esa cifra como alto,
        # acotada a un máximo cómodo de pantalla — más allá de ese máximo,
        # la `Scrollbar` de arriba permite ver el resto sin agrandar más la
        # ventana.
        # `update_idletasks()` no basta aquí: sin forzar un mapeo real de la
        # ventana, el ancho del widget se queda "virtual" en 1 píxel hasta
        # que pasa por el gestor de ventanas, y `count(..., "displaylines")`
        # calcula el ajuste de línea sobre un ancho que todavía no es el
        # real, devolviendo un número absurdamente alto (comprobado
        # empíricamente). `update()` fuerza ese mapeo. Nota para pruebas con
        # introspección (`root.withdraw()`): con la ventana principal oculta,
        # `dialog.transient(self)` impide que este diálogo llegue a mapearse
        # de verdad aunque se llame a `update()` — para probar este cálculo
        # concreto hace falta una ventana principal visible (o posicionada
        # fuera de pantalla con `geometry`), no oculta con `withdraw()`.
        dialog.update()
        display_lines = int(text.count("1.0", "end", "displaylines")[0])
        max_height_lines = max(15, int(self.winfo_screenheight() * 0.75 / 20))
        text.configure(height=min(max(display_lines + 1, 6), max_height_lines))

        ttk.Label(
            outer,
            text="Información general, no sustituye el consejo médico. Ver el manual de usuario "
            "(§3.1) para añadir o corregir una ficha.",
            bootstyle="secondary", wraplength=width * 7,
        ).pack(anchor="w")
        botones = ttk.Frame(outer)
        botones.pack(fill="x", pady=(PAD, 0))
        ttk.Button(botones, text="Cerrar", command=dialog.destroy).pack(side="right")
        self._center_dialog(dialog)
        self.wait_window(dialog)

    def _build_disclaimer_button(self, parent: ttk.Frame, titulo: str, texto: str) -> None:
        """Botón con icono de aviso que abre el texto legal/científico
        completo de un panel clínico (fórmulas, umbrales, citas,
        limitaciones) en un popup (`_show_disclaimer_popup`) en vez de
        mostrarlo siempre visible encima del gráfico, para dejar más
        espacio en pantalla al propio gráfico en todos los paneles
        clínicos."""
        ttk.Button(
            parent, text="⚠️ Aviso e información científica", bootstyle="warning",
            command=lambda: self._show_disclaimer_popup(titulo, texto),
        ).pack(anchor="w", padx=PAD, pady=(0, 6))

    def _show_disclaimer_popup(self, titulo: str, texto: str) -> None:
        """Diálogo de solo texto para el aviso completo de un panel
        clínico, mismo patrón de tamaño ajustado al contenido real que
        `_show_test_info`."""
        dialog, outer = self._new_dialog(titulo, resizable=True)

        max_width_chars = max(60, int(self.winfo_screenwidth() * 0.85 / 9))
        width = min(96, max_width_chars)

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True, pady=(0, 4))
        text = tk.Text(body, width=width, wrap="word", relief="flat")
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.insert("end", texto)
        text.configure(state="disabled")
        self._style_plain_widget(text)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="left", fill="y")

        dialog.update()
        display_lines = int(text.count("1.0", "end", "displaylines")[0])
        max_height_lines = max(15, int(self.winfo_screenheight() * 0.75 / 20))
        text.configure(height=min(max(display_lines + 1, 4), max_height_lines))

        botones = ttk.Frame(outer)
        botones.pack(fill="x", pady=(PAD, 0))
        ttk.Button(botones, text="Cerrar", command=dialog.destroy).pack(side="right")
        self._center_dialog(dialog)
        self.wait_window(dialog)

    # -- Comparativa ------------------------------------------------------
    def _build_tab_comparativa(self) -> None:
        frame = self.tab_comparativa
        left = ttk.Frame(frame)
        left.pack(side="left", fill="y", padx=PAD, pady=PAD)
        # Casillas en vez de lista con Ctrl/Shift (docs/GUIA_INTERFAZ.md §8),
        # en una columna del mismo ancho que la de Evolución.
        self._fixed_column(left)
        ttk.Label(
            left, text=f"Pruebas (máx. {MAX_COMPARISON_TESTS}; ⚠ = alguna vez fuera de rango):",
            justify="left", wraplength=left.cget("width"),
        ).pack(anchor="w")
        self.style.configure("Alterado.TCheckbutton", foreground=COLOR_ALTERADO)
        self.style.configure("Gris.TCheckbutton", foreground=COLOR_GRIS)
        self.checks_comparativa = self._scrollable_frame(left)
        self._comparativa_vars: list[tk.BooleanVar | None] = []
        ttk.Button(
            left, text="Comparar", bootstyle="primary", command=self._show_comparison
        ).pack(pady=(8, 4), fill="x")
        ttk.Button(
            left, text="ℹ️ ¿Qué son estos parámetros?", bootstyle="info",
            command=lambda: self._show_test_info(self._comparativa_selection()),
        ).pack(fill="x")
        ttk.Button(
            left, text="Desmarcar todo", bootstyle="secondary-outline",
            command=lambda: [v.set(False) for v in self._comparativa_vars if v is not None],
        ).pack(pady=(4, 0), fill="x")

        self.chart_frame_comparativa = ttk.Frame(frame)
        self.chart_frame_comparativa.pack(side="left", fill="both", expand=True, padx=PAD, pady=PAD)
        self.chart_canvas_comparativa = ttk.Frame(self.chart_frame_comparativa)
        self.chart_canvas_comparativa.pack(fill="both", expand=True)

    def _comparativa_selection(self) -> tuple[int, ...]:
        """Índices (alineados con `_evolution_tests`) de las pruebas marcadas."""
        return tuple(i for i, v in enumerate(self._comparativa_vars) if v is not None and v.get())

    def _show_comparison(self) -> None:
        selection = self._comparativa_selection()
        if not selection or self.current_patient_id is None:
            return
        series_by_test = {}
        for idx in selection:
            canonical_id, label = self._evolution_tests[idx]
            if canonical_id is None:
                continue
            series_by_test[label] = apply_target(
                get_series(self.con, canonical_id, self.current_patient_id),
                get_target(self.con, self.current_patient_id, canonical_id),
            )
        if not series_by_test:
            return
        fig = self._comparison_figure(series_by_test)
        self._embed_figure(fig, self.chart_canvas_comparativa)

    def _on_comparativa_check(self, var: tk.BooleanVar) -> None:
        if var.get() and len(self._comparativa_selection()) > MAX_COMPARISON_TESTS:
            var.set(False)
            messagebox.showwarning(
                "Demasiadas pruebas",
                f"Puedes comparar como máximo {MAX_COMPARISON_TESTS} pruebas a la vez.",
                parent=self,
            )

    # -- Resumen (semáforo) ------------------------------------------------
    def _build_tab_mapa_calor(self) -> None:
        """Mapa de calor del historial: una fila por parámetro, una columna
        por analítica, color según la posición respecto al rango de
        referencia de cada informe (`charts.heatmap_figure`)."""
        frame = self.tab_mapa_calor
        top = ttk.Frame(frame)
        top.pack(fill="x", padx=PAD, pady=(PAD, 4))
        ttk.Label(top, text="Mapa de calor", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Label(top, text="Mostrar:").pack(side="left", padx=(24, 6))
        self.var_mapa_calor_set = tk.StringVar(value=HEATMAP_OUT_OF_RANGE)
        combo = ttk.Combobox(
            top, textvariable=self.var_mapa_calor_set, state="readonly", width=36,
            values=[HEATMAP_OUT_OF_RANGE, HEATMAP_ALL, *HEATMAP_SETS],
        )
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _e: self._show_heatmap())
        ttk.Button(top, text="Ver mapa", bootstyle="primary", command=self._show_heatmap).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(
            frame,
            text="Cada fila es un parámetro y cada columna una analítica. Azul = por debajo del rango de "
            "referencia de ese informe, rojo = por encima (más intenso cuanto más lejos del rango), gris = "
            "dentro del rango. Pasa el ratón por una casilla para ver el valor, el rango y el laboratorio.",
            bootstyle="secondary", wraplength=1000, justify="left",
        ).pack(anchor="w", padx=PAD, pady=(0, 4))
        self.chart_canvas_mapa_calor = ttk.Frame(frame)
        self.chart_canvas_mapa_calor.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))

    def _heatmap_rows(self, choice: str) -> list[tuple[str, list[dict]]]:
        pid = self.current_patient_id
        if choice in HEATMAP_SETS:
            rows = []
            for label, ids in HEATMAP_SETS[choice]:
                series = sorted(get_merged_series(self.con, ids, pid).values(), key=lambda r: r["fecha"])
                if series:
                    rows.append((label, series))
            return rows
        tests = list_canonical_tests(self.con, pid)
        if choice == HEATMAP_OUT_OF_RANGE:
            tests = [t for t in tests if t.get("out_of_range")]
        rows = [(t["raw_name"], get_series(self.con, t["canonical_id"], pid)) for t in tests]
        return sorted(rows, key=lambda r: strip_accents(r[0]).casefold())

    def _show_heatmap(self) -> None:
        if self.current_patient_id is None:
            return
        choice = self.var_mapa_calor_set.get()
        rows = [r for r in self._heatmap_rows(choice) if r[1]]
        container = self.chart_canvas_mapa_calor
        if not rows:
            for child in container.winfo_children():
                child.destroy()
            ttk.Label(container, text="Sin datos para esta selección.", bootstyle="secondary").pack(anchor="w")
            return
        fig = heatmap_figure(rows, choice)
        fig.analitix_scroll = len(rows) > HEATMAP_SCROLL_ROWS
        self._embed_figure(fig, container)
        self._attach_heatmap_hover(fig)

    def _attach_heatmap_hover(self, fig) -> None:
        """Tooltip de casilla del mapa de calor (valor, fecha, rango,
        laboratorio) al pasar el ratón."""
        ax = next((a for a in fig.axes if hasattr(a, "analitix_heatmap")), None)
        if ax is None or fig.canvas is None:
            return
        meta = ax.analitix_heatmap
        n_cols = len(meta["dates"])
        annot = ax.annotate(
            "", xy=(0, 0), xytext=(12, 12), textcoords="offset points", fontsize=8, zorder=10,
            bbox=dict(boxstyle="round", fc="white", ec="#c3c2b7"),
        )
        annot.set_visible(False)

        def _on_move(event) -> None:
            item = None
            if event.inaxes is ax and event.xdata is not None and event.ydata is not None:
                i, j = int(round(event.ydata)), int(round(event.xdata))
                item = meta["cells"].get((i, j))
            if item is None:
                if annot.get_visible():
                    annot.set_visible(False)
                    fig.canvas.draw_idle()
                return
            fecha = item["fecha"][:10]
            texto = (
                f"{meta['rows'][i]}\n{fecha[8:10]}/{fecha[5:7]}/{fecha[:4]}\n"
                f"{item['value_num']:g} {item.get('unit') or ''}\nRango: {_format_range(item)}"
            )
            if item.get("lab"):
                texto += f"\n{item['lab']}"
            annot.xy = (j, i)
            # Cerca del borde derecho, el recuadro se abre hacia la izquierda.
            right = j > n_cols / 2
            annot.set_position((-12, 12) if right else (12, 12))
            annot.set_horizontalalignment("right" if right else "left")
            annot.set_text(texto.strip())
            annot.set_visible(True)
            fig.canvas.draw_idle()

        fig.canvas.mpl_connect("motion_notify_event", _on_move)

    def _build_tab_resumen(self) -> None:
        """Semáforo del último informe ("Semáforo/resumen de la última
        analítica" + "Alertas de cambio brusco"): todos los
        parámetros numéricos del informe más reciente en una sola tabla,
        en vez de tener que recorrer Evolución parámetro a parámetro.
        Reutiliza `flag_calc` ya calculado por informe (mismo criterio que
        el resto de la app) — no inventa ningún umbral clínico nuevo, solo
        el de "cambio brusco" (`CAMBIO_BRUSCO_PCT`), que es una elección de
        interfaz, no clínica."""
        frame = self.tab_resumen
        ttk.Label(frame, text="Resumen", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=PAD, pady=(PAD, 0)
        )
        ttk.Label(frame, textvariable=self.status_var, bootstyle="info").pack(
            anchor="w", padx=PAD, pady=(0, 2)
        )
        self.label_resumen_fecha = ttk.Label(
            frame, text="Último informe disponible", font=("Segoe UI", 11, "bold")
        )
        self.label_resumen_fecha.pack(anchor="w", padx=PAD, pady=(2, 4))
        ttk.Label(
            frame,
            text="⚠ Apoyo informativo y de seguimiento, nunca un diagnóstico: la interpretación "
            "clínica final es siempre del médico. Estado según el rango de referencia de cada "
            f"informe; \"⚡ cambio brusco\" cuando el valor varía ±{CAMBIO_BRUSCO_PCT:g}% o más "
            "respecto al informe anterior, esté o no dentro de rango. \"Tendencia\" (↑/→/↓) usa "
            "todo el histórico del parámetro, no solo el último informe, con el % anual que "
            "recorre del rango de referencia (p. ej. +100%/año = cruza todo el rango normal en "
            "un año, tendencia fuerte); → si no hay tendencia demostrable; \"—\" con menos de 5 "
            "analíticas o menos de 2 años.",
            bootstyle="secondary", wraplength=900, justify="left",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        # Dos vistas del mismo informe: la tabla y "Qué ha cambiado".
        notebook = ttk.Notebook(frame)
        notebook.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        tabla = ttk.Frame(notebook)
        cambios = ttk.Frame(notebook)
        posicion = ttk.Frame(notebook)
        notebook.add(tabla, text="Tabla")
        notebook.add(cambios, text="Qué ha cambiado")
        notebook.add(posicion, text="Posición en el rango")
        ttk.Label(
            posicion,
            text="Dónde está cada parámetro del último informe respecto a su rango de referencia, para "
            "comparar de un vistazo parámetros de escalas muy distintas. La franja es el rango (de su "
            "límite inferior al superior; con solo un límite superior, desde 0), el punto lleno el "
            "valor actual y el hueco el anterior. Fuera del rango: ▲ alto / ▼ bajo, más claro si la "
            "desviación es leve. Arriba, los más alejados. Estar en el centro de la franja no es "
            "«mejor» que estar cerca de un límite: todo el rango es normal.",
            bootstyle="secondary", wraplength=900, justify="left",
        ).pack(anchor="w", pady=(6, 2))
        self.label_resumen_posicion = ttk.Label(posicion, text="", bootstyle="secondary")
        self.label_resumen_posicion.pack(anchor="w", pady=(0, 4))
        self.chart_canvas_resumen_posicion = ttk.Frame(posicion)
        self.chart_canvas_resumen_posicion.pack(fill="both", expand=True)
        ttk.Label(
            cambios,
            text="Cada barra es el cambio de un parámetro respecto al informe anterior, medido en "
            "anchos de su rango de referencia (1 = moverse todo el ancho del rango normal), para "
            "poder comparar parámetros de escalas muy distintas. Rojo ✗ = se aleja del rango o sale "
            "de él; verde ✓ = se acerca o vuelve; gris = dentro del rango antes y ahora. Barra "
            "atenuada = el cambio cabe en la variación esperable (RCV: variación biológica de la "
            "propia persona + imprecisión del análisis, según estudios publicados); no se valora si "
            "los dos valores son de laboratorios distintos. Pasa el ratón por una barra para ver los "
            "valores, el % de cambio, el RCV y su fuente.",
            bootstyle="secondary", wraplength=900, justify="left",
        ).pack(anchor="w", pady=(6, 2))
        self.label_resumen_cambios = ttk.Label(cambios, text="", bootstyle="secondary")
        self.label_resumen_cambios.pack(anchor="w", pady=(0, 4))
        self.chart_canvas_resumen_cambios = ttk.Frame(cambios)
        self.chart_canvas_resumen_cambios.pack(fill="both", expand=True)

        columns = ("parametro", "valor", "referencia", "estado", "variacion", "tendencia")
        self.tree_resumen = ttk.Treeview(tabla, columns=columns, show="headings", height=22)
        for col, texto, width in (
            ("parametro", "Parámetro", 260),
            ("valor", "Valor", 140),
            ("referencia", "Rango de referencia", 160),
            ("estado", "Estado", 110),
            ("variacion", "Variación vs. informe anterior", 220),
            ("tendencia", "Tendencia", 130),
        ):
            self.tree_resumen.heading(col, text=texto)
            self.tree_resumen.column(col, width=width, anchor="center" if col == "tendencia" else "w")
        self.tree_resumen.tag_configure("alto", foreground=COLOR_ALTO)
        self.tree_resumen.tag_configure("bajo", foreground=COLOR_BAJO)
        self.tree_resumen.tag_configure("brusco", foreground=COLOR_BRUSCO)
        vsb = ttk.Scrollbar(tabla, orient="vertical", command=self.tree_resumen.yview)
        self.tree_resumen.configure(yscrollcommand=vsb.set)
        self.tree_resumen.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

    @staticmethod
    def _enrich_with_variation(r: dict) -> dict:
        """Añade a una fila (`canonical_id`/`raw_name`/`value_num`/`unit`/
        `ref_low`/`ref_high`/`flag_calc`/`valor_anterior`) el % de
        variación, si es un cambio brusco (`CAMBIO_BRUSCO_PCT`) y su
        prioridad de orden (0 = fuera de rango, 1 = cambio brusco dentro
        de rango, 2 = resto) — compartido por `_classify_latest_report`
        (informe "completo"/pestaña Resumen) y `_build_altered_rows`
        (informe "de alterados"), para no mantener el cálculo dos veces."""
        flag = r["flag_calc"]
        pct = None
        if r["valor_anterior"] not in (None, 0):
            pct = (r["value_num"] - r["valor_anterior"]) / r["valor_anterior"] * 100
        brusco = pct is not None and abs(pct) >= CAMBIO_BRUSCO_PCT
        orden = 0 if flag in ("alto", "bajo") else (1 if brusco else 2)
        return {**r, "pct": pct, "brusco": brusco, "orden": orden}

    @classmethod
    def _classify_latest_report(cls, summary: dict) -> list[dict]:
        """Enriquece `summary['resultados']` (`repository.
        get_latest_report_summary`) vía `_enrich_with_variation` y lo
        ordena por prioridad (alfabético dentro de cada grupo) —
        compartido por la pestaña Resumen y `_export_pdf` (informe
        "completo"), para no mantener la misma clasificación dos veces."""
        filas = [cls._enrich_with_variation(r) for r in summary["resultados"]]
        filas.sort(key=lambda f: (f["orden"], f["raw_name"] or ""))
        return filas

    def _refresh_resumen_panel(self) -> None:
        self.tree_resumen.delete(*self.tree_resumen.get_children())
        for canvas in (self.chart_canvas_resumen_cambios, self.chart_canvas_resumen_posicion):
            for child in canvas.winfo_children():
                child.destroy()
        self.label_resumen_cambios.configure(text="")
        self.label_resumen_posicion.configure(text="")
        summary = get_latest_report_summary(self.con, self.current_patient_id) if self.current_patient_id else None
        if not summary:
            self.label_resumen_fecha.configure(text="Sin informes con resultados numéricos para este paciente")
            return
        self.label_resumen_fecha.configure(text=f"Último informe: {summary['fecha'][:10]}")
        self._draw_changes(summary)
        self._draw_positions(summary)

        for f in self._classify_latest_report(summary):
            flag, pct, brusco = f["flag_calc"], f["pct"], f["brusco"]
            ref_low, ref_high = f["ref_low"], f["ref_high"]
            referencia = f"{ref_low:g} - {ref_high:g}" if ref_low is not None and ref_high is not None else "—"
            # ▲/▼ en vez de 🔴/🟠/🟢: los emojis de color no se distinguen con daltonismo.
            estado = {"alto": "▲ Alto", "bajo": "▼ Bajo"}.get(flag, "Normal")
            variacion = "—" if pct is None else f"{'⚡ ' if brusco else ''}{pct:+.1f}%"
            serie = get_series(self.con, f["canonical_id"], self.current_patient_id) if f["canonical_id"] else []
            tendencia = trend_arrow(serie, ref_low, ref_high) or "—"
            tag = flag if flag in ("alto", "bajo") else ("brusco" if brusco else "")
            self.tree_resumen.insert(
                "", "end",
                values=(
                    f["raw_name"], f"{f['value_num']:g} {f['unit'] or ''}".strip(), referencia, estado,
                    variacion, tendencia,
                ),
                tags=(tag,) if tag else (),
            )

    def _changes_rows(self, summary: dict) -> list[dict]:
        """Filas de "Qué ha cambiado" (con su RCV), compartidas por la
        pestaña Resumen y el informe PDF personalizado."""
        sex = get_patient_sex(self.con, self.current_patient_id)
        return [
            dict(label=f["raw_name"], value=f["value_num"], previous=f["valor_anterior"], unit=f["unit"],
                 ref_low=f["ref_low"], ref_high=f["ref_high"], pct=f["pct"],
                 rcv=classify_change(f["canonical_id"], f["valor_anterior"], f["value_num"], sex,
                                     f.get("lab_anterior"), f.get("lab")))
            for f in self._classify_latest_report(summary)
        ]

    def _draw_changes(self, summary: dict) -> None:
        """Gráfico "Qué ha cambiado" (`charts.changes_figure`) del último
        informe frente al anterior de cada parámetro."""
        filas = self._changes_rows(summary)
        con_anterior = [f for f in filas if f["previous"] is not None]
        medibles = [f for f in con_anterior if f["ref_low"] is not None or f["ref_high"] is not None]
        omitidos = []
        if len(filas) > len(con_anterior):
            omitidos.append(f"{len(filas) - len(con_anterior)} sin valor anterior")
        if len(con_anterior) > len(medibles):
            omitidos.append(f"{len(con_anterior) - len(medibles)} sin rango de referencia")
        self.label_resumen_cambios.configure(
            text=f"{len(medibles)} parámetros comparados" + (f" (se omiten {', '.join(omitidos)})" if omitidos else "")
        )
        if not medibles:
            ttk.Label(
                self.chart_canvas_resumen_cambios, text="No hay ningún parámetro con informe anterior para comparar.",
                bootstyle="secondary",
            ).pack(anchor="w")
            return
        fig = changes_figure(medibles, f"Qué ha cambiado — último informe ({summary['fecha'][:10]})")
        sin_cambio = fig.axes[0].analitix_changes_unchanged
        if sin_cambio:
            self.label_resumen_cambios.configure(
                text=self.label_resumen_cambios.cget("text") + f"; {sin_cambio} sin cambio no se dibujan"
            )
        fig.analitix_scroll = len(fig.axes[0].analitix_changes) > HEATMAP_SCROLL_ROWS
        self._embed_figure(fig, self.chart_canvas_resumen_cambios)
        self._attach_changes_hover(fig)

    def _draw_positions(self, summary: dict) -> None:
        """Gráfico "Posición en el rango" (`charts.position_figure`) del
        último informe, con el valor anterior de cada parámetro."""
        filas = [
            dict(label=f["raw_name"], value=f["value_num"], previous=f["valor_anterior"], unit=f["unit"],
                 ref_low=f["ref_low"], ref_high=f["ref_high"])
            for f in self._classify_latest_report(summary)
        ]
        fig = position_figure(filas, f"Posición en el rango — último informe ({summary['fecha'][:10]})")
        ax = fig.axes[0]
        dibujados, omitidos = len(ax.analitix_positions), ax.analitix_position_skipped
        self.label_resumen_posicion.configure(
            text=f"{dibujados} parámetros"
            + (f" (se omiten {omitidos} sin rango o con solo límite inferior)" if omitidos else "")
        )
        if not dibujados:
            return
        fig.analitix_scroll = dibujados > HEATMAP_SCROLL_ROWS
        self._embed_figure(fig, self.chart_canvas_resumen_posicion)

    def _attach_changes_hover(self, fig) -> None:
        """Tooltip de cada barra de "Qué ha cambiado": valores, % y rango."""
        ax = next((a for a in fig.axes if hasattr(a, "analitix_changes")), None)
        if ax is None or fig.canvas is None:
            return
        items = ax.analitix_changes
        annot = ax.annotate(
            "", xy=(0, 0), xytext=(12, -12), textcoords="offset points", fontsize=8, zorder=10, va="top",
            bbox=dict(boxstyle="round", fc="white", ec="#c3c2b7"),
        )
        annot.set_visible(False)
        estados = {"empeora": "se aleja del rango", "mejora": "se acerca al rango", "igual": "dentro del rango"}

        def _on_move(event) -> None:
            item = None
            if event.inaxes is ax and event.ydata is not None:
                i = int(round(event.ydata))
                if 0 <= i < len(items):
                    item = items[i]
            if item is None:
                if annot.get_visible():
                    annot.set_visible(False)
                    fig.canvas.draw_idle()
                return
            unit = item.get("unit") or ""
            pct = f" ({item['pct']:+.1f}%)" if item.get("pct") is not None else ""
            annot.set_text(
                f"{item['label']}\n{item['previous']:g} → {item['value']:g} {unit}{pct}\n"
                f"Rango: {_format_range(item)} · {estados[item['estado']]}" + _rcv_tooltip(item.get("rcv"))
            )
            annot.xy = (0, i)
            annot.set_visible(True)
            fig.canvas.draw_idle()

        fig.canvas.mpl_connect("motion_notify_event", _on_move)

    # -- Riesgo cardiovascular ---------------------------------------------
    def _build_tab_riesgo_cv(self) -> None:
        """Perfil lipídico y riesgo cardiovascular orientativo (ver
        `lipid_risk.py` para las fórmulas y sus fuentes científicas
        citadas)."""
        frame = self.tab_riesgo_cv
        ttk.Label(frame, text="Riesgo cardiovascular", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=PAD, pady=(PAD, 0)
        )
        ttk.Label(frame, textvariable=self.status_var, bootstyle="info").pack(
            anchor="w", padx=PAD, pady=(0, 2)
        )
        ttk.Label(
            frame, text="Último panel lipídico disponible", font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=PAD, pady=(2, 4))
        self._build_disclaimer_button(
            frame, "Aviso — Riesgo cardiovascular",
            "⚠ Los umbrales de estos índices proceden de estudios en Colombia y EE. UU., "
            "no de población europea — las guías europeas actuales (ESC/EAS, SCORE2) no fijan "
            "un umbral así para estos índices: usan un cálculo de riesgo personalizado (edad, "
            "sexo, tensión, tabaquismo) que Analitix no calcula hoy. Ver \"ℹ ¿Qué es este "
            "índice?\" para el detalle completo con fuentes.",
        )
        self.text_lipid_summary = tk.Text(frame, height=11, wrap="word", relief="flat")
        self.text_lipid_summary.pack(fill="x", padx=PAD, pady=(0, PAD))
        self._style_plain_widget(self.text_lipid_summary)
        self.text_lipid_summary.configure(state="disabled")

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self.list_lipid_indices = self._list_column(left, "Índice (⚠ = alguna vez por encima del umbral orientativo):", height=10)
        ttk.Button(
            left, text="Ver evolución", bootstyle="primary", command=self._show_lipid_index
        ).pack(pady=(8, 4), fill="x")
        ttk.Button(
            left, text="ℹ️ ¿Qué es este índice?", bootstyle="info",
            command=lambda: self._show_test_info(self.list_lipid_indices.curselection(), tests=self._lipid_indices),
        ).pack(fill="x")

        self.chart_frame_riesgo_cv = ttk.Frame(body)
        self.chart_frame_riesgo_cv.pack(side="left", fill="both", expand=True, padx=(PAD, 0))
        self.chart_canvas_riesgo_cv = ttk.Frame(self.chart_frame_riesgo_cv)
        self.chart_canvas_riesgo_cv.pack(fill="both", expand=True)

        self._lipid_indices: list[tuple[str | None, str]] = []
        self._lipid_series: dict[str, list[dict]] = {}

    def _show_lipid_index(self) -> None:
        selection = self.list_lipid_indices.curselection()
        if not selection or self.current_patient_id is None:
            return
        canonical_id, label = self._lipid_indices[selection[0]]
        if canonical_id is None:
            return
        fig = self._evolution_figure(self._lipid_series.get(canonical_id, []), label, canonical_id)
        self._embed_figure(fig, self.chart_canvas_riesgo_cv)

    def _format_lipid_summary(self, s: dict) -> str:
        """Texto legible del último panel lipídico (`lipid_risk.
        get_latest_lipid_summary`): valores en crudo con su clasificación
        orientativa ATP III y los índices de riesgo cardiovascular
        calculables ese mismo día."""

        def linea_valor(etiqueta, valor, umbral_texto, extra=""):
            if valor is None:
                return f"{etiqueta}: no disponible en este informe"
            marca = " ⚠" if extra == "alto" or extra == "bajo" else ""
            return f"{etiqueta}: {valor:g} mg/dL{marca} — {umbral_texto}"

        def linea_indice(etiqueta, valor, umbral):
            if valor is None:
                return f"{etiqueta}: no calculable con este informe"
            marca = " ⚠ por encima del umbral orientativo" if valor >= umbral else " — dentro del umbral orientativo"
            return f"{etiqueta}: {valor:.2f}{marca} (umbral: {umbral:g})"

        ldl_nota = " (estimado por fórmula de Friedewald)" if s.get("ldl_estimado") else ""
        lineas = [
            f"Fecha del informe: {s['fecha'][:10]} (el más reciente con perfil lipídico completo; "
            "usa \"Ver evolución\" en la lista de abajo para el histórico de cada índice)",
            "",
            linea_valor("Colesterol total", s["total"], "umbral orientativo ATP III: 200 mg/dL", s["total_flag"]),
            linea_valor("Colesterol HDL", s["hdl"], "umbral orientativo ATP III: >= 40 mg/dL", s["hdl_flag"]),
            linea_valor(f"Colesterol LDL{ldl_nota}", s["ldl"], "umbral orientativo ATP III: 130 mg/dL", s["ldl_flag"]),
            linea_valor("Triglicéridos", s["tg"], "umbral orientativo ATP III: 150 mg/dL", s["tg_flag"]),
            "",
            linea_indice("Índice aterogénico (CT/HDL, Castelli I)", s["castelli_1"], 5.0),
            linea_indice("Índice LDL/HDL (Castelli II)", s["castelli_2"], 3.0),
            linea_indice("Índice TG/HDL", s["tg_hdl"], 3.0),
            "",
            "Valores orientativos de apoyo al seguimiento, no un diagnóstico — la lista de "
            "índices de abajo enlaza a las fuentes científicas completas (\"ℹ ¿Qué es este "
            "índice?\").",
        ]
        return "\n".join(lineas)

    def _refresh_lipid_panel(self) -> None:
        self._lipid_series = (
            get_lipid_index_series(self.con, self.current_patient_id) if self.current_patient_id else {}
        )
        self._lipid_indices = [(cid, LIPID_INDEX_LABELS[cid]) for cid in self._lipid_series]
        self.list_lipid_indices.delete(0, "end")
        for cid, label in self._lipid_indices:
            points = self._lipid_series[cid]
            fuera_de_rango = any(p["flag_calc"] == "alto" for p in points)
            idx = self.list_lipid_indices.size()
            self.list_lipid_indices.insert("end", f"{'⚠ ' if fuera_de_rango else ''}{label} (n={len(points)})")
            if fuera_de_rango:
                self.list_lipid_indices.itemconfig(idx, fg=COLOR_ALTERADO)

        summary = get_latest_lipid_summary(self.con, self.current_patient_id) if self.current_patient_id else None
        self.text_lipid_summary.configure(state="normal")
        self.text_lipid_summary.delete("1.0", "end")
        self.text_lipid_summary.insert(
            "end",
            self._format_lipid_summary(summary)
            if summary
            else "Sin datos de perfil lipídico (colesterol total + HDL en mg/dL) para este paciente.",
        )
        self.text_lipid_summary.configure(state="disabled")

    # -- Salud hepática -----------------------------------------------------
    def _build_tab_salud_hepatica(self) -> None:
        """Función e índices hepáticos orientativos (ver `hepatic_risk.py`
        para las fórmulas y sus fuentes científicas citadas). Misma
        disposición que "❤ Riesgo cardiovascular"."""
        frame = self.tab_salud_hepatica
        ttk.Label(frame, text="Salud hepática", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=PAD, pady=(PAD, 0)
        )
        ttk.Label(frame, textvariable=self.status_var, bootstyle="info").pack(
            anchor="w", padx=PAD, pady=(0, 2)
        )
        ttk.Label(
            frame, text="Último panel hepático disponible", font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=PAD, pady=(2, 4))
        self._build_disclaimer_button(
            frame, "Aviso — Salud hepática",
            "⚠ FIB-4 y APRI son índices de cribado de fibrosis hepática, no un diagnóstico: "
            "un resultado alterado no sustituye una prueba de imagen, una biopsia ni la valoración "
            "de un hepatólogo. FIB-4 solo se muestra si se conoce la fecha de nacimiento del "
            "paciente (necesita la edad en la fecha de cada informe).\n"
            "Basado en: ratio AST/ALT o índice De Ritis (De Ritis, Coltorti y Giusti, 1957); "
            "APRI (Wai et al., Hepatology 2003, validado en hepatitis C); FIB-4 (Sterling et al., "
            "Hepatology 2006, validado en VIH/VHC), con los puntos de corte más recientes de la "
            "guía de práctica clínica de la AASLD para hígado graso (Rinella et al., Hepatology "
            "2023) en vez de los del estudio original de 2006. Ver \"ℹ ¿Qué es este índice?\" "
            "para la cita completa (DOI/PMID) y los límites de cada índice.",
        )
        self.text_hepatic_summary = tk.Text(frame, height=11, wrap="word", relief="flat")
        self.text_hepatic_summary.pack(fill="x", padx=PAD, pady=(0, PAD))
        self._style_plain_widget(self.text_hepatic_summary)
        self.text_hepatic_summary.configure(state="disabled")

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self.list_hepatic_indices = self._list_column(left, "Índice (⚠ = alguna vez por encima del umbral orientativo):", height=10)
        ttk.Button(
            left, text="Ver evolución", bootstyle="primary", command=self._show_hepatic_index
        ).pack(pady=(8, 4), fill="x")
        ttk.Button(
            left, text="ℹ️ ¿Qué es este índice?", bootstyle="info",
            command=lambda: self._show_test_info(self.list_hepatic_indices.curselection(), tests=self._hepatic_indices),
        ).pack(fill="x")

        self.chart_frame_salud_hepatica = ttk.Frame(body)
        self.chart_frame_salud_hepatica.pack(side="left", fill="both", expand=True, padx=(PAD, 0))
        self.chart_canvas_salud_hepatica = ttk.Frame(self.chart_frame_salud_hepatica)
        self.chart_canvas_salud_hepatica.pack(fill="both", expand=True)

        self._hepatic_indices: list[tuple[str | None, str]] = []
        self._hepatic_series: dict[str, list[dict]] = {}

    def _show_hepatic_index(self) -> None:
        selection = self.list_hepatic_indices.curselection()
        if not selection or self.current_patient_id is None:
            return
        canonical_id, label = self._hepatic_indices[selection[0]]
        if canonical_id is None:
            return
        fig = self._evolution_figure(self._hepatic_series.get(canonical_id, []), label, canonical_id)
        self._embed_figure(fig, self.chart_canvas_salud_hepatica)

    def _format_hepatic_summary(self, s: dict) -> str:
        """Texto legible del último panel hepático (`hepatic_risk.
        get_latest_hepatic_summary`): AST/ALT/plaquetas disponibles y los
        índices calculables ese mismo día, con la clasificación de 3 niveles
        de APRI/FIB-4 (bajo/intermedio/alto riesgo de fibrosis) en vez del
        simple alto/bajo del resto de la app — así se refleja tal cual la
        interpretación real de estos índices (ver
        `data/descripciones/idx_apri.txt`/`idx_fib4.txt`)."""

        def linea_valor(etiqueta, valor, unidad):
            if valor is None:
                return f"{etiqueta}: no disponible en este informe"
            return f"{etiqueta}: {valor:g} {unidad}"

        def clasifica_fibrosis(valor, bajo, alto):
            if valor < bajo:
                return "riesgo bajo"
            if valor > alto:
                return "riesgo alto ⚠"
            return "riesgo intermedio (se recomendaría una prueba adicional, p. ej. elastografía)"

        def linea_indice_fibrosis(etiqueta, valor, bajo, alto):
            if valor is None:
                return f"{etiqueta}: no calculable con este informe"
            return f"{etiqueta}: {valor:.2f} — {clasifica_fibrosis(valor, bajo, alto)}"

        de_ritis = s.get("de_ritis")
        if de_ritis is None:
            de_ritis_linea = "Ratio AST/ALT (De Ritis): no calculable con este informe"
        elif de_ritis > 2.0:
            de_ritis_linea = f"Ratio AST/ALT (De Ritis): {de_ritis:.2f} ⚠ — patrón sugestivo de daño hepático alcohólico"
        elif de_ritis < 1.0:
            de_ritis_linea = f"Ratio AST/ALT (De Ritis): {de_ritis:.2f} — patrón típico de hígado graso/hepatitis viral aguda (hallazgo común, no una alarma por sí solo)"
        else:
            de_ritis_linea = f"Ratio AST/ALT (De Ritis): {de_ritis:.2f}"

        edad_txt = f"{s['edad']} años" if s.get("edad") is not None else "no disponible (falta la fecha de nacimiento)"
        lineas = [
            f"Fecha del informe: {s['fecha'][:10]} (el más reciente con AST y ALT; "
            "usa \"Ver evolución\" en la lista de abajo para el histórico de cada índice)",
            f"Edad del paciente en esa fecha: {edad_txt}",
            "",
            linea_valor("AST", s["ast"], "U/L"),
            linea_valor("ALT", s["alt"], "U/L"),
            linea_valor("Plaquetas", s["plaquetes"], "x10³/µL"),
            "",
            de_ritis_linea,
            linea_indice_fibrosis("APRI", s.get("apri"), 0.5, 1.5),
            linea_indice_fibrosis("FIB-4", s.get("fib4"), 1.3, 2.67),
            "",
            "Valores orientativos de apoyo al seguimiento, no un diagnóstico — la lista de "
            "índices de abajo enlaza a las fuentes científicas completas (\"ℹ ¿Qué es este "
            "índice?\").",
        ]
        return "\n".join(lineas)

    def _refresh_hepatic_panel(self) -> None:
        self._hepatic_series = (
            get_hepatic_index_series(self.con, self.current_patient_id) if self.current_patient_id else {}
        )
        self._hepatic_indices = [(cid, HEPATIC_INDEX_LABELS[cid]) for cid in self._hepatic_series]
        self.list_hepatic_indices.delete(0, "end")
        for cid, label in self._hepatic_indices:
            points = self._hepatic_series[cid]
            fuera_de_rango = any(p["flag_calc"] == "alto" for p in points)
            idx = self.list_hepatic_indices.size()
            self.list_hepatic_indices.insert("end", f"{'⚠ ' if fuera_de_rango else ''}{label} (n={len(points)})")
            if fuera_de_rango:
                self.list_hepatic_indices.itemconfig(idx, fg=COLOR_ALTERADO)

        summary = get_latest_hepatic_summary(self.con, self.current_patient_id) if self.current_patient_id else None
        self.text_hepatic_summary.configure(state="normal")
        self.text_hepatic_summary.delete("1.0", "end")
        self.text_hepatic_summary.insert(
            "end",
            self._format_hepatic_summary(summary)
            if summary
            else "Sin datos de AST y ALT en U/L para este paciente.",
        )
        self.text_hepatic_summary.configure(state="disabled")

    # -- Función renal --------------------------------------------------
    def _build_tab_funcion_renal(self) -> None:
        """Función renal orientativa (ver `renal_risk.py` para las fórmulas
        y sus fuentes científicas citadas). Misma disposición que "❤ Riesgo cardiovascular"/
        "🧪 Salud hepática"."""
        frame = self.tab_funcion_renal
        ttk.Label(frame, text="Función renal", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=PAD, pady=(PAD, 0)
        )
        ttk.Label(frame, textvariable=self.status_var, bootstyle="info").pack(
            anchor="w", padx=PAD, pady=(0, 2)
        )
        ttk.Label(
            frame, text="Último informe con filtrado glomerular disponible", font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=PAD, pady=(2, 4))
        self._build_disclaimer_button(
            frame, "Aviso — Función renal",
            "⚠ Apoyo informativo y de seguimiento, nunca un diagnóstico: la interpretación "
            "clínica final es siempre del médico/nefrólogo.\n"
            "Basado en: clasificación y mapa de riesgo KDIGO 2012 (Kidney Int Suppl. 2013), "
            "verificado contra la adaptación oficial de la National Kidney Foundation; ratio "
            "urea/creatinina (Higgins, acutecaretesting.org, 2016); aviso de subida brusca de "
            "creatinina adaptado del algoritmo de alerta de AKI del NHS de Inglaterra (Sawhney et "
            "al., Nephrol Dial Transplant 2015) — señal débil, no una detección de fallo renal "
            "agudo. Ver \"ℹ ¿Qué es este índice?\" para la cita completa (DOI/PMID) de cada uno.",
        )
        self.text_renal_summary = tk.Text(frame, height=11, wrap="word", relief="flat")
        self.text_renal_summary.pack(fill="x", padx=PAD, pady=(0, PAD))
        self._style_plain_widget(self.text_renal_summary)
        self.text_renal_summary.configure(state="disabled")

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self.list_renal_indices = self._list_column(left, "Índice (⚠ = alguna vez por encima/debajo del umbral orientativo):", height=10)
        ttk.Button(
            left, text="Ver evolución", bootstyle="primary", command=self._show_renal_index
        ).pack(pady=(8, 4), fill="x")
        ttk.Button(
            left, text="ℹ️ ¿Qué es este índice?", bootstyle="info",
            command=lambda: self._show_test_info(self.list_renal_indices.curselection(), tests=self._renal_indices),
        ).pack(fill="x")

        self.chart_frame_funcion_renal = ttk.Frame(body)
        self.chart_frame_funcion_renal.pack(side="left", fill="both", expand=True, padx=(PAD, 0))
        self.chart_canvas_funcion_renal = ttk.Frame(self.chart_frame_funcion_renal)
        self.chart_canvas_funcion_renal.pack(fill="both", expand=True)

        self._renal_indices: list[tuple[str | None, str]] = []
        self._renal_series: dict[str, list[dict]] = {}

    def _show_renal_index(self) -> None:
        selection = self.list_renal_indices.curselection()
        if not selection or self.current_patient_id is None:
            return
        canonical_id, label = self._renal_indices[selection[0]]
        if canonical_id is None:
            return
        fig = self._evolution_figure(self._renal_series.get(canonical_id, []), label, canonical_id)
        self._embed_figure(fig, self.chart_canvas_funcion_renal)

    def _format_renal_summary(self, s: dict) -> str:
        """Texto legible del último panel renal (`renal_risk.
        get_latest_renal_summary`): FG/ACR con su categoría KDIGO y el
        riesgo cruzado G×A, más los índices calculables ese mismo día."""

        def linea_valor(etiqueta, valor, unidad, categoria=None):
            if valor is None:
                return f"{etiqueta}: no disponible en este informe"
            cat_txt = f" ({categoria})" if categoria else ""
            return f"{etiqueta}: {valor:g} {unidad}{cat_txt}"

        riesgo = s.get("riesgo_kdigo")
        if riesgo is None:
            riesgo_linea = (
                "Riesgo KDIGO (FG × albuminuria): no calculable — falta el ratio "
                "albúmina/creatinina de este informe"
            )
        else:
            riesgo_linea = f"Riesgo KDIGO (FG × albuminuria): {KDIGO_RISK_LABELS[riesgo]} ({riesgo})"

        urea_creat = s.get("urea_creatinina")
        if urea_creat is None:
            urea_creat_linea = "Ratio urea/creatinina: no calculable con este informe"
        elif urea_creat > 42.8:
            urea_creat_linea = f"Ratio urea/creatinina: {urea_creat:.1f} ⚠ — sugiere causa prerrenal"
        elif urea_creat < 21.4:
            urea_creat_linea = f"Ratio urea/creatinina: {urea_creat:.1f} ⚠ — sugiere causa renal intrínseca"
        else:
            urea_creat_linea = f"Ratio urea/creatinina: {urea_creat:.1f}"

        aki = s.get("aki_ratio")
        if aki is None:
            aki_linea = (
                "Comparación con la mediana del último año: no calculable (sin creatininas "
                "previas en la ventana de 8-365 días)"
            )
        elif aki >= 1.5:
            aki_linea = (
                f"Creatinina actual / mediana del último año: {aki:.2f} ⚠ — subida notable, "
                "coméntalo con tu médico"
            )
        else:
            aki_linea = f"Creatinina actual / mediana del último año: {aki:.2f}"

        lineas = [
            f"Fecha del informe: {s['fecha'][:10]} (el más reciente con filtrado glomerular "
            "estimado; usa \"Ver evolución\" en la lista de abajo para el histórico de cada índice)",
            "",
            linea_valor("Filtrado glomerular estimado", s["fg"], "mL/min", s.get("g_categoria")),
            linea_valor("Ratio albúmina/creatinina", s["acr"], "mg/g", s.get("a_categoria")),
            riesgo_linea,
            "",
            linea_valor("Urea", s["urea"], "mg/dL"),
            linea_valor("Creatinina", s["creatinina"], "mg/dL"),
            urea_creat_linea,
            aki_linea,
            "",
            "Valores orientativos de apoyo al seguimiento, no un diagnóstico — la lista de "
            "índices de abajo enlaza a las fuentes científicas completas (\"ℹ ¿Qué es este "
            "índice?\").",
        ]
        return "\n".join(lineas)

    def _refresh_renal_panel(self) -> None:
        self._renal_series = (
            get_renal_index_series(self.con, self.current_patient_id) if self.current_patient_id else {}
        )
        self._renal_indices = [(cid, RENAL_INDEX_LABELS[cid]) for cid in self._renal_series]
        self.list_renal_indices.delete(0, "end")
        for cid, label in self._renal_indices:
            points = self._renal_series[cid]
            # A diferencia de lípidos/hígado, aquí "bajo" también es
            # clínicamente interesante (ratio urea/creatinina sugiriendo
            # causa renal intrínseca), no solo "alto".
            fuera_de_rango = any(p["flag_calc"] in ("alto", "bajo") for p in points)
            idx = self.list_renal_indices.size()
            self.list_renal_indices.insert("end", f"{'⚠ ' if fuera_de_rango else ''}{label} (n={len(points)})")
            if fuera_de_rango:
                self.list_renal_indices.itemconfig(idx, fg=COLOR_ALTERADO)

        summary = get_latest_renal_summary(self.con, self.current_patient_id) if self.current_patient_id else None
        self.text_renal_summary.configure(state="normal")
        self.text_renal_summary.delete("1.0", "end")
        self.text_renal_summary.insert(
            "end",
            self._format_renal_summary(summary)
            if summary
            else "Sin filtrado glomerular estimado (mL/min) para este paciente.",
        )
        self.text_renal_summary.configure(state="disabled")

    def _build_tab_hemograma(self) -> None:
        """Hemograma y series roja/blanca orientativas (ver `hemogram_risk.py`
        para las fórmulas y sus fuentes científicas citadas). Misma disposición que "🧪 Salud hepática"/"🩺 Función renal"."""
        frame = self.tab_hemograma
        ttk.Label(frame, text="Hemograma", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=PAD, pady=(PAD, 0)
        )
        ttk.Label(frame, textvariable=self.status_var, bootstyle="info").pack(
            anchor="w", padx=PAD, pady=(0, 2)
        )
        ttk.Label(
            frame, text="Último informe con hemograma disponible", font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=PAD, pady=(2, 4))
        self._build_disclaimer_button(
            frame, "Aviso — Hemograma",
            "⚠ Apoyo informativo y de seguimiento, nunca un diagnóstico: la interpretación "
            "clínica final es siempre del médico/hematólogo.\n"
            "Basado en: NLR/PLR/LMR — Wang J et al., Clin Lab Anal. 2021;35(9):e23935; "
            "corroboración global de NLR — Wang Q et al., Front Cell Infect Microbiol. "
            "2025;15:1529532; índice de Mentzer — Mentzer WC Jr., Lancet. 1973;1(7808):882 "
            "(PMID 4123424); orientación de anemia por VCM/RDW — StatPearls NBK499994. No hay "
            "ningún score combinado de riesgo de leucemia u otras neoplasias hematológicas (no "
            "existe ninguno validado en la literatura) — solo el aviso puntual de linfocitosis "
            "sostenida > 5×10⁹/L en ≥2 informes descrito en el resumen de abajo (ESMO 2021/iwCLL "
            "2018). Ver \"ℹ ¿Qué es este índice?\" para la cita completa (DOI/PMID) y una "
            "explicación en lenguaje sencillo de cada uno.",
        )
        self.text_hemogram_summary = tk.Text(frame, height=13, wrap="word", relief="flat")
        self.text_hemogram_summary.pack(fill="x", padx=PAD, pady=(0, PAD))
        self._style_plain_widget(self.text_hemogram_summary)
        self.text_hemogram_summary.configure(state="disabled")

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self.list_hemogram_indices = self._list_column(left, "Índice (⚠ = alguna vez por encima del umbral orientativo):", height=10)
        ttk.Button(
            left, text="Ver evolución", bootstyle="primary", command=self._show_hemogram_index
        ).pack(pady=(8, 4), fill="x")
        ttk.Button(
            left, text="ℹ️ ¿Qué es este índice?", bootstyle="info",
            command=lambda: self._show_test_info(
                self.list_hemogram_indices.curselection(), tests=self._hemogram_indices
            ),
        ).pack(fill="x")

        self.chart_frame_hemograma = ttk.Frame(body)
        self.chart_frame_hemograma.pack(side="left", fill="both", expand=True, padx=(PAD, 0))
        self.chart_canvas_hemograma = ttk.Frame(self.chart_frame_hemograma)
        self.chart_canvas_hemograma.pack(fill="both", expand=True)

        self._hemogram_indices: list[tuple[str | None, str]] = []
        self._hemogram_series: dict[str, list[dict]] = {}

    def _show_hemogram_index(self) -> None:
        selection = self.list_hemogram_indices.curselection()
        if not selection or self.current_patient_id is None:
            return
        canonical_id, label = self._hemogram_indices[selection[0]]
        if canonical_id is None:
            return
        fig = self._evolution_figure(self._hemogram_series.get(canonical_id, []), label, canonical_id)
        self._embed_figure(fig, self.chart_canvas_hemograma)

    def _format_hemogram_summary(self, s: dict, alerta_linfocitosis: Optional[dict] = None) -> str:
        """Texto legible del último panel de hemograma (`hemogram_risk.
        get_latest_hemogram_summary`): orientación de anemia por VCM/RDW en
        lenguaje llano y técnico, más los índices calculables ese mismo día."""

        def linea_valor(etiqueta, valor, unidad):
            if valor is None:
                return f"{etiqueta}: no disponible en este informe"
            return f"{etiqueta}: {valor:g} {unidad}"

        vcm_cat = s.get("vcm_categoria")
        if vcm_cat == "microcitica":
            vcm_linea = (
                "Tamaño de los glóbulos rojos (VCM): más pequeño de lo habitual (microcitosis). "
                "En lenguaje sencillo: si hay anemia, esto orienta más hacia falta de hierro o un "
                "rasgo genético (talasemia) que hacia otras causas — mira el índice de Mentzer "
                "de abajo si aparece."
            )
        elif vcm_cat == "macrocitica":
            vcm_linea = (
                "Tamaño de los glóbulos rojos (VCM): más grande de lo habitual (macrocitosis). "
                "En lenguaje sencillo: si hay anemia, esto orienta más hacia falta de vitamina "
                "B12/ácido fólico, alcohol o algunos medicamentos que hacia falta de hierro."
            )
        elif vcm_cat == "normocitica":
            vcm_linea = "Tamaño de los glóbulos rojos (VCM): dentro del rango normal."
        else:
            vcm_linea = "Tamaño de los glóbulos rojos (VCM): no disponible en este informe."

        mentzer = s.get("mentzer")
        if mentzer is None:
            mentzer_linea = None
        elif mentzer < 13.0:
            mentzer_linea = f"Índice de Mentzer: {mentzer:.1f} ⚠ — orienta a rasgo talasémico"
        else:
            mentzer_linea = f"Índice de Mentzer: {mentzer:.1f} — orienta a anemia ferropénica"

        nlr_v, plr_v, lmr_v = s.get("nlr"), s.get("plr"), s.get("lmr")
        nlr_linea = (
            f"NLR (neutrófilos/linfocitos): {nlr_v:.2f}" + (" ⚠" if nlr_v is not None and nlr_v > 3.83 else "")
            if nlr_v is not None else "NLR: no calculable con este informe"
        )
        plr_linea = (
            f"PLR (plaquetas/linfocitos): {plr_v:.2f}" + (" ⚠" if plr_v is not None and plr_v > 185.52 else "")
            if plr_v is not None else "PLR: no calculable con este informe"
        )
        lmr_linea = f"LMR (linfocitos/monocitos): {lmr_v:.2f}" if lmr_v is not None else "LMR: no calculable con este informe"

        lineas = [
            f"Fecha del informe: {s['fecha'][:10]} (el más reciente con hemograma disponible; "
            "usa \"Ver evolución\" en la lista de abajo para el histórico de cada índice)",
            "",
            vcm_linea,
            linea_valor("RDW (variabilidad del tamaño de los glóbulos rojos)", s.get("rdw"), "%"),
            linea_valor("Hematíes", s.get("hematies"), "millones/µL"),
        ]
        if mentzer_linea:
            lineas.append(mentzer_linea)
        lineas += [
            "",
            "En lenguaje sencillo: NLR y PLR suelen subir con inflamación o estrés físico "
            "reciente (infección, cirugía...), sin señalar ninguna enfermedad concreta; LMR se "
            "muestra solo como tendencia, sin umbral fiable de \"bajo\".",
            nlr_linea,
            plr_linea,
            lmr_linea,
            "",
            "Valores orientativos de apoyo al seguimiento, no un diagnóstico — la lista de "
            "índices de abajo enlaza a las fuentes científicas completas (\"ℹ ¿Qué es este "
            "índice?\").",
        ]
        if alerta_linfocitosis:
            lineas += ["", self._format_lymphocytosis_alert(alerta_linfocitosis)]
        return "\n".join(lineas)

    def _format_lymphocytosis_alert(self, alerta: dict) -> str:
        """Texto del aviso de linfocitosis sostenida (`hemogram_risk.
        get_sustained_lymphocytosis_alert`); la explicación con citas
        completas vive en `data/descripciones/aviso_linfocitosis.txt`
        (`catalog.get_description`), nunca embebida aquí."""
        fechas = ", ".join(f[:10] for f in alerta["fechas"])
        descripcion = get_description("aviso_linfocitosis") or ""
        return (
            f"⚠ Linfocitos por encima de {LYMPHOCYTOSIS_HIGH:g} x10⁹/L en {len(alerta['fechas'])} "
            f"informes ({fechas}), último valor {alerta['ultimo_valor']:g} x10⁹/L.\n\n{descripcion}"
        )

    def _refresh_hemogram_panel(self) -> None:
        self._hemogram_series = (
            get_hemogram_index_series(self.con, self.current_patient_id) if self.current_patient_id else {}
        )
        self._hemogram_indices = [(cid, HEMOGRAM_INDEX_LABELS[cid]) for cid in self._hemogram_series]
        self.list_hemogram_indices.delete(0, "end")
        for cid, label in self._hemogram_indices:
            points = self._hemogram_series[cid]
            fuera_de_rango = any(p["flag_calc"] in ("alto", "bajo") for p in points)
            idx = self.list_hemogram_indices.size()
            self.list_hemogram_indices.insert("end", f"{'⚠ ' if fuera_de_rango else ''}{label} (n={len(points)})")
            if fuera_de_rango:
                self.list_hemogram_indices.itemconfig(idx, fg=COLOR_ALTERADO)

        summary = (
            get_latest_hemogram_summary(self.con, self.current_patient_id) if self.current_patient_id else None
        )
        alerta_linfocitosis = (
            get_sustained_lymphocytosis_alert(self.con, self.current_patient_id)
            if self.current_patient_id else None
        )
        if summary:
            texto = self._format_hemogram_summary(summary, alerta_linfocitosis)
        elif alerta_linfocitosis:
            texto = self._format_lymphocytosis_alert(alerta_linfocitosis)
        else:
            texto = "Sin hemograma (VCM) disponible para este paciente."
        self.text_hemogram_summary.configure(state="normal")
        self.text_hemogram_summary.delete("1.0", "end")
        self.text_hemogram_summary.insert("end", texto)
        self.text_hemogram_summary.configure(state="disabled")

    def _build_tab_hierro(self) -> None:
        """Metabolismo del hierro orientativo (ver `iron_risk.py` para las
        fórmulas y sus fuentes científicas citadas). Misma disposición que "🩸 Hemograma"/"🩺 Función renal"."""
        frame = self.tab_hierro
        ttk.Label(frame, text="Metabolismo del hierro", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=PAD, pady=(PAD, 0)
        )
        ttk.Label(frame, textvariable=self.status_var, bootstyle="info").pack(
            anchor="w", padx=PAD, pady=(0, 2)
        )
        ttk.Label(
            frame, text="Último informe con algún dato del metabolismo del hierro disponible",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=PAD, pady=(2, 4))
        self._build_disclaimer_button(
            frame, "Aviso — Metabolismo del hierro",
            "⚠ Apoyo informativo y de seguimiento, nunca un diagnóstico: la interpretación "
            "clínica final es siempre del médico.\n"
            "Basado en: umbrales de ferritina — WHO guideline on ferritin concentrations, 2020; "
            "umbrales de saturación de transferrina (TSAT) — University of Iowa Path Handbook y "
            "Medscape; fórmula de TSAT — Total Iron-Binding Capacity y protocolo NCT03920657. No "
            "se automatiza ningún diagnóstico diferencial entre ferropenia/anemia de trastorno "
            "crónico/sobrecarga de hierro: Analitix no guarda si hay un proceso inflamatorio "
            "activo, dato imprescindible para esa distinción. Ver \"ℹ ¿Qué es este índice?\" para "
            "la cita completa y una explicación en lenguaje sencillo de cada uno.",
        )
        self.text_iron_summary = tk.Text(frame, height=13, wrap="word", relief="flat")
        self.text_iron_summary.pack(fill="x", padx=PAD, pady=(0, PAD))
        self._style_plain_widget(self.text_iron_summary)
        self.text_iron_summary.configure(state="disabled")

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self.list_iron_indices = self._list_column(left, "Índice (⚠ = alguna vez fuera del rango orientativo):", height=10)
        ttk.Button(
            left, text="Ver evolución", bootstyle="primary", command=self._show_iron_index
        ).pack(pady=(8, 4), fill="x")
        ttk.Button(
            left, text="ℹ️ ¿Qué es este índice?", bootstyle="info",
            command=lambda: self._show_test_info(
                self.list_iron_indices.curselection(), tests=self._iron_indices
            ),
        ).pack(fill="x")

        self.chart_frame_hierro = ttk.Frame(body)
        self.chart_frame_hierro.pack(side="left", fill="both", expand=True, padx=(PAD, 0))
        self.chart_canvas_hierro = ttk.Frame(self.chart_frame_hierro)
        self.chart_canvas_hierro.pack(fill="both", expand=True)

        self._iron_indices: list[tuple[str | None, str]] = []
        self._iron_series: dict[str, list[dict]] = {}

    def _show_iron_index(self) -> None:
        selection = self.list_iron_indices.curselection()
        if not selection or self.current_patient_id is None:
            return
        canonical_id, label = self._iron_indices[selection[0]]
        if canonical_id is None:
            return
        fig = self._evolution_figure(self._iron_series.get(canonical_id, []), label, canonical_id)
        self._embed_figure(fig, self.chart_canvas_hierro)

    def _format_iron_summary(self, s: dict) -> str:
        """Texto legible del último panel de hierro (`iron_risk.
        get_latest_iron_summary`): valores en lenguaje llano y técnico, sin
        automatizar ningún diagnóstico diferencial."""

        def linea_valor(etiqueta, valor, unidad, flag=None):
            if valor is None:
                return f"{etiqueta}: no disponible en este informe"
            marca = " ⚠" if flag in ("alto", "bajo") else ""
            return f"{etiqueta}: {valor:g} {unidad}{marca}"

        tsat = s.get("tsat")
        tsat_nota = " (estimada a partir de hierro/transferrina, este informe no la trae calculada)" if s.get(
            "tsat_estimado"
        ) else ""
        tsat_linea = (
            f"Saturación de transferrina (TSAT): {tsat:.1f} %{tsat_nota}"
            + (" ⚠" if s.get("tsat_flag") in ("alto", "bajo") else "")
            if tsat is not None
            else "Saturación de transferrina (TSAT): no calculable con este informe"
        )

        lineas = [
            f"Fecha del informe: {s['fecha'][:10]} (el más reciente con algún dato del hierro; "
            "usa \"Ver evolución\" en la lista de abajo para el histórico de cada índice)",
            "",
            "En lenguaje sencillo: la ferritina son las reservas de hierro guardadas; el hierro y "
            "la saturación de transferrina reflejan el hierro circulando en ese momento. Un valor "
            "alto de ferritina no siempre significa exceso de hierro: también sube con cualquier "
            "inflamación o infección.",
            linea_valor("Ferritina (reservas de hierro)", s.get("ferritina"), "ng/mL", s.get("ferritina_flag")),
            tsat_linea,
            linea_valor("Hierro sérico", s.get("ferro"), "µg/dL"),
            linea_valor("Transferrina", s.get("transferrina"), "mg/dL"),
            "",
            "Analitix no combina estos valores en un diagnóstico automático (ferropenia / anemia "
            "de trastorno crónico / sobrecarga de hierro): esa distinción depende de si hay "
            "inflamación activa, un dato que esta app no guarda. Como orientación general (no una "
            "regla automática de esta app): ferritina y TSAT bajas a la vez apuntan más a "
            "ferropenia; ferritina normal/alta con TSAT baja puede deberse a inflamación "
            "enmascarando una ferropenia real; ferritina y TSAT altas a la vez requieren estudio "
            "de sobrecarga de hierro.",
            "",
            "Valores orientativos de apoyo al seguimiento, no un diagnóstico — la lista de "
            "índices de abajo enlaza a las fuentes científicas completas (\"ℹ ¿Qué es este "
            "índice?\").",
        ]
        return "\n".join(lineas)

    def _refresh_iron_panel(self) -> None:
        self._iron_series = (
            get_iron_index_series(self.con, self.current_patient_id) if self.current_patient_id else {}
        )
        self._iron_indices = [(cid, IRON_INDEX_LABELS[cid]) for cid in self._iron_series]
        self.list_iron_indices.delete(0, "end")
        for cid, label in self._iron_indices:
            points = self._iron_series[cid]
            fuera_de_rango = any(p["flag_calc"] in ("alto", "bajo") for p in points)
            idx = self.list_iron_indices.size()
            self.list_iron_indices.insert("end", f"{'⚠ ' if fuera_de_rango else ''}{label} (n={len(points)})")
            if fuera_de_rango:
                self.list_iron_indices.itemconfig(idx, fg=COLOR_ALTERADO)

        summary = get_latest_iron_summary(self.con, self.current_patient_id) if self.current_patient_id else None
        self.text_iron_summary.configure(state="normal")
        self.text_iron_summary.delete("1.0", "end")
        self.text_iron_summary.insert(
            "end",
            self._format_iron_summary(summary)
            if summary
            else "Sin datos del metabolismo del hierro para este paciente.",
        )
        self.text_iron_summary.configure(state="disabled")

    def _build_tab_inflamacion(self) -> None:
        """Inflamación (PCR + VSG) orientativa (ver `inflammation_risk.py`
        para las citas científicas). A diferencia del resto de
        paneles clínicos, aquí no hay ningún índice sintético que elegir en
        una lista: siempre se muestran las dos series superpuestas, porque
        no existe ningún índice combinado PCR+VSG validado (cinéticas
        demasiado distintas) — ver `inflammation_risk.py` para el detalle."""
        frame = self.tab_inflamacion
        ttk.Label(frame, text="Inflamación", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=PAD, pady=(PAD, 0)
        )
        ttk.Label(frame, textvariable=self.status_var, bootstyle="info").pack(
            anchor="w", padx=PAD, pady=(0, 2)
        )
        ttk.Label(
            frame, text="Últimos valores de PCR y VSG disponibles", font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=PAD, pady=(2, 4))
        self._build_disclaimer_button(
            frame, "Aviso — Inflamación",
            "⚠ Apoyo informativo y de seguimiento, nunca un diagnóstico: la interpretación "
            "clínica final es siempre del médico.\n"
            "No existe ningún índice combinado PCR+VSG validado: sus cinéticas son demasiado "
            "distintas para combinarlas con sentido fisiológico — la PCR sube y baja en días, la "
            "VSG mucho más despacio (Lapić I et al., Am J Clin Pathol. 2020;153(1):14-29; College "
            "of American Pathologists, \"C-Reactive Protein and Erythrocyte Sedimentation Rate "
            "Test Use\"). Por eso se muestran por separado, cada una clasificada contra el rango "
            "de referencia de su propio informe, y se avisa si discrepan entre sí. Ver "
            "\"ℹ️ ¿Qué es esto?\" para la cita completa y una explicación en lenguaje sencillo.",
        )
        self.text_inflammation_summary = tk.Text(frame, height=8, wrap="word", relief="flat")
        self.text_inflammation_summary.pack(fill="x", padx=PAD, pady=(0, 6))
        self._style_plain_widget(self.text_inflammation_summary)
        self.text_inflammation_summary.configure(state="disabled")

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self._fixed_column(left)
        ttk.Button(
            left, text="Ver evolución (PCR + VSG)", bootstyle="primary",
            command=self._show_inflammation_chart,
        ).pack(pady=(0, 4), fill="x")
        ttk.Button(
            left, text="ℹ️ ¿Qué es esto?", bootstyle="info",
            command=lambda: self._show_test_info((0,), tests=[("idx_inflamacion", "PCR + VSG")]),
        ).pack(fill="x")

        self.chart_frame_inflamacion = ttk.Frame(body)
        self.chart_frame_inflamacion.pack(side="left", fill="both", expand=True, padx=(PAD, 0))
        self.chart_canvas_inflamacion = ttk.Frame(self.chart_frame_inflamacion)
        self.chart_canvas_inflamacion.pack(fill="both", expand=True)

        self._inflammation_series: dict[str, list[dict]] = {}

    def _show_inflammation_chart(self) -> None:
        if self.current_patient_id is None or not self._inflammation_series:
            return
        series_by_test = {}
        if self._inflammation_series.get("pcr"):
            series_by_test["PCR"] = self._inflammation_series["pcr"]
        if self._inflammation_series.get("vsg"):
            series_by_test["VSG"] = self._inflammation_series["vsg"]
        if not series_by_test:
            return
        fig = self._comparison_figure(series_by_test)
        self._embed_figure(fig, self.chart_canvas_inflamacion)

    def _format_inflammation_summary(self, s: dict) -> str:
        """Texto legible del último panel de inflamación
        (`inflammation_risk.get_latest_inflammation_summary`): PCR y VSG
        clasificadas cada una contra el rango de referencia de su propio
        informe, más el aviso de discordancia si aplica."""

        def linea(row, etiqueta):
            if row is None:
                return f"{etiqueta}: no disponible para este paciente"
            marca = " ⚠" if row["flag_calc"] in ("alto", "bajo") else ""
            return f"{etiqueta} ({row['fecha'][:10]}): {row['value_num']:g} {row['unit']}{marca}"

        lineas = [
            linea(s.get("pcr"), "PCR"),
            linea(s.get("vsg"), "VSG"),
            "",
        ]
        if s.get("discordancia"):
            lineas.append(f"⚠ {s['discordancia']}")
            lineas.append("")
        lineas.append(
            "En lenguaje sencillo: la PCR reacciona en horas y baja rápido; la VSG tarda más en "
            "subir y mucho más en normalizarse — que no coincidan en un momento dado es esperable, "
            "no un error de laboratorio."
        )
        return "\n".join(lineas)

    def _refresh_inflammation_panel(self) -> None:
        self._inflammation_series = (
            get_inflammation_series(self.con, self.current_patient_id) if self.current_patient_id else {}
        )
        summary = (
            get_latest_inflammation_summary(self.con, self.current_patient_id)
            if self.current_patient_id
            else None
        )
        self.text_inflammation_summary.configure(state="normal")
        self.text_inflammation_summary.delete("1.0", "end")
        self.text_inflammation_summary.insert(
            "end",
            self._format_inflammation_summary(summary)
            if summary
            else "Sin PCR ni VSG disponibles para este paciente.",
        )
        self.text_inflammation_summary.configure(state="disabled")

    def _build_tab_acido_urico(self) -> None:
        """Ácido úrico/hiperuricemia orientativa (ver `uric_acid_risk.py`
        para las citas científicas). Mismo patrón que "🩸 Metabolismo del hierro", con un solo
        índice en la lista (un único parámetro, sin variantes que
        fusionar)."""
        frame = self.tab_acido_urico
        ttk.Label(frame, text="Ácido úrico", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=PAD, pady=(PAD, 0)
        )
        ttk.Label(frame, textvariable=self.status_var, bootstyle="info").pack(
            anchor="w", padx=PAD, pady=(0, 2)
        )
        ttk.Label(
            frame, text="Último valor de ácido úrico disponible", font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=PAD, pady=(2, 4))
        self._build_disclaimer_button(
            frame, "Aviso — Ácido úrico",
            "⚠ Apoyo informativo y de seguimiento, nunca un diagnóstico: la interpretación "
            "clínica final es siempre del médico.\n"
            "Umbral de hiperuricemia asintomática (≥6.8 mg/dL, unisex): FitzGerald JD, et al., "
            "para el American College of Rheumatology. \"2020 American College of Rheumatology "
            "Guideline for the Management of Gout.\" Arthritis Care Res (Hoboken). "
            "2020;72(6):744-760. Un valor alto es hiperuricemia, no un diagnóstico de gota: eso "
            "requiere confirmación por cristales de urato o el patrón clínico de los criterios "
            "ACR/EULAR 2015, que no viven en una analítica de sangre. Ver \"ℹ ¿Qué es este "
            "índice?\" para la cita completa y una explicación en lenguaje sencillo.",
        )
        self.text_uric_acid_summary = tk.Text(frame, height=6, wrap="word", relief="flat")
        self.text_uric_acid_summary.pack(fill="x", padx=PAD, pady=(0, PAD))
        self._style_plain_widget(self.text_uric_acid_summary)
        self.text_uric_acid_summary.configure(state="disabled")

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self.list_uric_acid_indices = self._list_column(left, "Índice (⚠ = alguna vez por encima del umbral orientativo):", height=10)
        ttk.Button(
            left, text="Ver evolución", bootstyle="primary", command=self._show_uric_acid_index
        ).pack(pady=(8, 4), fill="x")
        ttk.Button(
            left, text="ℹ️ ¿Qué es este índice?", bootstyle="info",
            command=lambda: self._show_test_info(
                self.list_uric_acid_indices.curselection(), tests=self._uric_acid_indices
            ),
        ).pack(fill="x")

        self.chart_frame_acido_urico = ttk.Frame(body)
        self.chart_frame_acido_urico.pack(side="left", fill="both", expand=True, padx=(PAD, 0))
        self.chart_canvas_acido_urico = ttk.Frame(self.chart_frame_acido_urico)
        self.chart_canvas_acido_urico.pack(fill="both", expand=True)

        self._uric_acid_indices: list[tuple[str | None, str]] = []
        self._uric_acid_series: dict[str, list[dict]] = {}

    def _show_uric_acid_index(self) -> None:
        selection = self.list_uric_acid_indices.curselection()
        if not selection or self.current_patient_id is None:
            return
        canonical_id, label = self._uric_acid_indices[selection[0]]
        if canonical_id is None:
            return
        fig = self._evolution_figure(self._uric_acid_series.get(canonical_id, []), label, canonical_id)
        self._embed_figure(fig, self.chart_canvas_acido_urico)

    def _format_uric_acid_summary(self, s: dict) -> str:
        """Texto legible del último valor de ácido úrico
        (`uric_acid_risk.get_latest_uric_acid_summary`)."""
        lineas = [
            f"Fecha del informe: {s['fecha'][:10]}",
            f"Ácido úrico: {s['value']:g} mg/dL" + (" ⚠ hiperuricemia" if s["flag"] == "alto" else ""),
            "",
        ]
        if s["flag"] == "alto":
            lineas.append(
                "En lenguaje sencillo: este valor indica hiperuricemia (exceso de ácido úrico en "
                "sangre), no un diagnóstico de gota — mucha gente vive años así sin desarrollarla. "
                f"Si ya estás en tratamiento por gota diagnosticada, el objetivo habitual es más "
                f"estricto (< {URATE_LOWERING_TARGET:g} mg/dL)."
            )
        else:
            lineas.append("En lenguaje sencillo: dentro del rango orientativo, sin hiperuricemia.")
        lineas += [
            "",
            "Valor orientativo de apoyo al seguimiento, no un diagnóstico — la lista de índices "
            "de abajo enlaza a la fuente científica completa (\"ℹ ¿Qué es este índice?\").",
        ]
        return "\n".join(lineas)

    def _refresh_uric_acid_panel(self) -> None:
        self._uric_acid_series = (
            get_uric_acid_series(self.con, self.current_patient_id) if self.current_patient_id else {}
        )
        self._uric_acid_indices = [(cid, URIC_ACID_INDEX_LABELS[cid]) for cid in self._uric_acid_series]
        self.list_uric_acid_indices.delete(0, "end")
        for cid, label in self._uric_acid_indices:
            points = self._uric_acid_series[cid]
            fuera_de_rango = any(p["flag_calc"] == "alto" for p in points)
            idx = self.list_uric_acid_indices.size()
            self.list_uric_acid_indices.insert("end", f"{'⚠ ' if fuera_de_rango else ''}{label} (n={len(points)})")
            if fuera_de_rango:
                self.list_uric_acid_indices.itemconfig(idx, fg=COLOR_ALTERADO)

        summary = (
            get_latest_uric_acid_summary(self.con, self.current_patient_id)
            if self.current_patient_id
            else None
        )
        self.text_uric_acid_summary.configure(state="normal")
        self.text_uric_acid_summary.delete("1.0", "end")
        self.text_uric_acid_summary.insert(
            "end",
            self._format_uric_acid_summary(summary)
            if summary
            else "Sin ácido úrico disponible para este paciente.",
        )
        self.text_uric_acid_summary.configure(state="disabled")

    def _build_tab_calcio(self) -> None:
        """Calcio corregido por albúmina (ver `calcium_risk.py` para las
        citas científicas). Mismo patrón que "🩹 Ácido úrico",
        con un solo índice en la lista."""
        frame = self.tab_calcio
        ttk.Label(frame, text="Calcio corregido", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=PAD, pady=(PAD, 0)
        )
        ttk.Label(frame, textvariable=self.status_var, bootstyle="info").pack(
            anchor="w", padx=PAD, pady=(0, 2)
        )
        ttk.Label(
            frame, text="Último calcio corregido disponible (solo en informes con calcio y albúmina)",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=PAD, pady=(2, 4))
        self._build_disclaimer_button(
            frame, "Aviso — Calcio corregido",
            "⚠ Apoyo informativo y de seguimiento, nunca un diagnóstico: la interpretación "
            "clínica final es siempre del médico.\n"
            "Fórmula: Payne RB, Little AJ, Williams RB, Milner JR. \"Interpretation of serum "
            "calcium in patients with abnormal serum proteins.\" Br Med J. 1973;4(5893):643-646. "
            "Se clasifica con el mismo rango de referencia que el laboratorio ya usa para el "
            "calcio total, sin inventar ningún umbral nuevo. Ver \"ℹ ¿Qué es este índice?\" para "
            "la cita completa y una explicación en lenguaje sencillo.",
        )
        self.text_calcio_summary = tk.Text(frame, height=6, wrap="word", relief="flat")
        self.text_calcio_summary.pack(fill="x", padx=PAD, pady=(0, PAD))
        self._style_plain_widget(self.text_calcio_summary)
        self.text_calcio_summary.configure(state="disabled")

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self.list_calcio_indices = self._list_column(left, "Índice (⚠ = alguna vez fuera del rango de referencia):", height=10)
        ttk.Button(
            left, text="Ver evolución", bootstyle="primary", command=self._show_calcio_index
        ).pack(pady=(8, 4), fill="x")
        ttk.Button(
            left, text="ℹ️ ¿Qué es este índice?", bootstyle="info",
            command=lambda: self._show_test_info(
                self.list_calcio_indices.curselection(), tests=self._calcio_indices
            ),
        ).pack(fill="x")

        self.chart_frame_calcio = ttk.Frame(body)
        self.chart_frame_calcio.pack(side="left", fill="both", expand=True, padx=(PAD, 0))
        self.chart_canvas_calcio = ttk.Frame(self.chart_frame_calcio)
        self.chart_canvas_calcio.pack(fill="both", expand=True)

        self._calcio_indices: list[tuple[str | None, str]] = []
        self._calcio_series: dict[str, list[dict]] = {}

    def _show_calcio_index(self) -> None:
        selection = self.list_calcio_indices.curselection()
        if not selection or self.current_patient_id is None:
            return
        canonical_id, label = self._calcio_indices[selection[0]]
        if canonical_id is None:
            return
        fig = self._evolution_figure(self._calcio_series.get(canonical_id, []), label, canonical_id)
        self._embed_figure(fig, self.chart_canvas_calcio)

    def _format_calcio_summary(self, s: dict) -> str:
        """Texto legible del último calcio corregido
        (`calcium_risk.get_latest_calcium_summary`)."""
        lineas = [
            f"Fecha del informe: {s['fecha'][:10]}",
            f"Calcio medido: {s['calcio_medido']:g} mg/dL",
            f"Albúmina: {s['albumina']:g} g/dL",
            f"Calcio corregido: {s['calcio_corregido']:.2f} mg/dL"
            + (" ⚠" if s["flag"] in ("alto", "bajo") else ""),
            "",
        ]
        if s["flag"] == "bajo":
            lineas.append(
                "En lenguaje sencillo: el calcio corregido sigue saliendo bajo aunque ya se ha "
                "tenido en cuenta la albúmina — puede valer la pena comentarlo con tu médico."
            )
        elif s["flag"] == "alto":
            lineas.append(
                "En lenguaje sencillo: el calcio corregido sigue saliendo alto aunque ya se ha "
                "tenido en cuenta la albúmina — puede valer la pena comentarlo con tu médico."
            )
        else:
            lineas.append(
                "En lenguaje sencillo: dentro del rango habitual una vez corregido por la "
                "albúmina."
            )
        lineas += [
            "",
            "Valor orientativo de apoyo al seguimiento, no un diagnóstico — la lista de índices "
            "de abajo enlaza a la fuente científica completa (\"ℹ ¿Qué es este índice?\").",
        ]
        return "\n".join(lineas)

    def _refresh_calcio_panel(self) -> None:
        self._calcio_series = (
            get_calcium_index_series(self.con, self.current_patient_id) if self.current_patient_id else {}
        )
        self._calcio_indices = [(cid, CALCIUM_INDEX_LABELS[cid]) for cid in self._calcio_series]
        self.list_calcio_indices.delete(0, "end")
        for cid, label in self._calcio_indices:
            points = self._calcio_series[cid]
            fuera_de_rango = any(p["flag_calc"] in ("alto", "bajo") for p in points)
            idx = self.list_calcio_indices.size()
            self.list_calcio_indices.insert("end", f"{'⚠ ' if fuera_de_rango else ''}{label} (n={len(points)})")
            if fuera_de_rango:
                self.list_calcio_indices.itemconfig(idx, fg=COLOR_ALTERADO)

        summary = (
            get_latest_calcium_summary(self.con, self.current_patient_id)
            if self.current_patient_id
            else None
        )
        self.text_calcio_summary.configure(state="normal")
        self.text_calcio_summary.delete("1.0", "end")
        self.text_calcio_summary.insert(
            "end",
            self._format_calcio_summary(summary)
            if summary
            else "Sin calcio y albúmina el mismo día disponibles para este paciente.",
        )
        self.text_calcio_summary.configure(state="disabled")

    def _build_tab_glucemia(self) -> None:
        """Glucosa media estimada (eAG) a partir de la HbA1c (ver
        `glycemic_risk.py` para las citas científicas). Mismo patrón que "🩹 Ácido úrico"."""
        frame = self.tab_glucemia
        ttk.Label(frame, text="Glucosa: glucosa media estimada (eAG) e índice TyG", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=PAD, pady=(PAD, 0)
        )
        ttk.Label(frame, textvariable=self.status_var, bootstyle="info").pack(
            anchor="w", padx=PAD, pady=(0, 2)
        )
        ttk.Label(
            frame, text="Última HbA1c disponible, traducida a glucosa media estimada",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=PAD, pady=(2, 4))
        self._build_disclaimer_button(
            frame, "Aviso — Glucosa (eAG y TyG)",
            "⚠ Apoyo informativo y de seguimiento, nunca un diagnóstico: la interpretación "
            "clínica final es siempre del médico.\n"
            "Fórmula ADAG: eAG (mg/dL) = 28.7 × HbA1c(%) − 46.7. Nathan DM, Kuenen J, Borg R, "
            "Zheng H, Schoenfeld D, Heine RJ, for the ADAG Study Group. \"Translating the A1C "
            "Assay Into Estimated Average Glucose Values.\" Diabetes Care. 2008;31(8):1473-1478. "
            "Los puntos de corte de HbA1c (normal <5.7%, prediabetes 5.7-6.4%, diabetes ≥6.5%) "
            "son umbrales diagnósticos oficiales de la ADA, pero requieren un HbA1c de "
            "laboratorio estandarizado para uso diagnóstico formal. Ver \"ℹ ¿Qué es este "
            "índice?\" para la cita completa, las limitaciones (anemia, ferropenia, embarazo...) "
            "y una explicación en lenguaje sencillo.\n"
            "Índice TyG = ln[triglicéridos (mg/dL) × glucosa (mg/dL) / 2], marcador indirecto de "
            "resistencia a la insulina (Simental-Mendía LE et al., Metab Syndr Relat Disord "
            "2008;6(4):299-304; fórmula corregida en Eur J Pediatr 2020;179:1171). Se muestra solo "
            "como tendencia, sin umbral: los puntos de corte publicados dependen de la población. "
            "Usa glucosa y triglicéridos del mismo informe; la fórmula se validó en ayunas.",
        )
        self.text_glucemia_summary = tk.Text(frame, height=6, wrap="word", relief="flat")
        self.text_glucemia_summary.pack(fill="x", padx=PAD, pady=(0, 6))
        self._style_plain_widget(self.text_glucemia_summary)
        self.text_glucemia_summary.configure(state="disabled")

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self.list_glucemia_indices = self._list_column(left, "Índice (⚠ = alguna vez en rango de diabetes):", height=10)
        ttk.Button(
            left, text="Ver evolución", bootstyle="primary", command=self._show_glucemia_index
        ).pack(pady=(8, 4), fill="x")
        ttk.Button(
            left, text="ℹ️ ¿Qué es este índice?", bootstyle="info",
            command=lambda: self._show_test_info(
                self.list_glucemia_indices.curselection(), tests=self._glucemia_indices
            ),
        ).pack(fill="x")
        ttk.Button(
            left, text="Ver evolución (Glucosa + eAG)", bootstyle="primary-outline",
            command=self._show_glucose_eag_chart,
        ).pack(pady=(12, 4), fill="x")
        ttk.Button(
            left, text="ℹ️ ¿Qué es esto?", bootstyle="info",
            command=lambda: self._show_test_info((0,), tests=[("idx_glucosa_eag", "Glucosa + eAG")]),
        ).pack(fill="x")

        self.chart_frame_glucemia = ttk.Frame(body)
        self.chart_frame_glucemia.pack(side="left", fill="both", expand=True, padx=(PAD, 0))
        self.chart_canvas_glucemia = ttk.Frame(self.chart_frame_glucemia)
        self.chart_canvas_glucemia.pack(fill="both", expand=True)

        self._glucemia_indices: list[tuple[str | None, str]] = []
        self._glucemia_series: dict[str, list[dict]] = {}
        self._glucose_series: list[dict] = []

    def _show_glucose_eag_chart(self) -> None:
        """Gráfico combinado Glucosa + eAG (idea §6 punto 2, "Gráficos
        combinados de dos parámetros, sin cálculo nuevo") — reutiliza
        `charts.comparison_figure` sin cambios, mismo patrón que
        `_show_inflammation_chart`."""
        if self.current_patient_id is None:
            return
        series_by_test = {}
        if self._glucose_series:
            series_by_test["Glucosa"] = self._glucose_series
        if self._glucemia_series.get("idx_eag"):
            series_by_test["eAG (desde HbA1c)"] = self._glucemia_series["idx_eag"]
        if not series_by_test:
            return
        fig = self._comparison_figure(series_by_test)
        self._embed_figure(fig, self.chart_canvas_glucemia)

    def _show_glucemia_index(self) -> None:
        selection = self.list_glucemia_indices.curselection()
        if not selection or self.current_patient_id is None:
            return
        canonical_id, label = self._glucemia_indices[selection[0]]
        if canonical_id is None:
            return
        fig = self._evolution_figure(self._glucemia_series.get(canonical_id, []), label, canonical_id)
        self._embed_figure(fig, self.chart_canvas_glucemia)

    def _format_glucemia_summary(self, s: dict) -> str:
        """Texto legible de la última HbA1c/eAG
        (`glycemic_risk.get_latest_glycemic_summary`)."""
        categorias = {"normal": "normal", "prediabetes": "prediabetes", "diabetes": "rango de diabetes"}
        lineas = [
            f"Fecha del informe: {s['fecha'][:10]}",
            f"HbA1c: {s['hba1c']:g}% ({categorias.get(s['categoria'], s['categoria'])})",
            f"Glucosa media estimada (eAG): {s['eag']:.0f} mg/dL",
            "",
        ]
        if s["categoria"] == "diabetes":
            lineas.append(
                f"En lenguaje sencillo: {s['hba1c']:g}% de HbA1c está en el rango diagnóstico de "
                f"diabetes de la ADA (≥{ADA_DIABETES_LOW:g}%) — coméntalo con tu médico si no lo "
                "has hecho ya; un valor de laboratorio aislado no sustituye el diagnóstico formal."
            )
        elif s["categoria"] == "prediabetes":
            lineas.append(
                f"En lenguaje sencillo: {s['hba1c']:g}% de HbA1c está en el rango de prediabetes "
                f"de la ADA ({ADA_NORMAL_HIGH:g}-{ADA_DIABETES_LOW:g}%), un momento razonable para "
                "hablar con tu médico sobre prevención."
            )
        else:
            lineas.append("En lenguaje sencillo: HbA1c dentro del rango normal.")
        lineas += [
            "",
            "Valores orientativos de apoyo al seguimiento, no un diagnóstico — la lista de "
            "índices de abajo enlaza a la fuente científica completa y a las limitaciones "
            "(\"ℹ ¿Qué es este índice?\").",
        ]
        return "\n".join(lineas)

    def _refresh_glucemia_panel(self) -> None:
        self._glucemia_series = (
            get_glycemic_index_series(self.con, self.current_patient_id) if self.current_patient_id else {}
        )
        self._glucose_series = (
            get_glucose_series(self.con, self.current_patient_id) if self.current_patient_id else []
        )
        if self.current_patient_id:
            # El índice TyG (`tyg_risk.py`) va en este mismo panel: también es metabolismo glucídico.
            self._glucemia_series.update(get_tyg_series(self.con, self.current_patient_id))
        etiquetas = {**GLYCEMIC_INDEX_LABELS, **TYG_INDEX_LABELS}
        self._glucemia_indices = [(cid, etiquetas[cid]) for cid in self._glucemia_series]
        self.list_glucemia_indices.delete(0, "end")
        for cid, label in self._glucemia_indices:
            points = self._glucemia_series[cid]
            fuera_de_rango = any(p["flag_calc"] == "alto" for p in points)
            idx = self.list_glucemia_indices.size()
            self.list_glucemia_indices.insert("end", f"{'⚠ ' if fuera_de_rango else ''}{label} (n={len(points)})")
            if fuera_de_rango:
                self.list_glucemia_indices.itemconfig(idx, fg=COLOR_ALTERADO)

        summary = (
            get_latest_glycemic_summary(self.con, self.current_patient_id)
            if self.current_patient_id
            else None
        )
        self.text_glucemia_summary.configure(state="normal")
        self.text_glucemia_summary.delete("1.0", "end")
        self.text_glucemia_summary.insert(
            "end",
            self._format_glucemia_summary(summary)
            if summary
            else "Sin HbA1c disponible para este paciente.",
        )
        self.text_glucemia_summary.configure(state="disabled")

    def _build_tab_tiroides(self) -> None:
        """TSH + T4L, gráfico combinado (ver `thyroid_risk.py` para las
        citas científicas, y su alcance deliberadamente
        reducido: solo el gráfico combinado, sin clasificación por
        cuadrante). Mismo patrón que "🔥 Inflamación", sin ningún índice
        sintético que elegir en una lista."""
        frame = self.tab_tiroides
        ttk.Label(frame, text="Tiroides", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=PAD, pady=(PAD, 0)
        )
        ttk.Label(frame, textvariable=self.status_var, bootstyle="info").pack(
            anchor="w", padx=PAD, pady=(0, 2)
        )
        ttk.Label(
            frame, text="Últimos valores de TSH y T4 libre disponibles", font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=PAD, pady=(2, 4))
        self._build_disclaimer_button(
            frame, "Aviso — Tiroides",
            "⚠ Apoyo informativo y de seguimiento, nunca un diagnóstico: la interpretación "
            "clínica final es siempre del médico.\n"
            "Este panel NO clasifica por cuadrante (hipotiroidismo/hipertiroidismo) ni interpreta "
            "el patrón: esa tabla es literalmente el criterio clínico diagnóstico estándar, y su "
            "umbral cambia con el embarazo, dato que Analitix no registra. Solo muestra las dos "
            "series juntas (relación fisiológica inversa: American Thyroid Association, "
            "\"Clinical Thyroidology for the Public\") clasificadas cada una contra el rango de "
            "referencia de su propio informe. Ver \"ℹ️ ¿Qué es esto?\" para la cita completa.",
        )
        self.text_thyroid_summary = tk.Text(frame, height=2, wrap="word", relief="flat")
        self.text_thyroid_summary.pack(fill="x", padx=PAD, pady=(0, 6))
        self._style_plain_widget(self.text_thyroid_summary)
        self.text_thyroid_summary.configure(state="disabled")

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self._fixed_column(left)
        ttk.Button(
            left, text="Ver evolución (TSH + T4L)", bootstyle="primary",
            command=self._show_thyroid_chart,
        ).pack(pady=(0, 4), fill="x")
        ttk.Button(
            left, text="ℹ️ ¿Qué es esto?", bootstyle="info",
            command=lambda: self._show_test_info((0,), tests=[("idx_tiroides", "TSH + T4L")]),
        ).pack(fill="x")

        self.chart_frame_tiroides = ttk.Frame(body)
        self.chart_frame_tiroides.pack(side="left", fill="both", expand=True, padx=(PAD, 0))
        self.chart_canvas_tiroides = ttk.Frame(self.chart_frame_tiroides)
        self.chart_canvas_tiroides.pack(fill="both", expand=True)

        self._thyroid_series: dict[str, list[dict]] = {}

    def _show_thyroid_chart(self) -> None:
        if self.current_patient_id is None or not self._thyroid_series:
            return
        series_by_test = {}
        if self._thyroid_series.get("tsh"):
            series_by_test["TSH"] = self._thyroid_series["tsh"]
        if self._thyroid_series.get("t4l"):
            series_by_test["T4 libre"] = self._thyroid_series["t4l"]
        if not series_by_test:
            return
        fig = self._comparison_figure(series_by_test)
        self._embed_figure(fig, self.chart_canvas_tiroides)

    def _format_thyroid_summary(self, s: dict) -> str:
        """Texto legible del último panel de tiroides
        (`thyroid_risk.get_latest_thyroid_summary`): TSH y T4L clasificadas
        cada una contra el rango de referencia de su propio informe, sin
        ningún texto de patrón/cuadrante — ver el aviso fijo de la pestaña."""

        def linea(row, etiqueta):
            if row is None:
                return f"{etiqueta}: no disponible para este paciente"
            marca = " ⚠" if row["flag_calc"] in ("alto", "bajo") else ""
            return f"{etiqueta} ({row['fecha'][:10]}): {row['value_num']:g} {row['unit']}{marca}"

        return "\n".join([linea(s.get("tsh"), "TSH"), linea(s.get("t4l"), "T4 libre")])

    def _refresh_thyroid_panel(self) -> None:
        self._thyroid_series = (
            get_thyroid_series(self.con, self.current_patient_id) if self.current_patient_id else {}
        )
        summary = (
            get_latest_thyroid_summary(self.con, self.current_patient_id)
            if self.current_patient_id
            else None
        )
        self.text_thyroid_summary.configure(state="normal")
        self.text_thyroid_summary.delete("1.0", "end")
        self.text_thyroid_summary.insert(
            "end",
            self._format_thyroid_summary(summary)
            if summary
            else "Sin TSH ni T4 libre disponibles para este paciente.",
        )
        self.text_thyroid_summary.configure(state="disabled")

    def _refresh_test_lists(self) -> None:
        tests = list_canonical_tests(self.con, self.current_patient_id) if self.current_patient_id else []
        normales = [t for t in tests if t["num_points"] >= self.min_points]
        pocos_datos = [t for t in tests if t["num_points"] < self.min_points]

        # `_evolution_tests` queda alineado fila a fila con el Listbox; la fila
        # separadora usa canonical_id=None para poder detectarla y no puede
        # seleccionarse como una prueba real.
        self._evolution_tests: list[tuple[str | None, str]] = [
            (t["canonical_id"], t["raw_name"]) for t in normales
        ]
        if pocos_datos:
            self._evolution_tests.append((None, ""))
            self._evolution_tests.extend((t["canonical_id"], t["raw_name"]) for t in pocos_datos)

        # (texto, color) de cada fila, alineadas también con `_evolution_tests`.
        filas: list[tuple[str, str | None]] = [
            (f"{'⚠ ' if t.get('out_of_range') else ''}{t['raw_name']}", COLOR_ALTERADO if t.get("out_of_range") else None)
            for t in normales
        ]
        if pocos_datos:
            filas.append((f"── Pocas analíticas (< {self.min_points} valores) ──", COLOR_GRIS))
            filas.extend(
                (f"{'⚠ ' if t.get('out_of_range') else ''}{t['raw_name']} (n={t['num_points']})",
                 COLOR_ALTERADO if t.get("out_of_range") else COLOR_GRIS)
                for t in pocos_datos
            )

        lista = self.list_tests_evolucion
        lista.delete(0, "end")
        for i, (texto, color) in enumerate(filas):
            lista.insert("end", texto)
            if color:
                lista.itemconfig(i, fg=color)

        for widget in self.checks_comparativa.winfo_children():
            widget.destroy()
        self._comparativa_vars = []
        estilos = {COLOR_ALTERADO: "Alterado.TCheckbutton", COLOR_GRIS: "Gris.TCheckbutton", None: "TCheckbutton"}
        for (canonical_id, _label), (texto, color) in zip(self._evolution_tests, filas):
            if canonical_id is None:
                ttk.Label(self.checks_comparativa, text=texto, foreground=COLOR_GRIS).pack(anchor="w", pady=(6, 2))
                self._comparativa_vars.append(None)
                continue
            var = tk.BooleanVar(value=False)
            self._comparativa_vars.append(var)
            ttk.Checkbutton(
                self.checks_comparativa, text=texto, variable=var, style=estilos[color],
                command=lambda v=var: self._on_comparativa_check(v),
            ).pack(anchor="w", pady=1)
        self._refresh_resumen_panel()
        self._refresh_lipid_panel()
        self._refresh_hepatic_panel()
        self._refresh_renal_panel()
        self._refresh_hemogram_panel()
        self._refresh_iron_panel()
        self._refresh_inflammation_panel()
        self._refresh_uric_acid_panel()
        self._refresh_calcio_panel()
        self._refresh_glucemia_panel()
        self._refresh_thyroid_panel()
        self._clear_charts()

    def _clear_charts(self) -> None:
        """Vacía los gráficos de Evolución/Comparativa/Riesgo cardiovascular/
        Salud hepática/Función renal/Hemograma/Metabolismo del hierro/
        Inflamación/Ácido úrico/Calcio corregido/Glucosa media estimada/
        Tiroides ya dibujados, si los hay. Ninguna pestaña muestra ya una
        descripción bajo el gráfico (2026-09-21: duplicaba el texto del
        botón "ℹ️ ¿Qué es este índice?"/"¿Qué es esto?"), así que solo
        hay que destruir el contenido de cada `chart_canvas_*`, no ningún
        label que vaciar.

        `_show_evolution`/`_show_comparison`/`_show_lipid_index`/
        `_show_hepatic_index`/`_show_renal_index` solo se ejecutan al pulsar
        sus botones, no automáticamente al cambiar de
        paciente o de pestaña; sin este vaciado, el gráfico (con sus
        valores fuera de rango en rojo) del paciente anterior seguía visible
        tras seleccionar otro paciente, aunque la lista de pruebas y el
        resto de datos ya fueran los correctos — riesgo real de confundir
        analíticas de personas distintas. Se llama desde `_refresh_test_lists`,
        que ya se invoca en todo cambio de paciente (`_refresh_patients`)
        y en cualquier otro cambio que pueda dejar el gráfico obsoleto
        (entrada manual guardada, fusión de pruebas, umbral de puntos).
        """
        for container in (
            self.chart_canvas_evolucion,
            self.chart_canvas_comparativa,
            self.chart_canvas_riesgo_cv,
            self.chart_canvas_salud_hepatica,
            self.chart_canvas_funcion_renal,
            self.chart_canvas_hemograma,
            self.chart_canvas_hierro,
            self.chart_canvas_inflamacion,
            self.chart_canvas_acido_urico,
            self.chart_canvas_calcio,
            self.chart_canvas_glucemia,
            self.chart_canvas_tiroides,
            self.chart_canvas_mapa_calor,
        ):
            for child in container.winfo_children():
                child.destroy()

    def _evolution_figure(
        self, series: list[dict], label: str, canonical_id: str | None, with_personal: bool = False
    ):
        """Gráfico de evolución común a Evolución y a todos los paneles:
        umbral de pocos datos del usuario y banda de variación esperable
        (RCV) de los dos últimos valores, si el parámetro tiene variación
        biológica (`rcv.py`; los índices calculados de los paneles no la
        tienen y se dibujan sin banda). El rango personal solo en Evolución
        (`with_personal`), donde está su interruptor."""
        hidden = len(series)
        series = self._windowed(series)
        hidden -= len(series)
        sex = get_patient_sex(self.con, self.current_patient_id)
        rcv = None
        if len(series) >= 2:
            rcv = classify_change(
                canonical_id, series[-2]["value_num"], series[-1]["value_num"],
                sex, series[-2].get("lab"), series[-1].get("lab"),
            )
        personal = (
            personal_range(canonical_id, series, sex) if with_personal and self.var_personal_range.get() else None
        )
        # Deriva lenta (CUSUM con la variación biológica), también contra el
        # rango del laboratorio y antes del objetivo del médico.
        deriva = cusum_note(cusum_drift(canonical_id, series, sex))
        # Después del RCV y del rango personal, que se miden contra el rango
        # del laboratorio: el objetivo del médico solo cambia lo que se dibuja.
        if canonical_id:
            series = apply_target(series, get_target(self.con, self.current_patient_id, canonical_id))
        # Filtrado glomerular (prueba suelta o índice "fg" del panel renal):
        # único umbral de velocidad con respaldo de guía (KDIGO, ver
        # `charts.KDIGO_RAPID_DECLINE_PER_YEAR`).
        if canonical_id in FG_IDS or canonical_id == "fg":
            series = [{**s, "kdigo_fg": True} for s in series]
        return self._mark_window(
            evolution_figure(series, label, self.min_points, rcv=rcv, personal=personal, note=deriva), hidden)

    def _comparison_figure(self, series_by_test: dict[str, list[dict]]):
        """`charts.comparison_figure` con la misma ventana de años que
        `_evolution_figure` (Comparativa e Inflamación/Tiroides/Glucosa)."""
        hidden = sum(len(s) for s in series_by_test.values())
        series_by_test = {label: self._windowed(s) for label, s in series_by_test.items()}
        hidden -= sum(len(s) for s in series_by_test.values())
        return self._mark_window(comparison_figure(series_by_test, self.min_points), hidden)

    def _windowed(self, series: list[dict]) -> list[dict]:
        """Los `HISTORY_YEARS` años anteriores a la última analítica de la
        serie (no a hoy: un historial antiguo no queda vacío), salvo con
        "Ver todo el histórico". `fecha` es "AAAA-MM-DD[ HH:MM:SS]"."""
        if self.var_full_history.get() or not series:
            return series
        last = series[-1]["fecha"][:10]
        cutoff = f"{int(last[:4]) - HISTORY_YEARS}{last[4:]}"
        return [s for s in series if s["fecha"][:10] >= cutoff]

    @staticmethod
    def _mark_window(fig, hidden: int, que: str = "analíticas"):
        """Aviso en el gráfico cuando la ventana de años oculta datos
        (`que`: "analíticas" o, en tensión arterial, "mediciones")."""
        if hidden:
            fig.text(
                0.99, 0.005, f"Últimos {HISTORY_YEARS} años · {hidden} {que} anteriores ocultas "
                "(Análisis → Ver todo el histórico)", ha="right", va="bottom", fontsize=7, color="#777777",
            )
        return fig

    def _history_menu_label(self) -> str:
        """Texto de la opción del menú Análisis: lo que hará al pulsarla."""
        return f"Ver solo los últimos {HISTORY_YEARS} años" if self.var_full_history.get() else "Ver todo el histórico"

    def _toggle_full_history(self) -> None:
        """Interruptor "Ver todo el histórico" (Evolución y menú Análisis):
        se recuerda y redibuja Evolución/Comparativa si tienen algo elegido;
        los paneles lo aplican al elegir su siguiente índice."""
        set_setting(self.con, "full_history", "1" if self.var_full_history.get() else "0")
        menu, index = self._history_menu
        menu.entryconfigure(index, label=self._history_menu_label())
        if self.list_tests_evolucion.curselection():
            self._show_evolution()
        if self._comparativa_selection():
            self._show_comparison()
        self._refresh_bp_panel()

    def _toggle_personal_range(self) -> None:
        """Interruptor "Mostrar mi rango personal" de Evolución: se recuerda
        y redibuja el gráfico si hay una prueba elegida."""
        set_setting(self.con, "personal_range", "1" if self.var_personal_range.get() else "0")
        if self.list_tests_evolucion.curselection():
            self._show_evolution()

    def _embed_figure(self, fig, container: ttk.Frame) -> None:
        for child in container.winfo_children():
            child.destroy()

        if len(fig.axes) <= 1 and not getattr(fig, "analitix_scroll", False):
            canvas = FigureCanvasTkAgg(fig, master=container)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
            self._attach_hover(fig)
            return

        # Gráficos de varios paneles (`charts.comparison_figure`:
        # Inflamación/Tiroides/Glucosa+eAG) pueden ser más altos que el
        # hueco disponible sin redimensionar la ventana a mano. Dejar que
        # Tkinter comprimiera la figura sin límite al tamaño del contenedor
        # (como el caso de arriba) recortaba los recuadros de tendencia de
        # cada panel: se dibujan con un desplazamiento fijo en puntos
        # (`charts._draw_info_box`) que no se reescala si la figura se
        # comprime — el margen que le reserva `comparison_figure` deja de
        # ser suficiente por debajo de `MIN_SHRINK_RATIO`. Aquí el ancho
        # se sigue ajustando siempre al contenedor; el alto se reduce hasta
        # ese límite si la ventana no está maximizada (para no necesitar
        # scroll si con un poco menos ya cabe entero, reduciendo el gráfico
        # sin reducir el tamaño del texto — el texto de los ejes/leyenda no
        # cambia de tamaño, solo el propio gráfico), y solo por debajo de
        # ese límite aparece scroll vertical.
        # Verificado visualmente (guardando la figura a distintos ratios con
        # matplotlib en modo Agg, sin Tkinter): por debajo de ~0.9 el
        # recuadro de tendencia del panel superior empieza a solaparse con
        # el título del panel siguiente (el hueco entre paneles, `hspace`,
        # es una fracción del alto de cada panel, no un tamaño absoluto —
        # se encoge más rápido que el margen inferior). 0.95 deja margen de
        # sobra.
        MIN_SHRINK_RATIO = 0.95
        scroll = tk.Canvas(container, highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient="vertical", command=scroll.yview)
        scroll.configure(yscrollcommand=vsb.set)
        scroll.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        fig_canvas = FigureCanvasTkAgg(fig, master=scroll)
        widget = fig_canvas.get_tk_widget()
        window_id = scroll.create_window((0, 0), window=widget, anchor="nw")
        _, design_height_in = fig.get_size_inches()
        min_height_in = design_height_in * MIN_SHRINK_RATIO
        dpi = fig.get_dpi()

        def _redraw(_event=None):
            width_in = max(scroll.winfo_width(), 1) / dpi
            available_height_in = max(scroll.winfo_height(), 1) / dpi
            height_in = (
                design_height_in if available_height_in >= design_height_in
                else max(min_height_in, available_height_in)
            )
            fig.set_size_inches(width_in, height_in)
            fig_canvas.draw()
            # Hay que fijar también el alto del item, no solo el ancho: sin
            # esto, el widget se queda con el alto "nativo" del tamaño de
            # diseño de la figura (el que tenía al crear `FigureCanvasTkAgg`)
            # y `bbox("all")` no refleja nunca el achicado.
            scroll.itemconfigure(window_id, width=int(width_in * dpi), height=int(height_in * dpi))
            scroll.configure(scrollregion=scroll.bbox("all"))

        scroll.bind("<Configure>", _redraw)
        scroll.after(0, _redraw)

        def _on_mousewheel(event):
            scroll.yview_scroll(int(-1 * (event.delta / 120)), "units")

        scroll.bind("<Enter>", lambda _e: scroll.bind_all("<MouseWheel>", _on_mousewheel))
        scroll.bind("<Leave>", lambda _e: scroll.unbind_all("<MouseWheel>"))

        self._attach_hover(fig)

    def _attach_hover(self, fig) -> None:
        if self._active_cursor is not None:
            self._active_cursor.remove()
            self._active_cursor = None
        scatters = [c for ax in fig.axes for c in ax.collections if hasattr(c, "analitix_series")]
        if not scatters:
            return
        cursor = mplcursors.cursor(scatters, hover=True)

        @cursor.connect("add")
        def _on_add(sel):
            item = sel.artist.analitix_series[sel.index]
            fecha = (item.get("fecha") or "")[:10]
            unit = item.get("unit") or ""
            lab = f"\n{item['lab']}" if item.get("lab") else ""
            sel.annotation.set_text(f"{fecha}\n{item['value_num']:g} {unit}".strip() + lab)

        self._active_cursor = cursor

    # -- Exportar ---------------------------------------------------------
    def _build_tab_exportar(self) -> None:
        frame = self.tab_exportar
        ttk.Label(
            frame, text="Exporta todos los resultados del paciente seleccionado.", font=("Segoe UI", 11)
        ).pack(anchor="w", padx=PAD, pady=PAD)
        boton_excel = ttk.Button(
            frame, text="Exportar a Excel...", bootstyle="success", command=lambda: self._export("xlsx")
        )
        boton_excel.pack(anchor="w", padx=PAD, pady=5)
        boton_csv = ttk.Button(
            frame, text="Exportar a CSV...", bootstyle="success-outline", command=lambda: self._export("csv")
        )
        boton_csv.pack(anchor="w", padx=PAD, pady=5)
        self._same_width(boton_excel, boton_csv)
        ttk.Label(
            frame,
            text="Informes de seguimiento en PDF — en los dos: portada (logo, paciente, fecha), una "
            "página con los parámetros fuera de rango, otra con el resto, y un gráfico de evolución "
            "por cada parámetro fuera de rango o con cambio brusco (nunca para los normales, ni para "
            "uno con un solo valor registrado).",
            bootstyle="secondary", wraplength=700, justify="left",
        ).pack(anchor="w", padx=PAD, pady=(PAD, 0))
        boton_completo = ttk.Button(
            frame, text="Exportar informe completo (PDF)...", bootstyle="danger",
            command=lambda: self._export_pdf("completo"),
        )
        boton_completo.pack(anchor="w", padx=PAD, pady=(5, 0))
        ttk.Label(
            frame,
            text="Todos los parámetros del último informe.",
            bootstyle="secondary", wraplength=700, justify="left",
        ).pack(anchor="w", padx=PAD, pady=(0, 5))
        boton_alterados = ttk.Button(
            frame, text="Exportar informe de alterados (PDF)...", bootstyle="danger-outline",
            command=lambda: self._export_pdf("alterados"),
        )
        boton_alterados.pack(anchor="w", padx=PAD, pady=(5, 0))
        ttk.Label(
            frame,
            text="Solo los parámetros que alguna vez han estado fuera de rango en todo el histórico "
            "del paciente (aunque en el informe más reciente ya estén normales), con su valor más "
            "reciente.",
            bootstyle="secondary", wraplength=700, justify="left",
        ).pack(anchor="w", padx=PAD, pady=(0, 5))
        boton_personalizado = ttk.Button(
            frame, text="Informe PDF personalizado...", bootstyle="danger-outline",
            command=self._export_custom_pdf,
        )
        boton_personalizado.pack(anchor="w", padx=PAD, pady=(5, 0))
        self._same_width(boton_completo, boton_alterados, boton_personalizado)
        ttk.Label(
            frame,
            text="Eliges qué incluir: la tabla del último informe, \"Qué ha cambiado\", el mapa de "
            "calor, la evolución de los parámetros que quieras y los paneles clínicos (su resumen y "
            "sus gráficos). Lo alterado se marca con ⚠ para encontrarlo fácilmente.",
            bootstyle="secondary", wraplength=700, justify="left",
        ).pack(anchor="w", padx=PAD, pady=(0, 5))

    def _export_pdf(self, modo: str) -> None:
        """`modo="completo"`: todos los parámetros del último informe.
        `modo="alterados"`: solo los parámetros que alguna vez han estado
        fuera de rango en todo el histórico del paciente
        (`repository.list_canonical_tests`, columna `out_of_range`), con
        su valor más reciente — puede no coincidir con el último informe
        si ese parámetro concreto no se repitió en él. Estructura de
        página igual en los dos modos (ampliada 2026-09-21 en dos pasos:
        primero los dos modos, después esta estructura fija tras
        comprobar con una analítica real que ni siquiera la tabla de
        "alterados" cabía siempre en una sola página): portada, tabla de
        fuera de rango, tabla del resto, gráficos — ver
        `export.export_pdf`."""
        if self.current_patient_id is None:
            messagebox.showwarning("Sin paciente", "Selecciona antes un paciente en la pestaña Pacientes.", parent=self)
            return

        if modo == "completo":
            summary = get_latest_report_summary(self.con, self.current_patient_id)
            if not summary:
                messagebox.showinfo("Sin datos", "No hay resultados numéricos para exportar.", parent=self)
                return
            filas = self._classify_latest_report(summary)
            fecha = summary["fecha"]
            tipo_informe = "Informe completo"
        else:
            filas, fecha = self._build_altered_rows(self.current_patient_id)
            if not filas:
                messagebox.showinfo(
                    "Sin datos", "Este paciente no tiene ningún parámetro fuera de rango en su histórico.",
                    parent=self,
                )
                return
            tipo_informe = "Informe de parámetros alterados"

        # Gráficas nunca para los parámetros normales. En "completo" eso significa filtrar por
        # orden (0 = fuera de rango, 1 = cambio brusco); en "alterados" no hace falta filtrar nada
        # más, porque el propio criterio de selección de `_build_altered_rows` (alguna vez fuera de
        # rango en todo el histórico) ya es en sí mismo "una alteración importante" para cada fila,
        # esté o no dentro de rango en el snapshot actual. `export_pdf` descarta además cualquier
        # serie de un solo punto (nada que mostrar como evolución).
        filas_con_grafico = filas if modo == "alterados" else [f for f in filas if f["orden"] in (0, 1)]
        series_by_canonical_id = {
            f["canonical_id"]: get_series(self.con, f["canonical_id"], self.current_patient_id)
            for f in filas_con_grafico
        }
        labels = {f["canonical_id"]: f["raw_name"] for f in filas}
        patient = next((p for p in self.patients if p["id"] == self.current_patient_id), None)
        patient_name = patient["full_name"] if patient else "—"

        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[(".pdf", "*.pdf")], parent=self)
        if not path:
            return
        filtro = self._lab_filter_text()
        if filtro:
            tipo_informe = f"{tipo_informe} · {filtro}"  # portada y pie de cada página
        with self._progress("Generando informe PDF") as paso:
            paginas = export_pdf(
                patient_name, fecha, filas, series_by_canonical_id, labels, CAMBIO_BRUSCO_PCT, Path(path),
                tipo_informe=tipo_informe, min_points=self.min_points,
                on_progress=lambda n, t: paso(f"Escribiendo página {n} de {t}...", n, t),
            )
        messagebox.showinfo(
            "Exportado",
            f"Informe generado con {len(filas)} parámetros y {paginas} gráficos en:\n{path}",
            parent=self,
        )

    def _panel_pdf_pages(self, key: str, label: str) -> list:
        """Páginas de un panel clínico para el PDF personalizado: su
        resumen tal como se ve en pantalla y un gráfico por índice (o el
        gráfico combinado en Inflamación y Tiroides)."""
        paginas = [text_page(label, getattr(self, f"text_{key}_summary").get("1.0", "end"))]
        series = getattr(self, f"_{key}_series")
        if key in PDF_COMBINED_PANELS:
            combinadas = {nombre: series[k] for k, nombre in PDF_COMBINED_PANELS[key].items() if series.get(k)}
            if combinadas:
                paginas.append(self._comparison_figure(combinadas))
            return paginas
        for cid, nombre in getattr(self, f"_{key}_indices"):
            if cid and data_sufficiency(len(series.get(cid, [])), self.min_points) not in ("sin_datos", "un_punto"):
                paginas.append(self._evolution_figure(series[cid], nombre, cid))
        return paginas

    def _export_custom_pdf(self) -> None:
        """Exportar → "Informe PDF personalizado...": el usuario elige las
        secciones (tabla del último informe, "Qué ha cambiado", mapa de
        calor, evolución de parámetros concretos, paneles clínicos). ⚠ marca
        lo que alguna vez ha estado fuera de rango o por encima del umbral
        orientativo de un panel. Mismas reglas que la pantalla: filtro de
        laboratorios, aviso de pocos datos, RCV y rango personal si su
        interruptor está activo."""
        if self.current_patient_id is None:
            messagebox.showwarning("Sin paciente", "Selecciona antes un paciente en la pestaña Pacientes.", parent=self)
            return
        summary = get_latest_report_summary(self.con, self.current_patient_id)
        if not summary:
            messagebox.showinfo("Sin datos", "No hay resultados numéricos para exportar.", parent=self)
            return
        dialog, body = self._new_dialog("Informe PDF personalizado", resizable=True)
        ttk.Label(
            body,
            text="Elige qué incluir en el informe. ⚠ = alguna vez fuera de rango (o por encima del umbral "
            "orientativo de un panel). El informe usa los mismos laboratorios y ajustes que la pantalla.",
            wraplength=560, justify="left",
        ).pack(anchor="w", pady=(0, 6))

        secciones = ttk.Labelframe(body, text="Secciones", padding=6)
        secciones.pack(fill="x")
        alterado_ahora = any(f["flag_calc"] in ("alto", "bajo") for f in summary["resultados"])
        var_tabla = tk.BooleanVar(value=True)
        var_cambios = tk.BooleanVar(value=False)
        var_mapa = tk.BooleanVar(value=False)
        var_tension = tk.BooleanVar(value=False)
        lecturas_bp = list_bp_readings(self.con, self.current_patient_id)
        for var, texto in (
            (var_tabla, f"{'⚠ ' if alterado_ahora else ''}Tabla del último informe ({summary['fecha'][:10]})"),
            (var_cambios, "Qué ha cambiado (respecto al informe anterior)"),
        ):
            ttk.Checkbutton(secciones, text=texto, variable=var).pack(anchor="w", padx=8, pady=1)
        # Periodo de la tensión arterial en el informe: por defecto, el
        # último año (los mismos 365 días que el botón "Último año" del panel).
        hoy = dt.date.today()
        vars_bp_pdf = (tk.StringVar(value=(hoy - dt.timedelta(days=BP_RANGO_DIAS["1a"] - 1)).isoformat()),
                       tk.StringVar(value=hoy.isoformat()))
        if lecturas_bp:
            fila_tension = ttk.Frame(secciones)
            fila_tension.pack(anchor="w", padx=8, pady=1)
            ttk.Checkbutton(fila_tension, text="Tensión arterial (resumen y gráfico):", variable=var_tension).pack(
                side="left")
            for texto, var in (("desde", vars_bp_pdf[0]), ("hasta", vars_bp_pdf[1])):
                ttk.Label(fila_tension, text=texto).pack(side="left", padx=(8, 4))
                entrada = ttk.Entry(fila_tension, textvariable=var, width=11)
                self._restrict(entrada, r"[\d-]{0,10}")
                entrada.pack(side="left")
            ttk.Label(secciones, text="Fechas AAAA-MM-DD; en blanco, sin límite.", bootstyle="secondary").pack(
                anchor="w", padx=32)
        fila_mapa = ttk.Frame(secciones)
        fila_mapa.pack(anchor="w", padx=8, pady=1)
        ttk.Checkbutton(fila_mapa, text="Mapa de calor:", variable=var_mapa).pack(side="left")
        var_conjunto_mapa = tk.StringVar(value=HEATMAP_OUT_OF_RANGE)
        ttk.Combobox(
            fila_mapa, textvariable=var_conjunto_mapa, values=[HEATMAP_OUT_OF_RANGE, HEATMAP_ALL, *HEATMAP_SETS],
            state="readonly", width=40,
        ).pack(side="left", padx=(6, 0))

        parametros = ttk.Labelframe(body, text="Evolución de parámetros", padding=6)
        parametros.pack(fill="both", expand=True, pady=(6, 0))
        tests = [t for t in list_canonical_tests(self.con, self.current_patient_id) if t["num_points"] >= 2]
        lista = self._scrollable_frame(parametros)
        vars_tests = []
        for t in tests:
            var = tk.BooleanVar(value=False)
            vars_tests.append(var)
            ttk.Checkbutton(
                lista, text=f"{'⚠ ' if t['out_of_range'] else ''}{t['raw_name']} (n={t['num_points']})", variable=var,
            ).pack(anchor="w", padx=8, pady=1)

        paneles = ttk.Labelframe(body, text="Paneles clínicos (resumen y gráficos)", padding=6)
        paneles.pack(fill="x", pady=(6, 0))
        vars_paneles = {}
        for i, (key, label) in enumerate(PDF_PANELS):
            series = getattr(self, f"_{key}_series")
            alterado = any(p.get("flag_calc") in ("alto", "bajo") for s in series.values() for p in s)
            vars_paneles[key] = (tk.BooleanVar(value=False), label, alterado)
            ttk.Checkbutton(
                paneles, text=f"{'⚠ ' if alterado else ''}{label}", variable=vars_paneles[key][0],
                state="normal" if series else "disabled",
            ).grid(row=i // 2, column=i % 2, sticky="w", padx=8, pady=1)

        graficos = ttk.Labelframe(body, text="Gráficos", padding=6)
        graficos.pack(fill="x", pady=(6, 0))
        var_por_pagina = tk.IntVar(value=1)
        # La opción de 3 por página queda desactivada: con los gráficos de
        # evolución (recuadro de notas) no caben más de 2 sin bajar de
        # `export._CHARTS_MIN_SCALE`. `export._flow_pages` sigue admitiéndola;
        # para recuperarla, añadir (3, "Tres por página, en vertical (menos hojas)").
        for valor, texto in ((1, "Uno por página, en horizontal (más detalle)"),
                             (2, "Dos por página, en vertical (menos hojas)")):
            ttk.Radiobutton(graficos, text=texto, variable=var_por_pagina, value=valor).pack(anchor="w", padx=8, pady=1)

        def _marcar_alterados() -> None:
            for t, var in zip(tests, vars_tests):
                var.set(bool(t["out_of_range"]))
            for var, _label, alterado in vars_paneles.values():
                var.set(alterado)

        def _desmarcar() -> None:
            for var in [var_tabla, var_cambios, var_mapa, var_tension, *vars_tests, *(v for v, _l, _a in vars_paneles.values())]:
                var.set(False)

        def _generar() -> None:
            seleccion = [t for t, var in zip(tests, vars_tests) if var.get()]
            elegidos = [(key, label) for key, (var, label, _a) in vars_paneles.items() if var.get()]
            if not (var_tabla.get() or var_cambios.get() or var_mapa.get() or var_tension.get() or seleccion
                    or elegidos):
                messagebox.showwarning("Informe personalizado", "Elige al menos una sección.", parent=dialog)
                return
            periodo_bp = None
            if var_tension.get():
                try:
                    periodo_bp = _check_period(*(v.get() for v in vars_bp_pdf)) or (None, None)
                except ValueError as exc:
                    messagebox.showwarning("Fechas no válidas", f"Revisa las fechas de la tensión arterial "
                                           f"(AAAA-MM-DD): {exc}.", parent=dialog)
                    return
            path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[(".pdf", "*.pdf")], parent=dialog)
            if not path:
                return
            tipo_informe = "Informe personalizado"
            filtro = self._lab_filter_text()
            if filtro:
                tipo_informe = f"{tipo_informe} · {filtro}"
            patient = next((p for p in self.patients if p["id"] == self.current_patient_id), None)
            # Barra de progreso: primero cada sección (gráficos y tablas),
            # después cada página escrita.
            pasos = (var_tabla.get() + var_cambios.get() + var_mapa.get() + (periodo_bp is not None)
                     + len(seleccion) + len(elegidos))
            total = 0
            with self._progress("Generando informe PDF", dialog) as paso:
                hechos = 0

                def avanza() -> None:
                    nonlocal hechos
                    hechos += 1
                    paso(f"Preparando secciones ({hechos} de {pasos})...", hechos, pasos)

                paginas = []
                if var_tabla.get():
                    filas = self._classify_latest_report(summary)
                    paginas.append(table_page(summary["fecha"], [f for f in filas if f["flag_calc"] in ("alto", "bajo")],
                                              CAMBIO_BRUSCO_PCT, "Parámetros alterados en la última analítica"))
                    paginas.append(table_page(summary["fecha"], [f for f in filas if f["flag_calc"] not in ("alto", "bajo")],
                                              CAMBIO_BRUSCO_PCT, "Resto de parámetros"))
                    avanza()
                if var_cambios.get():
                    medibles = [f for f in self._changes_rows(summary) if f["previous"] is not None
                                and (f["ref_low"] is not None or f["ref_high"] is not None)]
                    # Orden global de mayor a menor cambio antes de repartir en
                    # páginas (cada página conserva ese orden).
                    def _magnitud(f):
                        status = change_status(f["previous"], f["value"], f["ref_low"], f["ref_high"])
                        return abs(status[0]) if status else 0.0
                    medibles.sort(key=_magnitud, reverse=True)
                    titulo = f"Qué ha cambiado — último informe ({summary['fecha'][:10]})"
                    paginas.extend(_same_size([changes_figure(trozo, titulo + sufijo) for trozo, sufijo in _pages_of(medibles)]))
                    avanza()
                if var_mapa.get():
                    conjunto = var_conjunto_mapa.get()
                    paginas.extend(_same_size([heatmap_figure(trozo, conjunto + sufijo)
                                               for trozo, sufijo in _pages_of(self._heatmap_rows(conjunto))]))
                    avanza()
                for t in seleccion:
                    serie = get_series(self.con, t["canonical_id"], self.current_patient_id)
                    paginas.append(self._evolution_figure(serie, t["raw_name"], t["canonical_id"], with_personal=True))
                    avanza()
                if periodo_bp is not None:
                    # El periodo elegido manda sobre la ventana de años, como el
                    # intervalo del panel; el gráfico agrupa según su duración.
                    desde, hasta = periodo_bp
                    lecturas = [r for r in lecturas_bp if (desde is None or r["measured_at"][:10] >= desde)
                                and (hasta is None or r["measured_at"][:10] <= hasta)]
                    inicio = dt.date.fromisoformat(desde) if desde else None
                    fin = dt.date.fromisoformat(hasta) if hasta else hoy
                    titulo = f"Tensión arterial · {desde or 'inicio'} a {hasta or 'hoy'}"
                    paginas.append(text_page(titulo, bp_summary_text(lecturas)))
                    if lecturas or inicio is not None:
                        paginas.append(bp_figure(lecturas, titulo, dias=None if inicio is None else (fin - inicio).days + 1,
                                                 desde=inicio if inicio is not None and fin >= hoy else None))
                    avanza()
                for key, label in elegidos:
                    paginas.extend(self._panel_pdf_pages(key, label))
                    avanza()
                if paginas:
                    total = export_pages_pdf(
                        patient["full_name"] if patient else "—", summary["fecha"], paginas, Path(path),
                        tipo_informe=tipo_informe, graficos_por_pagina=var_por_pagina.get(),
                        on_progress=lambda n, t: paso(f"Escribiendo página {n} de {t}...", n, t),
                    )
            if not total:
                messagebox.showinfo("Informe personalizado", "Las secciones elegidas no tienen datos.", parent=dialog)
                return
            dialog.destroy()
            messagebox.showinfo("Exportado", f"Informe personalizado de {total} páginas en:\n{path}", parent=self)

        botones = ttk.Frame(body)
        botones.pack(fill="x", pady=(PAD, 0))
        boton_alterados = ttk.Button(botones, text="Marcar alterados", bootstyle="secondary-outline",
                                     command=_marcar_alterados)
        boton_alterados.pack(side="left")
        boton_ninguno = ttk.Button(botones, text="Desmarcar todo", bootstyle="secondary-outline", command=_desmarcar)
        boton_ninguno.pack(side="left", padx=(8, 0))
        self._same_width(boton_alterados, boton_ninguno)
        boton_cancelar = ttk.Button(botones, text="Cancelar", command=dialog.destroy)
        boton_cancelar.pack(side="right")
        boton_generar = ttk.Button(botones, text="Generar PDF...", bootstyle="primary", command=_generar)
        boton_generar.pack(side="right", padx=(0, 8))
        self._same_width(boton_cancelar, boton_generar)
        self._center_dialog(dialog)

    def _build_altered_rows(self, patient_id: int) -> tuple[list[dict], str | None]:
        """Una fila por cada `canonical_id` que alguna vez ha estado fuera
        de rango en todo el histórico del paciente
        (`list_canonical_tests`, columna `out_of_range` — ya calculada
        sobre **todos** los informes, no solo el más reciente), con su
        valor más reciente (el último punto de `get_series`, no
        necesariamente del informe más reciente del paciente en general:
        puede que ese parámetro concreto no se repitiera en él). Para el
        informe PDF "solo alterados"."""
        altered_ids = [t["canonical_id"] for t in list_canonical_tests(self.con, patient_id) if t["out_of_range"]]
        filas = []
        fecha_max = None
        for canonical_id in altered_ids:
            serie = get_series(self.con, canonical_id, patient_id)
            if not serie:
                continue
            ultimo = serie[-1]
            valor_anterior = serie[-2]["value_num"] if len(serie) >= 2 else None
            filas.append(self._enrich_with_variation({
                "canonical_id": canonical_id, "raw_name": ultimo["raw_name"], "value_num": ultimo["value_num"],
                "unit": ultimo["unit"], "ref_low": ultimo["ref_low"], "ref_high": ultimo["ref_high"],
                "flag_calc": ultimo["flag_calc"], "valor_anterior": valor_anterior,
            }))
            if fecha_max is None or ultimo["fecha"] > fecha_max:
                fecha_max = ultimo["fecha"]
        filas.sort(key=lambda f: (f["orden"], f["raw_name"] or ""))
        return filas, fecha_max

    def _export(self, kind: str) -> None:
        if self.current_patient_id is None:
            messagebox.showwarning("Sin paciente", "Selecciona antes un paciente en la pestaña Pacientes.", parent=self)
            return
        rows = get_all_results(self.con, self.current_patient_id)
        if not rows:
            messagebox.showinfo("Sin datos", "No hay resultados para exportar.", parent=self)
            return
        ext = ".xlsx" if kind == "xlsx" else ".csv"
        path = filedialog.asksaveasfilename(defaultextension=ext, filetypes=[(ext, f"*{ext}")], parent=self)
        if not path:
            return
        if kind == "xlsx":
            export_excel(rows, Path(path))
        else:
            export_csv(rows, Path(path))
        messagebox.showinfo("Exportado", f"Se han exportado {len(rows)} filas a:\n{path}", parent=self)

    # -- Explorador BD --------------------------------------------------------
    def _build_tab_explorador(self) -> None:
        frame = self.tab_explorador
        top = ttk.Frame(frame)
        top.pack(fill="x", padx=PAD, pady=PAD)
        ttk.Label(top, text="Tabla:").pack(side="left")
        self.var_explorer_table = tk.StringVar(value=EXPLORABLE_TABLES[0])
        combo = ttk.Combobox(
            top, textvariable=self.var_explorer_table, values=list(EXPLORABLE_TABLES),
            state="readonly", width=20,
        )
        combo.pack(side="left", padx=(6, 0))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_explorador())
        ttk.Button(top, text="Actualizar", command=self._refresh_explorador).pack(side="left", padx=(8, 0))
        self.var_explorer_count = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.var_explorer_count, bootstyle="secondary").pack(side="right")

        ttk.Label(
            frame,
            text="Solo lectura: sirve para comprobar qué datos hay guardados exactamente, "
            "no se puede editar nada desde aquí.",
            bootstyle="secondary",
        ).pack(anchor="w", padx=PAD)

        container = ttk.Frame(frame)
        container.pack(fill="both", expand=True, padx=PAD, pady=(4, PAD))
        self.tree_explorer = ttk.Treeview(container, show="headings")
        vsb = ttk.Scrollbar(container, orient="vertical", command=self.tree_explorer.yview)
        hsb = ttk.Scrollbar(container, orient="horizontal", command=self.tree_explorer.xview)
        self.tree_explorer.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree_explorer.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        self._refresh_explorador()

    def _refresh_explorador(self) -> None:
        table = self.var_explorer_table.get()
        columns, rows = get_table_rows(self.con, table)
        tree = self.tree_explorer
        tree.delete(*tree.get_children())
        tree["columns"] = columns
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=120, stretch=False, anchor="w")
        for row in rows:
            values = ["" if v is None else str(v) for v in row]
            tree.insert("", "end", values=values)
        self.var_explorer_count.set(f"{len(rows)} filas")

    # -- Normalizar pruebas ---------------------------------------------------
    def _build_tab_catalogo(self) -> None:
        frame = self.tab_catalogo
        ttk.Label(
            frame,
            text="El laboratorio a veces abrevia o renombra ligeramente el nombre de una misma "
            "prueba entre informes, y aparecen como pruebas distintas. Selecciona dos o más filas "
            "que sean en realidad la misma determinación y fusiónalas. No se permite fusionar dos "
            "pruebas que aparecen juntas en un mismo informe (el laboratorio las midió a la vez, "
            "p. ej. glucosa en sangre y en orina).",
            bootstyle="secondary", wraplength=900,
        ).pack(anchor="w", padx=PAD, pady=PAD)

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=PAD, pady=(0, 6))
        boton_actualizar = ttk.Button(top, text="Actualizar", command=self._refresh_catalogo)
        boton_actualizar.pack(side="left")
        boton_fusionar = ttk.Button(
            top, text="Fusionar seleccionadas...", bootstyle="primary", command=self._merge_selected_groups
        )
        boton_fusionar.pack(side="left", padx=(8, 0))
        self._same_width(boton_actualizar, boton_fusionar)

        columns = ("nombre", "canonical_id", "num_results", "labs", "variantes")
        # `show="tree headings"`: cada prueba se despliega (▸) en una fila por
        # nombre y laboratorio, para ver qué nombre usa cada laboratorio.
        self.tree_catalogo = ttk.Treeview(
            frame, columns=columns, show="tree headings", selectmode="extended", bootstyle="primary"
        )
        self._checkbox_tree(self.tree_catalogo)
        for col, label, width in zip(
            columns,
            ("Nombre más frecuente", "Identificador interno", "Nº resultados", "Laboratorios",
             "Variantes de nombre vistas"),
            (220, 160, 100, 160, 380),
        ):
            self.tree_catalogo.heading(col, text=label)
            self.tree_catalogo.column(col, width=width)
        _make_sortable(self.tree_catalogo, numeric_columns={"num_results"})
        self.tree_catalogo.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))

        self._refresh_catalogo()

    def _refresh_catalogo(self) -> None:
        self._catalog_groups = list_canonical_groups(self.con)
        tree = self.tree_catalogo
        tree.delete(*tree.get_children())
        for g in self._catalog_groups:
            nombre = g["raw_names"][0][0]
            variantes = ", ".join(f"{name} ({n})" for name, n in g["raw_names"])
            tree.insert(
                "", "end", iid=g["canonical_id"],
                values=(nombre, g["canonical_id"], g["num_results"], ", ".join(g["labs"]), variantes),
            )
            for name, lab, n in g["variants"]:
                tree.insert(g["canonical_id"], "end", values=(f"    {name}", "", n, lab or LAB_UNKNOWN, ""))
        tree._resort()
        self._sync_checks(tree)

    def _merge_selected_groups(self) -> None:
        # Una fila de detalle (nombre + laboratorio) cuenta como su prueba.
        tree = self.tree_catalogo
        selected_ids = list(dict.fromkeys(tree.parent(iid) or iid for iid in tree.selection()))
        if len(selected_ids) < 2:
            messagebox.showwarning(
                "Selecciona al menos 2", "Marca dos o más filas que sean la misma prueba para fusionarlas.",
                parent=self,
            )
            return
        blocked, warnings = merge_check(self.con, list(selected_ids))
        if blocked:
            messagebox.showerror("No se pueden fusionar", "\n\n".join(blocked), parent=self)
            return
        if warnings and not messagebox.askyesno(
            "Revisar antes de fusionar",
            "\n\n".join(warnings) + "\n\nPuede que no sean la misma prueba. ¿Fusionar de todos modos?",
            icon="warning", parent=self,
        ):
            return
        selected_groups = [g for g in self._catalog_groups if g["canonical_id"] in selected_ids]
        target_id = self._ask_merge_target(selected_groups)
        if target_id is None:
            return
        updated = merge_canonical_ids(self.con, list(selected_ids), target_id)
        logger.info("Fusionadas pruebas %s en %s (%d resultados actualizados)", selected_ids, target_id, updated)
        self._refresh_catalogo()
        self._refresh_test_lists()
        self.combo_manual_nombre["values"] = list_known_test_names(self.con)
        messagebox.showinfo(
            "Analitix", f"Fusionadas {len(selected_ids)} variantes ({updated} resultados actualizados).",
            parent=self,
        )

    def _ask_merge_target(self, groups: list[dict]) -> str | None:
        """Pequeño diálogo modal para elegir, de entre las filas seleccionadas
        para fusionar, cuál se queda como identificador interno; el resto
        pasa a valer lo mismo. Devuelve `None` si se cancela."""
        dialog, body = self._new_dialog("Elegir nombre a conservar")
        ttk.Label(
            body, text="¿Cuál de estas es la prueba a conservar? El resto se fundirá en ella."
        ).pack(anchor="w", pady=(0, 6))
        default_id = max(groups, key=lambda g: g["num_results"])["canonical_id"]
        choice = tk.StringVar(value=default_id)
        for g in groups:
            nombre = g["raw_names"][0][0]
            ttk.Radiobutton(
                body, text=f"{nombre}  ({g['num_results']} resultados, id: {g['canonical_id']})",
                variable=choice, value=g["canonical_id"],
            ).pack(anchor="w", padx=8, pady=2)
        result: dict[str, str | None] = {"value": None}

        def _confirm() -> None:
            result["value"] = choice.get()
            dialog.destroy()

        botones = ttk.Frame(body)
        botones.pack(fill="x", pady=(PAD, 0))
        boton_cancelar = ttk.Button(botones, text="Cancelar", command=dialog.destroy)
        boton_cancelar.pack(side="right")
        boton_ok = ttk.Button(botones, text="Fusionar", bootstyle="primary", command=_confirm)
        boton_ok.pack(side="right", padx=(0, 8))
        self._same_width(boton_cancelar, boton_ok)
        self._center_dialog(dialog)
        self.wait_window(dialog)
        return result["value"]

    # -- Configuración ------------------------------------------------------
    def _build_tab_config(self) -> None:
        sub = ttk.Notebook(self.tab_config)
        sub.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        tab_general = ttk.Frame(sub)
        tab_seguridad = ttk.Frame(sub)
        tab_datos = ttk.Frame(sub)
        tab_estadisticas = ttk.Frame(sub)
        tab_entrada = ttk.Frame(sub)
        sub.add(tab_general, text="General")
        sub.add(tab_entrada, text="Entrada manual")
        sub.add(tab_seguridad, text="Seguridad")
        sub.add(tab_datos, text="Datos")
        sub.add(tab_estadisticas, text="Estadísticas")

        self._build_subtab_general(tab_general)
        self._build_subtab_entrada(tab_entrada)
        self._build_subtab_seguridad(tab_seguridad)
        self._build_subtab_datos(tab_datos)
        self._build_subtab_estadisticas(tab_estadisticas)
        self._refresh_stats()

    def _build_subtab_general(self, frame: ttk.Frame) -> None:
        carpeta = ttk.Labelframe(frame, text="Carpeta de informes", padding=PAD)
        carpeta.pack(fill="x", padx=PAD, pady=(PAD, 6))
        ttk.Entry(carpeta, textvariable=self.var_reports_dir, state="readonly").pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(carpeta, text="Cambiar carpeta...", command=self._change_reports_dir).pack(
            side="left", padx=(8, 0)
        )

        graficos = ttk.Labelframe(frame, text="Gráficos", padding=PAD)
        graficos.pack(fill="x", padx=PAD, pady=6)
        ttk.Label(
            graficos,
            text="Nº mínimo de analíticas para que una evolución se considere representativa. Se "
            "aplica a todos los gráficos de evolución (Evolución, Comparativa, paneles clínicos y "
            "PDF): por debajo se dibujan con un aviso, y con una sola analítica no se dibuja el "
            "gráfico, solo el valor. En Evolución/Comparativa, esas pruebas se agrupan además al "
            "final de la lista. Los cambios se ven al volver a abrir el gráfico:",
            wraplength=700,
        ).pack(anchor="w")
        fila_min_puntos = ttk.Frame(graficos)
        fila_min_puntos.pack(anchor="w", pady=(6, 0))
        self.var_min_points = tk.IntVar(value=self.min_points)
        ttk.Spinbox(fila_min_puntos, from_=2, to=20, textvariable=self.var_min_points, width=5).pack(side="left")
        ttk.Button(fila_min_puntos, text="Guardar", command=self._change_min_points).pack(side="left", padx=(8, 0))

        actualizaciones = ttk.Labelframe(frame, text="Actualizaciones", padding=PAD)
        actualizaciones.pack(fill="x", padx=PAD, pady=6)
        ttk.Label(
            actualizaciones,
            text="Es la única conexión a internet de Analitix: consulta en GitHub el número de la "
            "última versión publicada. No envía ningún dato tuyo ni de la base de datos.",
            wraplength=700,
        ).pack(anchor="w")
        fila_actualizaciones = ttk.Frame(actualizaciones)
        fila_actualizaciones.pack(anchor="w", pady=(6, 0))
        self.var_check_updates = tk.BooleanVar(
            value=get_setting(self.con, "check_updates_on_start", "0") == "1"
        )
        ttk.Checkbutton(
            fila_actualizaciones, text="Comprobar al iniciar", variable=self.var_check_updates,
            bootstyle="round-toggle",
            command=lambda: set_setting(
                self.con, "check_updates_on_start", "1" if self.var_check_updates.get() else "0"
            ),
        ).pack(side="left")
        ttk.Button(
            fila_actualizaciones, text="Buscar ahora", command=lambda: self._check_updates(manual=True)
        ).pack(side="left", padx=(12, 0))

    def _build_subtab_seguridad(self, frame: ttk.Frame) -> None:
        seguridad = ttk.Labelframe(frame, text="Seguridad", padding=PAD)
        seguridad.pack(fill="x", padx=PAD, pady=(PAD, 6))
        ttk.Label(
            seguridad, text="La base de datos está cifrada (SQLCipher) con la contraseña maestra."
        ).pack(anchor="w")
        ttk.Button(
            seguridad, text="Cambiar contraseña...", bootstyle="warning", command=self._change_password
        ).pack(anchor="w", pady=(8, 0))

    def _build_subtab_datos(self, frame: ttk.Frame) -> None:
        datos = ttk.Labelframe(frame, text="Vaciar la base de datos", padding=PAD)
        datos.pack(fill="x", padx=PAD, pady=(PAD, 6))
        ttk.Label(
            datos,
            text="Borra todos los pacientes, informes y resultados (irreversible). "
            "Los PDF de la carpeta de informes no se tocan: puedes volver a importarlos después.",
            wraplength=700,
        ).pack(anchor="w")
        ttk.Button(
            datos, text="Vaciar toda la base de datos...", bootstyle="danger",
            command=self._delete_all_data,
        ).pack(anchor="w", pady=(8, 0))

        huerfanos = ttk.Labelframe(frame, text="Informes huérfanos", padding=PAD)
        huerfanos.pack(fill="both", expand=True, padx=PAD, pady=6)
        ttk.Label(
            huerfanos,
            text="Informes sin ningún resultado, o cuyo PDF ya no está en la carpeta de informes "
            "(se eliminó, no se renombró: un PDF renombrado se sigue reconociendo solo). No "
            "aportan datos a la evolución/comparativa; puedes borrarlos sin perder nada útil.",
            wraplength=700,
        ).pack(anchor="w")
        top_huerfanos = ttk.Frame(huerfanos)
        top_huerfanos.pack(fill="x", pady=(8, 4))
        boton_actualizar = ttk.Button(top_huerfanos, text="Actualizar", command=self._refresh_orphans)
        boton_actualizar.pack(side="left")
        boton_eliminar = ttk.Button(
            top_huerfanos, text="Eliminar seleccionados...", bootstyle="danger-outline",
            command=self._delete_selected_orphans,
        )
        boton_eliminar.pack(side="left", padx=(8, 0))
        self._same_width(boton_actualizar, boton_eliminar)
        columns = ("full_name", "fecha", "source_file", "num_results", "missing_file")
        self.tree_orphans = ttk.Treeview(
            huerfanos, columns=columns, show="headings", selectmode="extended", height=6,
            bootstyle="primary",
        )
        for col, label, width in zip(
            columns,
            ("Paciente", "Fecha", "Fichero", "Nº resultados", "¿PDF ya no existe?"),
            (200, 90, 260, 90, 110),
        ):
            self.tree_orphans.heading(col, text=label)
            self.tree_orphans.column(col, width=width)
        self.tree_orphans.pack(fill="both", expand=True, pady=(0, 4))
        self._checkbox_tree(self.tree_orphans)
        self._refresh_orphans()

    def _refresh_orphans(self) -> None:
        existing_filenames = known_pdf_filenames(self.reports_dir)
        self._orphan_reports = list_orphan_reports(self.con, existing_filenames)
        tree = self.tree_orphans
        tree.delete(*tree.get_children())
        for r in self._orphan_reports:
            tree.insert(
                "", "end", iid=str(r["id"]),
                values=(
                    r["full_name"], r["fecha"] or "", r["source_file"], r["num_results"],
                    "Sí" if r["missing_file"] else "No",
                ),
            )
        self._sync_checks(tree)

    def _delete_selected_orphans(self) -> None:
        selected_ids = [int(iid) for iid in self.tree_orphans.selection()]
        if not selected_ids:
            messagebox.showwarning(
                "Selecciona al menos uno", "Marca los informes a eliminar.", parent=self
            )
            return
        if not messagebox.askyesno(
            "Eliminar informes",
            f"¿Eliminar {len(selected_ids)} informe(s) y sus resultados? Esta acción no se puede "
            "deshacer. Los PDF de la carpeta no se tocan.",
            parent=self,
        ):
            return
        logger.info("Eliminando informes huérfanos id=%s", selected_ids)
        deleted = delete_reports(self.con, selected_ids)
        self._refresh_orphans()
        self._refresh_patients()
        self._refresh_stats()
        messagebox.showinfo("Analitix", f"Eliminados {deleted} informe(s).", parent=self)

    def _delete_all_data(self) -> None:
        if not messagebox.askyesno(
            "Vaciar la base de datos",
            "Esto borra TODOS los pacientes, informes y resultados de la base de datos. "
            "No se puede deshacer.\n\n¿Continuar?",
            parent=self,
            icon="warning",
        ):
            return
        confirm = simpledialog.askstring(
            "Confirmación", 'Escribe BORRAR (en mayúsculas) para confirmar:', parent=self
        )
        if confirm != "BORRAR":
            messagebox.showinfo("Analitix", "Cancelado: no se ha borrado nada.", parent=self)
            return
        logger.warning("Vaciando toda la base de datos (acción del usuario)")
        delete_all_data(self.con)
        self.current_patient_id = None
        self._refresh_patients()
        self._refresh_stats()
        messagebox.showinfo("Analitix", "Base de datos vaciada.", parent=self)

    def _build_subtab_estadisticas(self, frame: ttk.Frame) -> None:
        avisos = ttk.Labelframe(frame, text="Avisos — informes pendientes de revisión", padding=PAD)
        avisos.pack(fill="x", padx=PAD, pady=(PAD, 6))
        ttk.Label(
            avisos,
            text="Informes en los que no se reconoció el paciente o no se extrajo ningún "
            "resultado (posible PDF de un formato/laboratorio distinto):",
            wraplength=700,
        ).pack(anchor="w")
        self.list_review = tk.Listbox(avisos, height=4, relief="flat")
        self.list_review.pack(fill="x", pady=(6, 0))
        self._style_plain_widget(self.list_review)

        stats_frame = ttk.Labelframe(frame, text="Estadísticas de la base de datos", padding=PAD)
        stats_frame.pack(fill="both", expand=True, padx=PAD, pady=6)
        self.stats_labels: dict[str, tk.StringVar] = {}
        for row, (key, label) in enumerate(STATS_LABELS):
            var = tk.StringVar(value="—")
            self.stats_labels[key] = var
            ttk.Label(stats_frame, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Label(stats_frame, textvariable=var, font=("Segoe UI", 10, "bold")).grid(
                row=row, column=1, sticky="w", padx=(10, 0), pady=2
            )
        self.var_db_size = tk.StringVar(value="—")
        ttk.Label(stats_frame, text="Tamaño del fichero de base de datos:").grid(
            row=len(STATS_LABELS), column=0, sticky="w", pady=2
        )
        ttk.Label(stats_frame, textvariable=self.var_db_size, font=("Segoe UI", 10, "bold")).grid(
            row=len(STATS_LABELS), column=1, sticky="w", padx=(10, 0), pady=2
        )
        # Dónde está la base de datos, para que el usuario pueda copiarla como
        # copia de seguridad (en el ejecutable instalado no está junto al
        # programa, ver `config.DATA_DIR`).
        ttk.Label(stats_frame, text="Ubicación de la base de datos:").grid(
            row=len(STATS_LABELS) + 1, column=0, sticky="w", pady=2
        )
        ttk.Label(stats_frame, text=str(DB_PATH), font=("Segoe UI", 10, "bold")).grid(
            row=len(STATS_LABELS) + 1, column=1, sticky="w", padx=(10, 0), pady=2
        )
        buttons = ttk.Frame(stats_frame)
        buttons.grid(row=len(STATS_LABELS) + 2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(buttons, text="Actualizar", command=self._refresh_stats).pack(side="left")
        if sys.platform == "win32":
            ttk.Button(
                buttons, text="Abrir carpeta de datos", bootstyle="secondary-outline",
                command=lambda: os.startfile(DB_PATH.parent),  # noqa: S606 - carpeta propia de la app
            ).pack(side="left", padx=(8, 0))
        if FROZEN:
            ttk.Button(
                buttons, text="Cambiar ubicación de los datos...", bootstyle="warning-outline",
                command=self._change_data_home,
            ).pack(side="left", padx=(8, 0))
        self._same_width(*buttons.winfo_children())
        self._refresh_stats()

    def _change_data_home(self) -> None:
        """Solo en el ejecutable instalado: lleva la carpeta "Analitix" (base
        de datos, alias, log y PDF) a otra ubicación elegida por el usuario.
        Copia sin borrar el origen, apunta la nueva en el registro (como el
        instalador, `config.set_installed_home_dir`) y reinicia la app."""
        chosen = filedialog.askdirectory(
            title="Elige dónde guardar la carpeta Analitix", initialdir=str(PROJECT_ROOT.parent), parent=self
        )
        if not chosen:
            return
        new_home = Path(chosen) / "Analitix"
        if new_home.resolve() == PROJECT_ROOT.resolve():
            messagebox.showinfo("Analitix", "Los datos ya están en esa carpeta.", parent=self)
            return
        existing = (new_home / "data" / "analitix.db").exists()
        if existing:
            question = (
                f"Ya hay datos de Analitix en:\n{new_home}\n\nSe usarán esos datos (con la contraseña con la "
                f"que se crearon). Los actuales se quedan en:\n{PROJECT_ROOT}\n\n"
                "Analitix se reiniciará. ¿Continuar?"
            )
        else:
            question = (
                f"Se copiarán tu base de datos, tus alias y tus PDF a:\n{new_home}\n\nLos originales se quedan "
                f"en:\n{PROJECT_ROOT}\nhasta que los borres tú, cuando compruebes que todo está bien.\n\n"
                "Analitix se reiniciará. ¿Continuar?"
            )
        if not messagebox.askyesno("Cambiar ubicación de los datos", question, parent=self):
            return
        try:
            if not existing:
                # La carpeta de PDF solo se mueve con los datos si era la de
                # siempre; una elegida a mano por el usuario se respeta.
                if self.reports_dir.resolve() == REPORTS_DIR.resolve():
                    set_setting(self.con, "reports_dir", str(new_home / "informes_analiticas"))
                self.con.commit()
                copy_home(PROJECT_ROOT, new_home)
            set_installed_home_dir(new_home)
        except OSError as exc:
            logger.exception("No se pudo cambiar la ubicación de los datos")
            messagebox.showerror("Analitix", f"No se pudo cambiar la ubicación:\n{exc}", parent=self)
            return
        logger.info("Ubicación de los datos cambiada a %s", new_home)
        subprocess.Popen([sys.executable])  # noqa: S603 - vuelve a abrir el propio ejecutable
        self.destroy()

    def _change_reports_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=str(self.reports_dir), parent=self)
        if not chosen:
            return
        self.reports_dir = Path(chosen)
        self.var_reports_dir.set(str(self.reports_dir))
        set_setting(self.con, "reports_dir", str(self.reports_dir))
        messagebox.showinfo("Analitix", "Carpeta actualizada.", parent=self)

    def _bp_limits(self) -> dict[str, tuple[int, int]]:
        """Límites de plausibilidad de la tensión arterial (Configuración →
        Entrada manual, ajuste `bp_limits`); los de por defecto si no hay o
        si el ajuste guardado no es válido."""
        try:
            return check_bp_limits(json.loads(get_setting(self.con, "bp_limits", "") or "{}"))
        except (ValueError, TypeError):
            return dict(BP_DEFAULT_LIMITS)

    def _build_subtab_entrada(self, frame: ttk.Frame) -> None:
        """Límites para validar la entrada manual de tensión arterial."""
        caja = ttk.Labelframe(frame, text="Límites de la tensión arterial", padding=PAD)
        caja.pack(fill="x", padx=PAD, pady=PAD)
        ttk.Label(
            caja,
            text="Al guardar o importar una medición de tensión arterial, los valores fuera de estos límites se "
            "rechazan como probable error de tecleo o de columna. No son valores normales ni objetivos de "
            "salud: solo cazan errores evidentes (por ejemplo 18 en vez de 180). Cada límite se puede "
            "ajustar dentro del margen permitido que se indica a la derecha.",
            bootstyle="secondary", wraplength=760, justify="left",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        ttk.Label(caja, text="Mínimo").grid(row=1, column=1)
        ttk.Label(caja, text="Máximo").grid(row=1, column=2)
        actuales = self._bp_limits()
        self.vars_bp_limits = {}
        for fila, (clave, (tope_min, tope_max)) in enumerate(BP_ABSOLUTE_LIMITS.items(), start=2):
            unidad = "lpm" if clave == "pulse" else "mmHg"
            ttk.Label(caja, text=f"{BP_LIMIT_NAMES[clave].capitalize()} ({unidad}):").grid(
                row=fila, column=0, sticky="w", pady=2)
            par = (tk.IntVar(value=actuales[clave][0]), tk.IntVar(value=actuales[clave][1]))
            for col, var in enumerate(par, start=1):
                caja_num = ttk.Spinbox(caja, from_=tope_min, to=tope_max, textvariable=var, width=6)
                self._restrict(caja_num, r"\d{0,3}")
                caja_num.grid(row=fila, column=col, padx=6, pady=2)
            ttk.Label(caja, text=f"permitido: {tope_min} – {tope_max}", bootstyle="secondary").grid(
                row=fila, column=3, sticky="w", padx=(8, 0))
            self.vars_bp_limits[clave] = par
        botones = ttk.Frame(caja)
        botones.grid(row=len(BP_ABSOLUTE_LIMITS) + 2, column=0, columnspan=4, sticky="w", pady=(10, 0))
        guardar = ttk.Button(botones, text="Guardar límites", bootstyle="primary", command=self._save_bp_limits)
        guardar.pack(side="left")
        por_defecto = ttk.Button(botones, text="Valores por defecto", bootstyle="secondary-outline",
                                 command=self._reset_bp_limits)
        por_defecto.pack(side="left", padx=(8, 0))
        self._same_width(guardar, por_defecto)

    def _save_bp_limits(self) -> None:
        try:
            limites = check_bp_limits({k: (a.get(), b.get()) for k, (a, b) in self.vars_bp_limits.items()})
        except (ValueError, tk.TclError) as exc:
            texto = str(exc) if isinstance(exc, ValueError) else "escribe los límites como números enteros"
            messagebox.showwarning("Límites no válidos", texto[:1].upper() + texto[1:] + ".", parent=self)
            return
        set_setting(self.con, "bp_limits", json.dumps({k: list(v) for k, v in limites.items()}))
        messagebox.showinfo("Analitix", "Límites guardados.", parent=self)

    def _reset_bp_limits(self) -> None:
        for clave, (minimo, maximo) in BP_DEFAULT_LIMITS.items():
            self.vars_bp_limits[clave][0].set(minimo)
            self.vars_bp_limits[clave][1].set(maximo)
        self._save_bp_limits()

    def _change_min_points(self) -> None:
        self.min_points = max(2, self.var_min_points.get())
        self.var_min_points.set(self.min_points)
        set_setting(self.con, "min_points_evolucion", str(self.min_points))
        self._refresh_test_lists()
        messagebox.showinfo("Analitix", "Preferencia guardada.", parent=self)

    def _change_password(self) -> None:
        new_pw = simpledialog.askstring("Cambiar contraseña", "Nueva contraseña:", show="*", parent=self)
        if not new_pw:
            return
        confirm = simpledialog.askstring("Cambiar contraseña", "Repite la nueva contraseña:", show="*", parent=self)
        if confirm != new_pw:
            messagebox.showerror("Analitix", "Las contraseñas no coinciden. No se ha cambiado nada.", parent=self)
            return
        try:
            rekey(self.con, new_pw)
            self.con.commit()
        except Exception as exc:  # noqa: BLE001 - se informa al usuario tal cual
            logger.exception("Error al cambiar la contraseña")
            messagebox.showerror("Analitix", f"No se pudo cambiar la contraseña:\n{exc}", parent=self)
            return
        logger.info("Contraseña de la base de datos cambiada")
        messagebox.showinfo("Analitix", "Contraseña actualizada correctamente.", parent=self)

    def _refresh_stats(self) -> None:
        stats = get_stats(self.con)
        for key, var in self.stats_labels.items():
            value = stats.get(key)
            var.set(str(value) if value not in (None, "") else "—")
        if DB_PATH.exists():
            size_kb = DB_PATH.stat().st_size / 1024
            self.var_db_size.set(f"{size_kb:,.0f} KB" if size_kb < 1024 else f"{size_kb / 1024:,.1f} MB")
        else:
            self.var_db_size.set("—")

        self.list_review.delete(0, "end")
        pending = list_files_needing_review(self.con)
        if not pending:
            self.list_review.insert("end", "  (ninguno)")
        for item in pending:
            self.list_review.insert("end", f"  {item['filename']} — {item['error_message']}")

    # -- utilidades de estilo -----------------------------------------------
    def _style_plain_widget(self, widget: tk.Widget) -> None:
        """Colorea un widget clásico de Tk (Listbox/Text) acorde al tema ttk activo."""
        colors = self.style.colors
        widget.configure(
            background=colors.inputbg, foreground=colors.inputfg,
            selectbackground=colors.primary, selectforeground=colors.selectfg,
            highlightthickness=0,
        )
