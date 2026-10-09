# ---------------------------------------------------------------------------
# Script: main.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-10-09
# ---------------------------------------------------------------------------
"""Punto de entrada de Analitix."""
from __future__ import annotations

import logging
import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from analitix import databases
from analitix.branding import load_logo_photo, set_app_icon, show_splash
from analitix.db import WrongPasswordError, connect
from analitix.logging_setup import configure_logging
# `AnalitixApp` (gui.py) no se importa aquí arriba a propósito: arrastra
# matplotlib/ttkbootstrap (~2 s de importación) que, importados a nivel de
# módulo, retrasaban la propia ventana de bienvenida (`show_splash`) esos
# mismos ~2 s antes de que apareciera nada en pantalla. Se importa dentro de
# `main()`, después del aviso legal, en un hilo aparte mientras
# `_import_gui_with_loading` muestra una ventana de carga animada.

logger = logging.getLogger("analitix.main")


def _ask_new_password(parent: tk.Misc) -> str | None:
    """Contraseña para una base de datos nueva, escrita dos veces."""
    while True:
        password = simpledialog.askstring(
            "Analitix", "Crea una contraseña para proteger la nueva base de datos:", show="*", parent=parent)
        if password is None:
            return None
        if not password:
            messagebox.showerror("Analitix", "La contraseña no puede estar vacía.", parent=parent)
            continue
        confirm = simpledialog.askstring("Analitix", "Repite la contraseña:", show="*", parent=parent)
        if confirm != password:
            messagebox.showerror("Analitix", "Las contraseñas no coinciden.", parent=parent)
            continue
        return password


def _center(win: tk.Toplevel) -> None:
    win.update_idletasks()
    x = (win.winfo_screenwidth() - win.winfo_reqwidth()) // 2
    y = (win.winfo_screenheight() - win.winfo_reqheight()) // 3
    win.geometry(f"+{x}+{y}")


def _create_database(parent: tk.Misc):
    """Diálogo "Nueva base de datos": nombre corto del paciente (máx. 40),
    nombre de la base de datos (se propone a partir del nombre; el usuario
    lo elige) y contraseña. Crea el fichero cifrado y lo registra en la
    lista. Devuelve `(entrada, con)` o `None` si se cancela."""
    win = tk.Toplevel(parent)
    win.title("Analitix — Nueva base de datos")
    win.transient(parent)
    win.resizable(False, False)
    body = ttk.Frame(win, padding=14)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=f"Nombre del paciente (para reconocerlo en la lista, máx. {databases.NAME_MAX}):").grid(
        row=0, column=0, sticky="w")
    var_nombre = tk.StringVar()
    entry_nombre = ttk.Entry(body, textvariable=var_nombre, width=44)
    entry_nombre.grid(row=1, column=0, sticky="we", pady=(2, 8))
    ttk.Label(body, text="Nombre de la base de datos (p. ej. nombre + DNI u otro identificador):").grid(
        row=2, column=0, sticky="w")
    var_fichero = tk.StringVar()
    ttk.Entry(body, textvariable=var_fichero, width=44).grid(row=3, column=0, sticky="we", pady=(2, 4))
    ttk.Label(body, text="La lista de bases de datos no está cifrada: no pongas datos médicos en estos nombres.",
              foreground="#666666").grid(row=4, column=0, sticky="w", pady=(0, 10))
    sugerido = {"valor": ""}

    def _sugerir(*_args) -> None:
        # Propone el nombre del fichero mientras el usuario no lo cambie.
        if var_fichero.get() in ("", sugerido["valor"]):
            sugerido["valor"] = databases.suggest_filename(var_nombre.get()[:databases.NAME_MAX])
            var_fichero.set(sugerido["valor"])

    var_nombre.trace_add("write", _sugerir)
    resultado: dict = {}

    def _crear() -> None:
        nombre, fichero = var_nombre.get().strip(), var_fichero.get().strip()
        error = databases.validate_new(nombre, fichero)
        if error:
            messagebox.showerror("Analitix", error, parent=win)
            return
        password = _ask_new_password(win)
        if password is None:
            return
        # Primero se registra (valida que el fichero no exista) y después
        # `connect` lo crea; si falla, se deshace el registro.
        databases.add_database(nombre, fichero)
        path = databases.db_path(fichero)
        try:
            con = connect(password, path)
        except ValueError as exc:  # contraseña con forma de clave en bruto (ver db._set_key)
            databases.remove_database(fichero)
            path.unlink(missing_ok=True)
            messagebox.showerror("Analitix", str(exc), parent=win)
            return
        logger.info("Base de datos de paciente creada")
        resultado["valor"] = ({"nombre": nombre, "fichero": fichero}, con)
        win.destroy()

    botones = ttk.Frame(body)
    botones.grid(row=5, column=0, sticky="e")
    ttk.Button(botones, text="Crear", command=_crear).pack(side="left", padx=(0, 6))
    ttk.Button(botones, text="Cancelar", command=win.destroy).pack(side="left")
    win.bind("<Escape>", lambda _e: win.destroy())
    _center(win)
    entry_nombre.focus_set()
    win.grab_set()
    parent.wait_window(win)
    return resultado.get("valor")


def _choose_database(root: tk.Tk):
    """Lista de bases de datos para elegir cuál abrir, o crear una nueva.
    Devuelve `(entrada, None)` para abrir una existente (se pide después su
    contraseña), `(entrada, con)` si se acaba de crear, o `None` para salir."""
    win = tk.Toplevel(root)
    win.title("Analitix — Bases de datos")
    win.resizable(False, False)
    set_app_icon(win)
    body = ttk.Frame(win, padding=14)
    body.pack(fill="both", expand=True)
    lista = databases.list_databases()
    texto = ("Elige la base de datos del paciente que quieres abrir:" if lista
             else "Todavía no hay ninguna base de datos. Crea una para empezar:")
    ttk.Label(body, text=texto).pack(anchor="w", pady=(0, 6))
    tree = ttk.Treeview(body, columns=("nombre", "fichero"), show="headings", height=8, selectmode="browse")
    tree.heading("nombre", text="Paciente")
    tree.heading("fichero", text="Base de datos")
    tree.column("nombre", width=280)
    tree.column("fichero", width=240)
    for d in lista:
        tree.insert("", "end", iid=d["fichero"], values=(d["nombre"], d["fichero"]))
    if lista:
        tree.selection_set(lista[0]["fichero"])
        tree.focus(lista[0]["fichero"])
    tree.pack(fill="both", expand=True)
    resultado: dict = {}

    def _abrir(_event=None) -> None:
        seleccion = tree.selection()
        if seleccion:
            resultado["valor"] = (databases.find_database(seleccion[0]), None)
            win.destroy()

    def _nueva() -> None:
        creada = _create_database(win)
        if creada:
            resultado["valor"] = creada
            win.destroy()

    botones = ttk.Frame(body)
    botones.pack(fill="x", pady=(10, 0))
    ttk.Button(botones, text="Abrir", command=_abrir, state="normal" if lista else "disabled").pack(side="left")
    ttk.Button(botones, text="Nueva base de datos...", command=_nueva).pack(side="left", padx=(6, 0))
    ttk.Button(botones, text="Salir", command=win.destroy).pack(side="right")
    tree.bind("<Double-1>", _abrir)
    win.bind("<Return>", _abrir)
    win.bind("<Escape>", lambda _e: win.destroy())
    _center(win)
    win.grab_set()
    root.wait_window(win)
    return resultado.get("valor")


def _open_database(root: tk.Tk, use_last: bool):
    """Abre una base de datos de paciente: la última usada (si `use_last` y
    sigue existiendo) o la que se elija en la lista, pidiendo su
    contraseña. Cancelar la contraseña vuelve a la lista; salir de la lista
    devuelve `None`. Devuelve `(con, entrada)` y la recuerda como última."""
    entrada = databases.last_database() if use_last else None
    while True:
        con = None
        if entrada is None:
            elegido = _choose_database(root)
            if elegido is None:
                return None
            entrada, con = elegido
        if con is None:
            path = databases.db_path(entrada["fichero"])
            if not path.exists():  # borrada fuera de la app: `connect` crearía una vacía
                messagebox.showerror("Analitix", f"No se encuentra el fichero de la base de datos:\n{path}",
                                     parent=root)
                entrada = None
                continue
            password = simpledialog.askstring(
                "Analitix", f"Contraseña de la base de datos «{entrada['nombre']}»:", show="*", parent=root)
            if password is None:
                entrada = None
                continue
            try:
                con = connect(password, path)
            except WrongPasswordError:
                logger.warning("Intento de apertura con contraseña incorrecta")
                messagebox.showerror("Analitix", "Contraseña incorrecta.", parent=root)
                continue
            except ValueError as exc:
                # Contraseña con la forma reservada de clave SQLCipher en bruto
                # (`_set_key`, ver db.py): mensaje explícito, no una traza.
                logger.warning("Contraseña rechazada: %s", exc)
                messagebox.showerror("Analitix", str(exc), parent=root)
                continue
        databases.set_last_database(entrada["fichero"])
        return con, entrada


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

    use_last = True
    while True:
        abierta = _open_database(root, use_last)
        root.destroy()
        if abierta is None:
            sys.exit(0)
        con, entrada = abierta
        app = AnalitixApp(con, databases.db_path(entrada["fichero"]), entrada["nombre"])
        try:
            app.mainloop()
        except Exception:
            logger.exception("Error no controlado en la interfaz")
            raise
        finally:
            con.close()
        if not app.switch_db:
            break
        # Archivo → "Cambiar de base de datos...": de vuelta a la lista.
        use_last = False
        root = tk.Tk()
        root.withdraw()
        set_app_icon(root)
    logger.info("=== Analitix cerrado ===")


if __name__ == "__main__":
    main()
