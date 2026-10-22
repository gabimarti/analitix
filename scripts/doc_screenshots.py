# ---------------------------------------------------------------------------
# Script: doc_screenshots.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-25
# Última actualización: 2026-10-09
# ---------------------------------------------------------------------------
"""Genera las capturas de pantalla y figuras de la documentación
(`docs/images/`) y el informe PDF de ejemplo (`docs/ejemplos/`) con un
paciente **ficticio** y datos inventados.

Uso (Windows, desde la raíz del proyecto, con la app instalada):

    venv\\Scripts\\python.exe scripts\\doc_screenshots.py

Nunca abre `data/analitix.db` ni ningún PDF real: crea una base de datos
cifrada temporal, la misma que crea el botón «Base de datos de ejemplo...»
(`analitix.demo`: paciente ficticio y analíticas sintéticas de tres
laboratorios), abre la aplicación sobre ella, recorre las pantallas y
guarda cada captura. Las ventanas aparecen unos segundos en pantalla (hay
que traerlas al frente para capturarlas); no toques el ratón ni el teclado
mientras dura (~1 minuto). Al terminar borra la base de datos temporal. Las
figuras de la documentación técnica se generan directamente con matplotlib
(sin capturar pantalla).
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pdfplumber  # noqa: E402
from PIL import ImageGrab  # noqa: E402

from analitix import (  # noqa: E402
    branding,
    gui,
    main as app_main,  # noqa: E402
    repository,
)
from analitix.charts import changes_figure, evolution_figure, heatmap_figure  # noqa: E402
from analitix.demo import DEMO_PASSWORD, build_demo_db  # noqa: E402

OUT = ROOT / "docs" / "images"
PDF_EJEMPLO = ROOT / "docs" / "ejemplos" / "informe_alterados_ficticio.pdf"
WINDOW = (1280, 820)


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
        next(
            w for w in splash.winfo_children() if isinstance(w, gui.tk.Button)
        ).invoke()  # "Aceptar"

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

    # Contraseña de una base de datos nueva (diálogo "Nueva base de datos").
    root.after(
        1000, lambda: _password("contrasena_crear.png", lambda: _password("contrasena_repetir.png"))
    )
    assert app_main._ask_new_password(root) == DEMO_PASSWORD
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
        (
            "acido_urico",
            app.list_uric_acid_indices,
            app._show_uric_acid_index,
            "panel_acido_urico.png",
        ),
        ("calcio", app.list_calcio_indices, app._show_calcio_index, "panel_calcio.png"),
        ("glucemia", app.list_glucemia_indices, app._show_glucemia_index, "panel_glucemia.png"),
        ("tiroides", None, app._show_thyroid_chart, "panel_tiroides.png"),
        ("tension_panel", None, lambda: None, "panel_tension.png"),
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
    evolution_figure(series, "Hemoglobina (paciente ficticio)").savefig(
        OUT / "tecnica_puntos_laboratorio.png", dpi=90, bbox_inches="tight"
    )
    rows = []
    for label, ids in gui.HEATMAP_SETS["Panel: Hemograma"]:
        merged = sorted(
            repository.get_merged_series(con, ids, pid).values(), key=lambda r: r["fecha"]
        )
        rows.append((label, merged))
    heatmap_figure(rows, "Panel: Hemograma (paciente ficticio)").savefig(
        OUT / "tecnica_mapa_calor.png", dpi=90, bbox_inches="tight"
    )
    summary = repository.get_latest_report_summary(con, pid)
    change_rows = [
        dict(
            label=f["raw_name"],
            value=f["value_num"],
            previous=f["valor_anterior"],
            unit=f["unit"],
            ref_low=f["ref_low"],
            ref_high=f["ref_high"],
            pct=f["pct"],
        )
        for f in gui.AnalitixApp._classify_latest_report(summary)
    ]
    changes_figure(change_rows, "Qué ha cambiado (paciente ficticio)").savefig(
        OUT / "tecnica_que_ha_cambiado.png", dpi=90, bbox_inches="tight"
    )
    print("   tecnica_*.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        print("Arranque (no toques el ratón):")
        capture_startup(Path(tmp))
        con, pid = build_demo_db(
            Path(tmp) / "demo.db", reports_dir=r"C:\Analitix\informes_analiticas"
        )
        try:
            print("Figuras técnicas:")
            render_technical_figures(con, pid)
            print("Capturas de la aplicación (no toques el ratón):")
            capture_app(con, pid)
        finally:
            con.close()


if __name__ == "__main__":
    main()
