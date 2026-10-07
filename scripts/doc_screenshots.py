# ---------------------------------------------------------------------------
# Script: doc_screenshots.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-25
# Última actualización: 2026-10-06
# ---------------------------------------------------------------------------
"""Genera las capturas de pantalla y figuras de la documentación
(`docs/images/`) y el informe PDF de ejemplo (`docs/ejemplos/`) con un
paciente **ficticio** y datos inventados.

Uso (Windows, desde la raíz del proyecto, con la app instalada):

    venv\\Scripts\\python.exe scripts\\doc_screenshots.py

Nunca abre `data/analitix.db` ni ningún PDF real: crea una base de datos
cifrada temporal con "PACIENTE FICTICIO" y unas analíticas sintéticas de
tres laboratorios, abre la aplicación sobre ella, recorre las pantallas y
guarda cada captura. Las ventanas aparecen unos segundos en pantalla (hay
que traerlas al frente para capturarlas); no toques el ratón ni el teclado
mientras dura (~1 minuto). Al terminar borra la base de datos temporal. Las
figuras de la documentación técnica se generan directamente con matplotlib
(sin capturar pantalla).
"""
from __future__ import annotations

import hashlib
import random
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pdfplumber  # noqa: E402
from PIL import ImageGrab  # noqa: E402

from analitix import branding, db, gui, repository  # noqa: E402
from analitix import main as app_main  # noqa: E402
from analitix.charts import changes_figure, evolution_figure, heatmap_figure  # noqa: E402
from analitix.pdf_parser import compute_flag  # noqa: E402

OUT = ROOT / "docs" / "images"
PDF_EJEMPLO = ROOT / "docs" / "ejemplos" / "informe_alterados_ficticio.pdf"
WINDOW = (1280, 820)
DEMO_PASSWORD = "contraseña-de-ejemplo"

# Analíticas ficticias: (fecha, laboratorio). Tres laboratorios para que se
# vean la forma del punto por laboratorio y los nombres de prueba distintos.
REPORTS = [
    ("2020-02-11", "Synlab/Eurofins"), ("2020-09-22", "Synlab/Eurofins"), ("2021-03-09", "Synlab/Eurofins"),
    ("2021-10-14", "HUGTIP"), ("2022-05-18", "HUGTIP"), ("2022-12-01", "HUGTIP"),
    ("2023-06-20", "HUGTIP"), ("2024-01-16", "H. Mataró"), ("2024-06-04", "H. Mataró"),
    ("2024-11-19", "H. Mataró"), ("2025-03-11", "H. Mataró"), ("2025-10-07", "H. Mataró"),
    ("2026-02-03", "H. Mataró"), ("2026-04-14", "H. Mataró"),
]
LAB_INDEX = {"H. Mataró": 0, "Synlab/Eurofins": 1, "HUGTIP": 2}


# Estilo de cada serie ficticia, para que no todas se parezcan: (estilo,
# tendencia). "suave" = deriva lenta; "brusco" = deriva lenta más uno o dos
# saltos puntuales. Tendencia en amplitudes a lo largo de todo el periodo
# (+ sube, - baja; 0 = sin tendencia). Por defecto ("suave", 0).
STYLES = {
    "hemoglobina": ("suave", -0.8),
    "hematies": ("suave", -0.5),
    "rdw_cv": ("suave", 0.6),
    "neutrofils_total": ("brusco", 0.0),
    "plaquetes": ("suave", 0.3),
    "ferro_serum": ("brusco", 0.4),
    "ferritina_serum": ("suave", 1.0),
    "colesterol_serum": ("suave", -1.0),
    "colesterol_ldl": ("brusco", -0.7),
    "triglicerids_serum": ("brusco", 0.0),
    "glucosa_serum": ("suave", 0.9),
    "hb_glicosilada_hba1c_sang": ("suave", 1.0),
    "alanina_aminotransferasa_alt_serum": ("brusco", 0.0),
    "creatinina_serum": ("suave", 0.8),
    "filtrat_glomerular_estimat_serum": ("suave", -0.9),
    "urat_serum": ("brusco", 0.3),
    "proteina_c_reactiva_serum": ("brusco", 0.0),
    "vsg_velocitat_de_sedimentacio_globular": ("brusco", 0.0),
    "tirotropina_tsh_serum": ("suave", 0.7),
}


def synthetic_series(seed: str, mid: float, amp: float) -> list[float]:
    """Valores de una serie ficticia alrededor de `mid` (escala `amp`):
    paseo aleatorio con memoria (cada valor se parece al anterior, como en
    una analítica real), más la tendencia y los saltos de su estilo
    (`STYLES`). Semilla fija por parámetro: cada ejecución da las mismas
    capturas."""
    style, trend = STYLES.get(seed, ("suave", 0.0))
    rng = random.Random(seed)
    n = len(REPORTS)
    drift = rng.uniform(-0.4, 0.4)
    values = []
    for i in range(n):
        drift = 0.8 * drift + rng.gauss(0, 0.3)
        values.append(mid + amp * (trend * (2 * i / (n - 1) - 1) + drift))
    if style == "brusco":
        for i in rng.sample(range(2, n), rng.choice((1, 2))):
            values[i] = mid + amp * rng.choice((-1, 1)) * rng.uniform(1.1, 1.5)
    return [max(v, mid * 0.1) for v in values]  # nunca negativos


# canonical_id, (nombre Mataró, nombre Synlab, nombre HUGTIP), (unidad por laboratorio), rango,
# (centro, escala) de la serie sintética (ver `synthetic_series`), decimales
PARAMS = [
    ("hemoglobina", ("Hemoglobina", "Hemoglobina", "San-Hemoglobina, c. massa"), ("g/dL",) * 3,
     (13.0, 17.0), (15.0, 2.4), 1),
    ("hematies", ("Hematies", "Hematíes", "San-Hematies, c. nom."), ("x10^6/ul", "x106/mm³", "x10^12/L"),
     (4.5, 5.9), (5.2, 0.9), 2),
    ("vcm", ("VCM", "Volumen corpuscular medio (VCM)", "San-Volum Corpuscular Mig, vol"), ("fL",) * 3,
     (80.0, 100.0), (90.0, 12.0), 1),
    ("rdw_cv", ("RDW-CV", "Indice de anisocitosis (RDW)", "San-Ample Distribució Eritrocits,"), ("%",) * 3,
     (11.5, 15.0), (13.3, 2.2), 1),
    ("neutrofils_total", ("Neutròfils total", "Neutrófilos", "San-Neutròfils, c. nom"),
     ("x10^3/ul", "x10³/mm³", "x10^9/L"), (2.0, 7.5), (4.7, 3.3), 2),
    ("linfocits_total", ("Limfòcits total", "Linfocitos", "San-Limfòcits, c. nom"),
     ("x10^3/ul", "x10³/mm³", "x10^9/L"), (1.0, 3.0), (2.0, 1.2), 2),
    ("monocits_total", ("Monòcits total", "Monocitos", "San-Monòcits, c. nom"),
     ("x10^3/ul", "x10³/mm³", "x10^9/L"), (0.2, 0.8), (0.5, 0.35), 2),
    ("plaquetes", ("Plaquetes", "Plaquetas", "San-Plaquetes, c. nom"), ("x10^3/ul", "x10³/mm³", "x10^9/L"),
     (150.0, 400.0), (275.0, 150.0), 0),
    ("ferro_serum", ("Ferro sèrum", "Hierro", "Srm-Ferro, c. subst."), ("mcg/dL", "µg/dL", "µg/dL"),
     (59.0, 158.0), (105.0, 60.0), 0),
    ("ferritina_serum", ("Ferritina sèrum", "Ferritina", "Srm-Ferritina, c. subst."), ("ng/mL",) * 3,
     (30.0, 400.0), (220.0, 200.0), 0),
    ("transferrina_serum", ("Transferrina sèrum", "Transferrina", "Srm-Transferrina"), ("mg/dL",) * 3,
     (200.0, 360.0), (280.0, 100.0), 0),
    ("colesterol_serum", ("Colesterol sèrum", "Colesterol total", "Srm-Colesterol; c. subst."), ("mg/dL",) * 3,
     (None, 200.0), (205.0, 45.0), 0),
    ("colesterol_hdl", ("Colesterol HDL", "Colesterol HDL", "Srm-Colesterol HDL"), ("mg/dL",) * 3,
     (40.0, None), (48.0, 14.0), 0),
    ("colesterol_ldl", ("Colesterol LDL", "Colesterol LDL", "Srm-Colesterol LDL"), ("mg/dL",) * 3,
     (None, 130.0), (130.0, 40.0), 0),
    ("triglicerids_serum", ("Triglicèrids sèrum", "Triglicéridos", "Srm-Triglicèrids; c. subst."), ("mg/dL",) * 3,
     (None, 150.0), (145.0, 70.0), 0),
    ("glucosa_serum", ("Glucosa sèrum", "Glucosa (suero/plasma)", "Srm-Glucosa; c. subst."), ("mg/dL",) * 3,
     (70.0, 105.0), (92.0, 22.0), 0),
    ("hb_glicosilada_hba1c_sang", ("Hb glicosilada (HbA1c) sang", "Hemoglobina A1c (NGSP)", "San-HbA1c"),
     ("%",) * 3, (4.0, 5.7), (5.5, 0.6), 1),
    ("aspartat_aminotranferasa_ast_serum",
     ("Aspartat aminotranferasa (AST) sèrum", "Aspartato aminotransferasa (AST/GOT)",
      "Srm-Aspartat-aminotransferasa; c. cat."), ("U/L",) * 3, (10.0, 40.0), (30.0, 18.0), 0),
    ("alanina_aminotransferasa_alt_serum",
     ("Alanina aminotransferasa (ALT) sèrum", "Alanina aminotransferasa (ALT/GPT)",
      "Srm-Alanina-aminotransferasa; c. cat."), ("U/L",) * 3, (7.0, 41.0), (32.0, 20.0), 0),
    ("creatinina_serum", ("Creatinina sèrum", "Creatinina", "Srm-Creatinini; c. subst."), ("mg/dL",) * 3,
     (0.6, 1.2), (0.95, 0.35), 2),
    ("filtrat_glomerular_estimat_serum", ("Filtrat glomerular estimat sèrum", "Filtrado glomerular estimado",
                                          "Srm-Filtrat glomerular estimat"), ("mL/min/1,73m2",) * 3,
     (60.0, None), (78.0, 25.0), 0),
    ("urea_serum", ("Urea sèrum", "Urea", "Srm-Urea; c. subst."), ("mg/dL",) * 3, (17.0, 49.0), (34.0, 20.0), 0),
    ("urat_serum", ("Urat sèrum", "Urato", "Srm-Urat; c. subst."), ("mg/dL",) * 3, (3.4, 7.0), (6.0, 1.8), 1),
    ("calci", ("Calci", "Calcio total", "Srm-Calci(II); c. subst."), ("mg/dL",) * 3, (8.5, 10.5), (9.5, 1.2), 1),
    ("albumina_serum", ("Albúmina sèrum", "Albúmina sèrum", "Albúmina sèrum"), ("g/dL",) * 3, (3.5, 5.2),
     (4.3, 1.0), 1),
    ("proteina_c_reactiva_serum", ("Proteïna C reactiva sèrum", "Proteína C reactiva", "Proteïna C reactiva sèrum"),
     ("mg/dL",) * 3, (0.0, 0.5), (0.6, 0.55), 2),
    ("vsg_velocitat_de_sedimentacio_globular",
     ("VSG velocitat de sedimentació globular", "Velocidad de sedimentación globular (VSG)", "San-VSG"),
     ("mm/h",) * 3, (0.0, 20.0), (15.0, 12.0), 0),
    ("tirotropina_tsh_serum", ("Tirotropina (TSH) sèrum", "Hormona estimulante del tiroides (TSH)", "Srm-TSH"),
     ("mcUI/mL", "mU/L", "mcUI/mL"), (0.35, 4.94), (2.8, 2.6), 2),
    ("tiroxina_lliure_t4l", ("Tiroxina lliure (T4L)", "Tiroxina libre (T4L)", "Srm-Tiroxina lliure"), ("ng/dL",) * 3,
     (0.7, 1.48), (1.1, 0.5), 2),
]


def build_demo_db(path: Path):
    """BD cifrada temporal con "PACIENTE FICTICIO" y sus analíticas."""
    con = db.connect("demo-solo-para-capturas", path)
    pid, _ = repository.get_or_create_patient(
        con, "PACIENTE FICTICIO", "1970-05-15", "00000000T", "000000", sex="Hombre", cip="FICT0000000000",
    )
    repository.update_patient(con, pid, {
        "smoker_current": 0, "smoker_former": 1, "smoker_former_from": 1995, "smoker_former_to": 2008,
    })
    repository.set_setting(con, "reports_dir", r"C:\Analitix\informes_analiticas")
    series = {cid: synthetic_series(cid, mid, amp) for cid, _n, _u, _r, (mid, amp), _d in PARAMS}
    for n, (fecha, lab) in enumerate(REPORTS):
        name = f"informe_ficticio_{fecha}.pdf"
        rid = repository.upsert_report(
            con, pid, f"DEMO-{n:04d}", fecha, fecha, name,
            file_md5=hashlib.md5(name.encode()).hexdigest(), lab=lab,
        )
        li = LAB_INDEX[lab]
        for cid, names, units, (low, high), _osc, decimals in PARAMS:
            value = round(series[cid][n], decimals)
            repository.insert_result(con, rid, dict(
                section=None, test_group=None, loinc_code=None, raw_name=names[li], canonical_id=cid,
                value_raw=f"{value:g}", value_num=value, unit=units[li], ref_low=low, ref_high=high,
                ref_text=None, flag_pdf=None, flag_calc=compute_flag(value, low, high), sample_date=f"{fecha} 08:30:00",
            ))
    # Tensión arterial de ejemplo (ficticia): dos semanas de mañana y noche
    # en casa, con deriva lenta, y dos tomas en la consulta.
    rng = random.Random("tension")
    sis, dia = 128.0, 82.0
    for d in range(14):
        for hora in ("07:45", "21:30"):
            sis = 0.7 * sis + 0.3 * 128 + rng.gauss(0, 5)
            dia = 0.7 * dia + 0.3 * 82 + rng.gauss(0, 3)
            repository.add_bp_reading(con, pid, {
                "measured_at": f"2026-03-{d + 1:02d} {hora}", "systolic": round(sis), "diastolic": round(dia),
                "pulse": rng.randint(60, 76), "place": "casa", "note": "antes del desayuno" if hora == "07:45" else None,
            }, source="csv")
    for fecha, s, di in (("2026-02-10 10:30", 138, 88), ("2026-04-14 09:15", 134, 85)):
        repository.add_bp_reading(con, pid, {"measured_at": fecha, "systolic": s, "diastolic": di, "pulse": 70,
                                             "place": "consulta", "note": "revisión"})
    # Objetivo del médico de ejemplo (ficticio), para las capturas del LDL.
    repository.set_target(con, pid, "colesterol_ldl", None, 100.0, "Ejemplo ficticio")
    con.commit()
    return con, pid


def _save(img, name: str) -> None:
    # Paleta de 256 colores: capturas de interfaz, casi sin degradados;
    # reduce mucho el tamaño en el repositorio sin pérdida visible.
    img.convert("RGB").quantize(colors=256).save(OUT / name, optimize=True)
    print("  ", name)


def _grab(widget, name: str) -> None:
    top = widget.winfo_toplevel()
    top.lift()
    top.attributes("-topmost", True)
    top.focus_force()
    top.update()
    time.sleep(0.8)
    top.update()
    x, y = top.winfo_rootx(), top.winfo_rooty()
    _save(ImageGrab.grab(bbox=(x, y, x + top.winfo_width(), y + top.winfo_height())), name)


def _last_toplevel(parent):
    return [w for w in parent.winfo_children() if isinstance(w, gui.tk.Toplevel)][-1]


def _select(listbox, match: str) -> None:
    for i in range(listbox.size()):
        if match.lower() in listbox.get(i).lower():
            listbox.selection_clear(0, "end")
            listbox.selection_set(i)
            listbox.see(i)
            return
    raise ValueError(f"'{match}' no está en la lista")


def capture_startup(tmp: Path) -> None:
    """Arranque: aviso legal (splash), ventana de carga y creación de la
    contraseña de una base de datos nueva (la de ejemplo, en `tmp`)."""
    root = gui.tk.Tk()
    root.withdraw()
    branding.set_app_icon(root)

    def _splash() -> None:
        splash = _last_toplevel(root)
        _grab(splash, "splash.png")
        next(w for w in splash.winfo_children() if isinstance(w, gui.tk.Button)).invoke()  # "Aceptar"

    root.after(1200, _splash)
    assert branding.show_splash(root)

    loading, bar = app_main._show_loading(root)
    _grab(loading, "cargando.png")
    bar.stop()
    loading.destroy()

    def _password(name: str, then=None) -> None:
        dialog = _last_toplevel(root)
        dialog.entry.insert(0, DEMO_PASSWORD)
        _grab(dialog, name)
        if then:
            root.after(1000, then)
        dialog.ok()

    app_main.DB_PATH = tmp / "nueva.db"  # no existe: pide crear la contraseña
    root.after(1000, lambda: _password("contrasena_crear.png", lambda: _password("contrasena_repetir.png")))
    assert app_main._ask_password(root) == DEMO_PASSWORD
    root.destroy()


def capture_app(con, pid) -> None:
    gui.messagebox.showinfo = lambda *a, **k: None
    app = gui.AnalitixApp(con)
    w, h = WINDOW
    app.geometry(f"{w}x{h}+40+40")
    app.deiconify()
    app.update()
    _grab(app, "inicio.png")
    app.current_patient_id = pid
    app._refresh_patients()
    app.update()

    def show(page: str) -> None:
        app._show_page(page)
        app.update()

    def dialog_after(name: str) -> None:
        def _capture() -> None:
            dialog = _last_toplevel(app)
            _grab(dialog, name)
            dialog.destroy()
        app.after(800, _capture)

    for page, name in (("importar", "importar.png"), ("pacientes", "pacientes.png")):
        show(page)
        _grab(app, name)

    dialog_after("ficha_paciente.png")
    app._edit_selected_patient()

    show("manual")
    _grab(app, "entrada_manual.png")
    show("tension")
    _grab(app, "tension_arterial.png")

    show("evolucion")
    for match, name in (("Hemoglobina", "evolucion.png"), ("Colesterol LDL", "evolucion_ldl.png")):
        _select(app.list_tests_evolucion, match)
        app._show_evolution()
        _grab(app, name)
    dialog_after("objetivo_medico.png")  # con el LDL elegido
    app._edit_target()

    show("comparativa")
    for i, (_cid, label) in enumerate(app._evolution_tests):
        if app._comparativa_vars[i] is not None:
            app._comparativa_vars[i].set(label in ("Ferritina sèrum", "Hemoglobina"))
    app._show_comparison()
    _grab(app, "comparativa.png")

    show("resumen")
    notebook = next(c for c in app.tab_resumen.winfo_children() if isinstance(c, gui.ttk.Notebook))
    notebook.select(0)
    _grab(app, "resumen_tabla.png")
    notebook.select(1)
    _grab(app, "resumen_cambios.png")
    notebook.select(2)
    _grab(app, "resumen_posicion.png")

    show("mapa_calor")
    app.var_mapa_calor_set.set(gui.HEATMAP_OUT_OF_RANGE)
    app._show_heatmap()
    _grab(app, "mapa_calor.png")

    for page, listbox, method, name in (
        ("riesgo_cv", app.list_lipid_indices, app._show_lipid_index, "panel_riesgo_cv.png"),
        ("salud_hepatica", app.list_hepatic_indices, app._show_hepatic_index, "panel_hepatico.png"),
        ("funcion_renal", app.list_renal_indices, app._show_renal_index, "panel_renal.png"),
        ("hemograma", app.list_hemogram_indices, app._show_hemogram_index, "panel_hemograma.png"),
        ("hierro", app.list_iron_indices, app._show_iron_index, "panel_hierro.png"),
        ("inflamacion", None, app._show_inflammation_chart, "panel_inflamacion.png"),
        ("acido_urico", app.list_uric_acid_indices, app._show_uric_acid_index, "panel_acido_urico.png"),
        ("calcio", app.list_calcio_indices, app._show_calcio_index, "panel_calcio.png"),
        ("glucemia", app.list_glucemia_indices, app._show_glucemia_index, "panel_glucemia.png"),
        ("tiroides", None, app._show_thyroid_chart, "panel_tiroides.png"),
    ):
        show(page)
        if listbox is not None:
            listbox.selection_clear(0, "end")
            listbox.selection_set(0)
        method()
        _grab(app, name)

    for page, name in (("exportar", "exportar.png"), ("explorador", "explorador_bd.png")):
        show(page)
        _grab(app, name)

    show("catalogo")
    app._refresh_catalogo()
    app.update()
    app.tk.call(app.tree_catalogo.heading("nombre", "command"))  # ordenado por nombre
    _grab(app, "normalizar_pruebas.png")

    show("config")
    _grab(app, "configuracion.png")

    dialog_after("acerca_de.png")
    app._show_about()

    export_pdf_example(app)
    app.destroy()


def export_pdf_example(app) -> None:
    """Informe PDF de parámetros alterados del paciente ficticio, tal cual lo
    genera la app (Exportar → Informe de alterados), más una imagen de la
    portada, la tabla de alterados y el primer gráfico para el manual (ver
    `export.export_pdf` para el orden de las páginas)."""
    PDF_EJEMPLO.parent.mkdir(parents=True, exist_ok=True)
    gui.filedialog.asksaveasfilename = lambda *a, **k: str(PDF_EJEMPLO)
    app._export_pdf("alterados")
    print("  ", PDF_EJEMPLO.relative_to(ROOT))
    with pdfplumber.open(PDF_EJEMPLO) as pdf:
        for index, name in ((0, "portada"), (1, "tabla"), (3, "grafico")):
            _save(pdf.pages[index].to_image(resolution=72).original, f"pdf_alterados_{name}.png")


def render_technical_figures(con, pid) -> None:
    """Figuras de la documentación técnica, generadas sin capturar pantalla."""
    series = repository.get_series(con, "hemoglobina", pid)
    evolution_figure(series, "Hemoglobina (paciente ficticio)").savefig(OUT / "tecnica_puntos_laboratorio.png", dpi=90, bbox_inches="tight")
    rows = []
    for label, ids in gui.HEATMAP_SETS["Panel: Hemograma"]:
        merged = sorted(repository.get_merged_series(con, ids, pid).values(), key=lambda r: r["fecha"])
        rows.append((label, merged))
    heatmap_figure(rows, "Panel: Hemograma (paciente ficticio)").savefig(OUT / "tecnica_mapa_calor.png", dpi=90, bbox_inches="tight")
    summary = repository.get_latest_report_summary(con, pid)
    change_rows = [
        dict(label=f["raw_name"], value=f["value_num"], previous=f["valor_anterior"], unit=f["unit"],
             ref_low=f["ref_low"], ref_high=f["ref_high"], pct=f["pct"])
        for f in gui.AnalitixApp._classify_latest_report(summary)
    ]
    changes_figure(change_rows, "Qué ha cambiado (paciente ficticio)").savefig(OUT / "tecnica_que_ha_cambiado.png", dpi=90, bbox_inches="tight")
    print("   tecnica_*.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        print("Arranque (no toques el ratón):")
        capture_startup(Path(tmp))
        con, pid = build_demo_db(Path(tmp) / "demo.db")
        try:
            print("Figuras técnicas:")
            render_technical_figures(con, pid)
            print("Capturas de la aplicación (no toques el ratón):")
            capture_app(con, pid)
        finally:
            con.close()


if __name__ == "__main__":
    main()
