# ---------------------------------------------------------------------------
# Script: doc_screenshots.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-25
# ---------------------------------------------------------------------------
"""Genera las capturas de pantalla y figuras de la documentación
(`docs/images/`) con un paciente **ficticio** y datos inventados.

Uso (Windows, desde la raíz del proyecto, con la app instalada):

    venv\\Scripts\\python.exe scripts\\doc_screenshots.py

Nunca abre `data/analitix.db` ni ningún PDF: crea una base de datos cifrada
temporal con "PACIENTE FICTICIO" y unas analíticas sintéticas de tres
laboratorios, abre la aplicación sobre ella, recorre las pestañas y guarda
cada captura. La ventana aparece unos segundos en pantalla (hay que traerla
al frente para capturarla); no toques el ratón mientras dura. Al terminar
borra la base de datos temporal. Las figuras de la documentación técnica se
generan directamente con matplotlib (sin capturar pantalla).
"""
from __future__ import annotations

import hashlib
import math
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import ImageGrab  # noqa: E402

from analitix import db, gui, repository  # noqa: E402
from analitix.charts import changes_figure, evolution_figure, heatmap_figure  # noqa: E402
from analitix.pdf_parser import compute_flag  # noqa: E402

OUT = ROOT / "docs" / "images"
WINDOW = (1280, 820)

# Analíticas ficticias: (fecha, laboratorio). Tres laboratorios para que se
# vean la forma del punto por laboratorio y los nombres de prueba distintos.
REPORTS = [
    ("2021-03-09", "Synlab/Eurofins"), ("2021-10-14", "Synlab/Eurofins"), ("2022-05-18", "HUGTIP"),
    ("2022-12-01", "HUGTIP"), ("2023-06-20", "HUGTIP"), ("2024-01-16", "H. Mataró"),
    ("2024-09-03", "H. Mataró"), ("2025-03-11", "H. Mataró"), ("2025-10-07", "H. Mataró"),
    ("2026-04-14", "H. Mataró"),
]
LAB_INDEX = {"H. Mataró": 0, "Synlab/Eurofins": 1, "HUGTIP": 2}


def curve(start: float, end: float, wobble: float = 0.0, bump: tuple[int, float] | None = None):
    """Valores de una serie ficticia: de `start` a `end` con una oscilación
    suave y, opcionalmente, un pico puntual (índice, valor)."""
    n = len(REPORTS)
    values = [start + (end - start) * i / (n - 1) + wobble * math.sin(i * 1.7) for i in range(n)]
    if bump:
        values[bump[0]] = bump[1]
    return values


# canonical_id, (nombre Mataró, nombre Synlab, nombre HUGTIP), (unidad por laboratorio), rango, valores, decimales
PARAMS = [
    ("hemoglobina", ("Hemoglobina", "Hemoglobina", "San-Hemoglobina, c. massa"), ("g/dL",) * 3,
     (13.0, 17.0), curve(12.2, 14.6, 0.3), 1),
    ("hematies", ("Hematies", "Hematíes", "San-Hematies, c. nom."), ("x10^6/ul", "x106/mm³", "x10^12/L"),
     (4.5, 5.9), curve(4.3, 5.0, 0.1), 2),
    ("vcm", ("VCM", "Volumen corpuscular medio (VCM)", "San-Volum Corpuscular Mig, vol"), ("fL",) * 3,
     (80.0, 100.0), curve(79.0, 90.0, 1.0), 1),
    ("rdw_cv", ("RDW-CV", "Indice de anisocitosis (RDW)", "San-Ample Distribució Eritrocits,"), ("%",) * 3,
     (11.5, 15.0), curve(16.1, 13.0, 0.3), 1),
    ("neutrofils_total", ("Neutròfils total", "Neutrófilos", "San-Neutròfils, c. nom"),
     ("x10^3/ul", "x10³/mm³", "x10^9/L"), (2.0, 7.5), curve(3.4, 4.1, 0.4), 2),
    ("linfocits_total", ("Limfòcits total", "Linfocitos", "San-Limfòcits, c. nom"),
     ("x10^3/ul", "x10³/mm³", "x10^9/L"), (1.0, 3.0), curve(2.1, 2.3, 0.2), 2),
    ("monocits_total", ("Monòcits total", "Monocitos", "San-Monòcits, c. nom"),
     ("x10^3/ul", "x10³/mm³", "x10^9/L"), (0.2, 0.8), curve(0.45, 0.5, 0.05), 2),
    ("plaquetes", ("Plaquetes", "Plaquetas", "San-Plaquetes, c. nom"), ("x10^3/ul", "x10³/mm³", "x10^9/L"),
     (150.0, 400.0), curve(262, 280, 18), 0),
    ("ferro_serum", ("Ferro sèrum", "Hierro", "Srm-Ferro, c. subst."), ("mcg/dL", "µg/dL", "µg/dL"),
     (59.0, 158.0), curve(44, 96, 6), 0),
    ("ferritina_serum", ("Ferritina sèrum", "Ferritina", "Srm-Ferritina, c. subst."), ("ng/mL",) * 3,
     (30.0, 400.0), curve(16, 74, 4), 0),
    ("transferrina_serum", ("Transferrina sèrum", "Transferrina", "Srm-Transferrina"), ("mg/dL",) * 3,
     (200.0, 360.0), curve(385, 280, 8), 0),
    ("colesterol_serum", ("Colesterol sèrum", "Colesterol total", "Srm-Colesterol; c. subst."), ("mg/dL",) * 3,
     (None, 200.0), curve(248, 204, 6), 0),
    ("colesterol_hdl", ("Colesterol HDL", "Colesterol HDL", "Srm-Colesterol HDL"), ("mg/dL",) * 3,
     (40.0, None), curve(47, 55, 2), 0),
    ("colesterol_ldl", ("Colesterol LDL", "Colesterol LDL", "Srm-Colesterol LDL"), ("mg/dL",) * 3,
     (None, 130.0), curve(168, 124, 5), 0),
    ("triglicerids_serum", ("Triglicèrids sèrum", "Triglicéridos", "Srm-Triglicèrids; c. subst."), ("mg/dL",) * 3,
     (None, 150.0), curve(182, 118, 10), 0),
    ("glucosa_serum", ("Glucosa sèrum", "Glucosa (suero/plasma)", "Srm-Glucosa; c. subst."), ("mg/dL",) * 3,
     (70.0, 105.0), curve(99, 108, 4), 0),
    ("hb_glicosilada_hba1c_sang", ("Hb glicosilada (HbA1c) sang", "Hemoglobina A1c (NGSP)", "San-HbA1c"),
     ("%",) * 3, (4.0, 5.7), curve(5.5, 5.9, 0.1), 1),
    ("aspartat_aminotranferasa_ast_serum",
     ("Aspartat aminotranferasa (AST) sèrum", "Aspartato aminotransferasa (AST/GOT)",
      "Srm-Aspartat-aminotransferasa; c. cat."), ("U/L",) * 3, (10.0, 40.0), curve(24, 29, 3), 0),
    ("alanina_aminotransferasa_alt_serum",
     ("Alanina aminotransferasa (ALT) sèrum", "Alanina aminotransferasa (ALT/GPT)",
      "Srm-Alanina-aminotransferasa; c. cat."), ("U/L",) * 3, (7.0, 41.0), curve(30, 33, 4, bump=(4, 52)), 0),
    ("creatinina_serum", ("Creatinina sèrum", "Creatinina", "Srm-Creatinini; c. subst."), ("mg/dL",) * 3,
     (0.6, 1.2), curve(0.92, 1.08, 0.03), 2),
    ("filtrat_glomerular_estimat_serum", ("Filtrat glomerular estimat sèrum", "Filtrado glomerular estimado",
                                          "Srm-Filtrat glomerular estimat"), ("mL/min/1,73m2",) * 3,
     (60.0, None), curve(88, 76, 2), 0),
    ("urea_serum", ("Urea sèrum", "Urea", "Srm-Urea; c. subst."), ("mg/dL",) * 3, (17.0, 49.0), curve(31, 38, 3), 0),
    ("urat_serum", ("Urat sèrum", "Urato", "Srm-Urat; c. subst."), ("mg/dL",) * 3, (3.4, 7.0),
     curve(5.9, 6.4, 0.5, bump=(6, 7.6)), 1),
    ("calci", ("Calci", "Calcio total", "Srm-Calci(II); c. subst."), ("mg/dL",) * 3, (8.5, 10.5), curve(9.3, 9.6, 0.15), 1),
    ("albumina_serum", ("Albúmina sèrum", "Albúmina sèrum", "Albúmina sèrum"), ("g/dL",) * 3, (3.5, 5.2),
     curve(4.2, 4.4, 0.1), 1),
    ("proteina_c_reactiva_serum", ("Proteïna C reactiva sèrum", "Proteína C reactiva", "Proteïna C reactiva sèrum"),
     ("mg/dL",) * 3, (0.0, 0.5), curve(0.3, 0.2, 0.1, bump=(5, 1.4)), 2),
    ("tirotropina_tsh_serum", ("Tirotropina (TSH) sèrum", "Hormona estimulante del tiroides (TSH)", "Srm-TSH"),
     ("mcUI/mL", "mU/L", "mcUI/mL"), (0.35, 4.94), curve(2.1, 3.6, 0.3), 2),
    ("tiroxina_lliure_t4l", ("Tiroxina lliure (T4L)", "Tiroxina libre (T4L)", "Srm-Tiroxina lliure"), ("ng/dL",) * 3,
     (0.7, 1.48), curve(1.15, 1.02, 0.04), 2),
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
    for n, (fecha, lab) in enumerate(REPORTS):
        name = f"informe_ficticio_{fecha}.pdf"
        rid = repository.upsert_report(
            con, pid, f"DEMO-{n:04d}", fecha, fecha, name,
            file_md5=hashlib.md5(name.encode()).hexdigest(), lab=lab,
        )
        li = LAB_INDEX[lab]
        for cid, names, units, (low, high), values, decimals in PARAMS:
            value = round(values[n], decimals)
            repository.insert_result(con, rid, dict(
                section=None, test_group=None, loinc_code=None, raw_name=names[li], canonical_id=cid,
                value_raw=f"{value:g}", value_num=value, unit=units[li], ref_low=low, ref_high=high,
                ref_text=None, flag_pdf=None, flag_calc=compute_flag(value, low, high), sample_date=f"{fecha} 08:30:00",
            ))
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


def _select(listbox, match: str) -> None:
    for i in range(listbox.size()):
        if match.lower() in listbox.get(i).lower():
            listbox.selection_clear(0, "end")
            listbox.selection_set(i)
            listbox.see(i)
            return
    raise ValueError(f"'{match}' no está en la lista")


def capture_app(con, pid) -> None:
    gui.messagebox.showinfo = lambda *a, **k: None
    app = gui.AnalitixApp(con)
    w, h = WINDOW
    app.geometry(f"{w}x{h}+40+40")
    app.deiconify()
    app.current_patient_id = pid
    app._refresh_patients()
    app.update()

    def show(page: str) -> None:
        app._show_page(page)
        app.update()

    show("pacientes")
    _grab(app, "pacientes.png")

    def _ficha() -> None:
        dialog = next(c for c in app.winfo_children() if isinstance(c, gui.tk.Toplevel))
        _grab(dialog, "ficha_paciente.png")
        dialog.destroy()

    app.after(600, _ficha)
    app._edit_selected_patient()

    show("evolucion")
    _select(app.list_tests_evolucion, "Hemoglobina")
    app._show_evolution()
    _grab(app, "evolucion.png")

    show("comparativa")
    app.list_tests_comparativa.selection_clear(0, "end")
    for match in ("Ferritina", "Hemoglobina"):
        for i in range(app.list_tests_comparativa.size()):
            if match.lower() in app.list_tests_comparativa.get(i).lower():
                app.list_tests_comparativa.selection_set(i)
                break
    app._show_comparison()
    _grab(app, "comparativa.png")

    show("resumen")
    notebook = next(c for c in app.tab_resumen.winfo_children() if isinstance(c, gui.ttk.Notebook))
    notebook.select(0)
    _grab(app, "resumen_tabla.png")
    notebook.select(1)
    _grab(app, "resumen_cambios.png")

    show("mapa_calor")
    app.var_mapa_calor_set.set(gui.HEATMAP_OUT_OF_RANGE)
    app._show_heatmap()
    _grab(app, "mapa_calor.png")

    for page, listbox, method, name in (
        ("riesgo_cv", app.list_lipid_indices, app._show_lipid_index, "panel_riesgo_cv.png"),
        ("hemograma", app.list_hemogram_indices, app._show_hemogram_index, "panel_hemograma.png"),
        ("hierro", app.list_iron_indices, app._show_iron_index, "panel_hierro.png"),
    ):
        show(page)
        listbox.selection_clear(0, "end")
        listbox.selection_set(0)
        method()
        _grab(app, name)

    show("catalogo")
    app._refresh_catalogo()
    app.update()
    app.tk.call(app.tree_catalogo.heading("nombre", "command"))  # ordenado por nombre
    _grab(app, "normalizar_pruebas.png")

    app.destroy()


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
