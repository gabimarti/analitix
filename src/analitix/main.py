# ---------------------------------------------------------------------------
# Script: main.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-09-29
# ---------------------------------------------------------------------------
"""Punto de entrada de Analitix."""
from __future__ import annotations

import logging
import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from analitix.branding import load_logo_photo, set_app_icon, show_splash
from analitix.config import DB_PATH
from analitix.db import WrongPasswordError, connect
from analitix.logging_setup import configure_logging
# `AnalitixApp` (gui.py) no se importa aquí arriba a propósito: arrastra
# matplotlib/ttkbootstrap (~2 s de importación) que, importados a nivel de
# módulo, retrasaban la propia ventana de bienvenida (`show_splash`) esos
# mismos ~2 s antes de que apareciera nada en pantalla. Se importa dentro de
# `main()`, después del aviso legal, en un hilo aparte mientras
# `_import_gui_with_loading` muestra una ventana de carga animada.

logger = logging.getLogger("analitix.main")


def _ask_password(root: tk.Tk) -> str | None:
    is_new = not DB_PATH.exists()
    prompt = (
        "Crea una contraseña para proteger la nueva base de datos:"
        if is_new
        else "Introduce la contraseña de la base de datos:"
    )
    while True:
        password = simpledialog.askstring("Analitix", prompt, show="*", parent=root)
        if password is None:
            return None
        if not password:
            messagebox.showerror("Analitix", "La contraseña no puede estar vacía.", parent=root)
            continue
        if is_new:
            confirm = simpledialog.askstring("Analitix", "Repite la contraseña:", show="*", parent=root)
            if confirm != password:
                messagebox.showerror("Analitix", "Las contraseñas no coinciden.", parent=root)
                continue
        return password


def _show_loading(root: tk.Tk) -> tuple[tk.Toplevel, ttk.Progressbar]:
    """Ventana de carga centrada y bien visible (logo, título grande y barra
    de progreso en movimiento) mientras se importa `gui.py`."""
    loading = tk.Toplevel(root)
    loading.overrideredirect(True)
    loading.attributes("-topmost", True)
    loading.configure(bg="#2c3e50")  # borde de 2 px del color del splash
    body = tk.Frame(loading, bg="white", padx=40, pady=24)
    body.pack(padx=2, pady=2)
    photo = load_logo_photo(96)
    logo = tk.Label(body, image=photo, bg="white", borderwidth=0)
    logo.image = photo  # referencia viva
    logo.pack(pady=(0, 10))
    tk.Label(
        body, text="Cargando Analitix…", bg="white", fg="#2c3e50", font=("Segoe UI", 18, "bold"),
    ).pack()
    tk.Label(
        body, text="Preparando la interfaz y los gráficos, un momento por favor.",
        bg="white", fg="#555555", font=("Segoe UI", 10),
    ).pack(pady=(4, 14))
    bar = ttk.Progressbar(body, mode="indeterminate", length=380)
    bar.pack()
    bar.start(12)
    loading.update_idletasks()
    width, height = loading.winfo_reqwidth(), loading.winfo_reqheight()
    x = (loading.winfo_screenwidth() - width) // 2
    y = (loading.winfo_screenheight() - height) // 2
    loading.geometry(f"{width}x{height}+{x}+{y}")
    loading.update()
    return loading, bar


def _import_gui_with_loading(root: tk.Tk) -> type:
    """Importa `AnalitixApp` en un hilo aparte (matplotlib/ttkbootstrap
    tardan varios segundos) mientras el hilo principal sigue atendiendo el
    bucle de Tk, para que la barra de `_show_loading` se mueva de verdad en
    vez de congelarse. La importación no crea ningún widget, así que no
    toca Tk desde el hilo secundario; un error se relanza aquí."""
    loading, bar = _show_loading(root)
    outcome: dict = {}

    def _worker() -> None:
        try:
            from analitix.gui import AnalitixApp
            outcome["cls"] = AnalitixApp
        except BaseException as exc:  # noqa: BLE001 - se relanza en el hilo principal
            outcome["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    def _poll() -> None:
        if thread.is_alive():
            root.after(30, _poll)
        else:
            loading.quit()

    root.after(30, _poll)
    loading.mainloop()  # vuelve con `quit()` en cuanto termina la importación
    bar.stop()
    loading.destroy()
    if "error" in outcome:
        raise outcome["error"]
    return outcome["cls"]


def _self_test() -> int:
    """Comprobación sin interfaz del ejecutable empaquetado (`Analitix.exe
    --self-test`, la usa la prueba del instalador): importa la interfaz,
    carga los perfiles, abre una BD cifrada temporal y lee un PDF sintético.
    Devuelve el código de salida (0 = correcto); el detalle va al log."""
    import tempfile
    from pathlib import Path

    try:
        from matplotlib.figure import Figure

        from analitix import gui  # noqa: F401 - basta con que importe
        from analitix.parser_profiles import load_profiles
        from analitix.pdf_parser import extract_lines

        assert load_profiles(), "sin perfiles de parser"
        with tempfile.TemporaryDirectory() as tmp:
            connect("self-test", Path(tmp) / "self_test.db").close()
            pdf = Path(tmp) / "self_test.pdf"
            fig = Figure()
            fig.text(0.1, 0.5, "Glucosa sèrum 95 mg/dL ( 74 - 106 )")
            fig.savefig(pdf)
            assert "Glucosa" in " ".join(extract_lines(pdf)), "no se lee el PDF"
    except Exception:
        logger.exception("Autocomprobación fallida")
        return 1
    logger.info("Autocomprobación correcta")
    return 0


def main() -> None:
    configure_logging()
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    root = tk.Tk()
    root.withdraw()
    set_app_icon(root)
    if not show_splash(root):
        logger.info("Aviso legal no aceptado; cerrando la aplicación")
        root.destroy()
        sys.exit(0)

    AnalitixApp = _import_gui_with_loading(root)  # noqa: N806 - es una clase

    con = None
    while con is None:
        password = _ask_password(root)
        if password is None:
            root.destroy()
            sys.exit(0)
        try:
            con = connect(password)
        except WrongPasswordError:
            logger.warning("Intento de apertura con contraseña incorrecta")
            messagebox.showerror("Analitix", "Contraseña incorrecta.", parent=root)
        except ValueError as exc:
            # Contraseña con la forma reservada de clave SQLCipher en bruto
            # (`_set_key`, ver db.py) — caso de esquina, nunca debería llegar
            # aquí sin control (mensaje explícito en vez de una traza cruda).
            logger.warning("Contraseña rechazada: %s", exc)
            messagebox.showerror("Analitix", str(exc), parent=root)

    root.destroy()
    app = AnalitixApp(con)
    try:
        app.mainloop()
    except Exception:
        logger.exception("Error no controlado en la interfaz")
        raise
    finally:
        con.close()
        logger.info("=== Analitix cerrado ===")


if __name__ == "__main__":
    main()
