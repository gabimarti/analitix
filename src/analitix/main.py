# ---------------------------------------------------------------------------
# Script: main.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-10-09
# ---------------------------------------------------------------------------
"""Punto de entrada de Analitix."""

from __future__ import annotations

import datetime as dt
import logging
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from analitix import databases
from analitix.branding import ask_password, load_logo_photo, set_app_icon, show_splash
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
    return ask_password(
        parent, "Crea una contraseña para proteger la nueva base de datos:", repetir=True
    )


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
    ttk.Label(
        body, text=f"Nombre del paciente (para reconocerlo en la lista, máx. {databases.NAME_MAX}):"
    ).grid(row=0, column=0, sticky="w")
    var_nombre = tk.StringVar()
    entry_nombre = ttk.Entry(body, textvariable=var_nombre, width=44)
    entry_nombre.grid(row=1, column=0, sticky="we", pady=(2, 8))
    ttk.Label(
        body, text="Nombre de la base de datos (p. ej. nombre + DNI u otro identificador):"
    ).grid(row=2, column=0, sticky="w")
    var_fichero = tk.StringVar()
    ttk.Entry(body, textvariable=var_fichero, width=44).grid(
        row=3, column=0, sticky="we", pady=(2, 4)
    )
    ttk.Label(
        body,
        text="La lista de bases de datos no está cifrada: no pongas datos médicos en estos nombres.",
        foreground="#666666",
    ).grid(row=4, column=0, sticky="w", pady=(0, 10))
    # Datos opcionales de la ficha (van dentro de la BD cifrada): si se
    # rellenan, los informes se cotejan con ellos desde el primero.
    ficha = ttk.Labelframe(body, text="Datos del paciente (opcional)", padding=8)
    ficha.grid(row=5, column=0, sticky="we", pady=(0, 10))
    vars_ficha = {}
    for fila, (clave, texto) in enumerate(
        (
            ("nombre", "Nombre"),
            ("apellidos", "Apellidos"),
            ("birth_date", "Fecha de nacimiento (AAAA-MM-DD)"),
            ("dni", "DNI"),
        )
    ):
        ttk.Label(ficha, text=texto).grid(row=fila, column=0, sticky="w", pady=2)
        vars_ficha[clave] = tk.StringVar()
        ttk.Entry(ficha, textvariable=vars_ficha[clave], width=26).grid(
            row=fila, column=1, sticky="we", padx=(8, 0), pady=2
        )
    ttk.Label(
        ficha,
        text="Sirven para reconocer sus informes; se guardan cifrados en la base de datos.",
        foreground="#666666",
    ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
    sugerido = {"valor": ""}

    def _sugerir(*_args) -> None:
        # Propone el nombre del fichero mientras el usuario no lo cambie.
        if var_fichero.get() in ("", sugerido["valor"]):
            sugerido["valor"] = databases.suggest_filename(var_nombre.get()[: databases.NAME_MAX])
            var_fichero.set(sugerido["valor"])

    var_nombre.trace_add("write", _sugerir)
    resultado: dict = {}

    def _crear() -> None:
        nombre, fichero = var_nombre.get().strip(), var_fichero.get().strip()
        error = databases.validate_new(nombre, fichero)
        datos = {clave: var.get().strip() for clave, var in vars_ficha.items()}
        if not error and datos["birth_date"]:
            try:
                dt.date.fromisoformat(datos["birth_date"])
            except ValueError:
                error = "Fecha de nacimiento no válida (formato AAAA-MM-DD)."
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
        if any(datos.values()):
            # Import local: `repository` arrastra `pdf_parser` (ver nota de
            # cabecera sobre no retrasar la ventana de bienvenida).
            from analitix.repository import create_patient
            from analitix.textutils import join_full_name

            create_patient(
                con,
                {
                    "full_name": join_full_name(datos["nombre"], datos["apellidos"]),
                    "birth_date": datos["birth_date"],
                    "dni": datos["dni"],
                },
            )
        resultado["valor"] = ({"nombre": nombre, "fichero": fichero}, con)
        win.destroy()

    botones = ttk.Frame(body)
    botones.grid(row=6, column=0, sticky="e")
    ttk.Button(botones, text="Crear", command=_crear).pack(side="left", padx=(0, 6))
    ttk.Button(botones, text="Cancelar", command=win.destroy).pack(side="left")
    win.bind("<Escape>", lambda _e: win.destroy())
    _center(win)
    entry_nombre.focus_set()
    win.grab_set()
    parent.wait_window(win)
    return resultado.get("valor")


def _ask_name_and_file(parent: tk.Misc, titulo: str, fichero_inicial: str):
    """Nombre corto del paciente y nombre de la BD para añadir a la lista una
    BD que ya existe (`databases.add_existing_database`). Devuelve
    `(nombre, fichero)` válidos o `None` si se cancela."""
    win = tk.Toplevel(parent)
    win.title(titulo)
    win.transient(parent)
    win.resizable(False, False)
    body = ttk.Frame(win, padding=14)
    body.pack(fill="both", expand=True)
    ttk.Label(
        body, text=f"Nombre del paciente (para reconocerlo en la lista, máx. {databases.NAME_MAX}):"
    ).grid(row=0, column=0, sticky="w")
    var_nombre = tk.StringVar()
    entry_nombre = ttk.Entry(body, textvariable=var_nombre, width=44)
    entry_nombre.grid(row=1, column=0, sticky="we", pady=(2, 8))
    ttk.Label(body, text="Nombre de la base de datos:").grid(row=2, column=0, sticky="w")
    var_fichero = tk.StringVar(value=fichero_inicial)
    ttk.Entry(body, textvariable=var_fichero, width=44).grid(
        row=3, column=0, sticky="we", pady=(2, 10)
    )
    resultado: dict = {}

    def _aceptar(_event=None) -> None:
        nombre, fichero = var_nombre.get().strip(), var_fichero.get().strip()
        error = databases.validate_new(nombre, fichero)
        if error:
            messagebox.showerror("Analitix", error, parent=win)
            return
        resultado["valor"] = (nombre, fichero)
        win.destroy()

    botones = ttk.Frame(body)
    botones.grid(row=4, column=0, sticky="e")
    ttk.Button(botones, text="Añadir", command=_aceptar).pack(side="left", padx=(0, 6))
    ttk.Button(botones, text="Cancelar", command=win.destroy).pack(side="left")
    win.bind("<Return>", _aceptar)
    win.bind("<Escape>", lambda _e: win.destroy())
    _center(win)
    entry_nombre.focus_set()
    win.grab_set()
    parent.wait_window(win)
    return resultado.get("valor")


def _choose_database(root: tk.Tk):
    """Lista de bases de datos (gestor): abrir, crear, añadir una existente
    (copia de seguridad o de otro equipo), hacer copia de seguridad y
    borrar. Devuelve `(entrada, None)` para abrir una existente (se pide
    después su contraseña), `(entrada, con)` si se acaba de crear, o `None`
    para salir."""
    win = tk.Toplevel(root)
    win.title("Analitix — Bases de datos")
    win.resizable(False, False)
    set_app_icon(win)
    body = ttk.Frame(win, padding=14)
    body.pack(fill="both", expand=True)
    var_texto = tk.StringVar()
    ttk.Label(body, textvariable=var_texto).pack(anchor="w", pady=(0, 6))
    tree = ttk.Treeview(
        body, columns=("nombre", "fichero", "copia"), show="headings", height=8, selectmode="browse"
    )
    for col, texto, ancho in (
        ("nombre", "Paciente", 260),
        ("fichero", "Base de datos", 220),
        ("copia", "Última copia", 110),
    ):
        tree.heading(col, text=texto)
        tree.column(col, width=ancho)
    tree.pack(fill="both", expand=True)
    resultado: dict = {}
    botones_con_seleccion: list[ttk.Button] = []

    def _cargar(seleccionar: str | None = None) -> None:
        tree.delete(*tree.get_children())
        lista = databases.list_databases()
        for d in lista:
            copia = databases.last_backup(d["fichero"])
            tree.insert(
                "",
                "end",
                iid=d["fichero"],
                values=(d["nombre"], d["fichero"], copia.isoformat() if copia else "nunca"),
            )
        if lista:
            iid = seleccionar if seleccionar in tree.get_children() else lista[0]["fichero"]
            tree.selection_set(iid)
            tree.focus(iid)
        var_texto.set(
            "Elige la base de datos del paciente que quieres abrir:"
            if lista
            else "Todavía no hay ninguna base de datos. Crea una para empezar:"
        )
        for boton in botones_con_seleccion:
            boton.configure(state="normal" if lista else "disabled")

    def _seleccionada() -> str | None:
        seleccion = tree.selection()
        return seleccion[0] if seleccion else None

    def _abrir(_event=None) -> None:
        fichero = _seleccionada()
        if fichero:
            resultado["valor"] = (databases.find_database(fichero), None)
            win.destroy()

    def _nueva() -> None:
        creada = _create_database(win)
        if creada:
            resultado["valor"] = creada
            win.destroy()

    def _anadir() -> None:
        ruta = filedialog.askopenfilename(
            parent=win,
            title="Añadir una base de datos existente",
            filetypes=[("Base de datos de Analitix", "*.db"), ("Todos los ficheros", "*.*")],
        )
        if not ruta:
            return
        origen = Path(ruta)
        datos = _ask_name_and_file(
            win, "Analitix — Añadir base de datos", databases.suggest_filename(origen.stem)
        )
        if datos is None:
            return
        try:
            databases.add_existing_database(*datos, origen)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Analitix", f"No se pudo añadir: {exc}", parent=win)
            return
        logger.info("Base de datos existente añadida a la lista")
        _cargar(datos[1])

    def _copia() -> None:
        fichero = _seleccionada()
        if not fichero:
            return
        ruta = filedialog.asksaveasfilename(
            parent=win,
            title="Guardar copia de seguridad",
            initialfile=databases.backup_suggested_name(fichero),
            defaultextension=".db",
            filetypes=[("Base de datos de Analitix", "*.db")],
        )
        if not ruta:
            return
        try:
            databases.backup_database(fichero, Path(ruta))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Analitix", f"No se pudo copiar: {exc}", parent=win)
            return
        logger.info("Copia de seguridad hecha desde la lista de bases de datos")
        messagebox.showinfo(
            "Analitix",
            "Copia guardada. Sigue cifrada con la misma contraseña: guárdala en un lugar seguro.",
            parent=win,
        )
        _cargar(fichero)

    def _borrar() -> None:
        fichero = _seleccionada()
        if not fichero:
            return
        nombre = databases.find_database(fichero)["nombre"]
        if not messagebox.askyesno(
            "Borrar base de datos",
            f"¿Borrar la base de datos «{fichero}» ({nombre}) con TODOS sus datos?\n\n"
            "Se borra el fichero del equipo y no se puede deshacer. Las copias de seguridad "
            "que hayas hecho no se tocan.",
            icon="warning",
            parent=win,
        ):
            return
        confirmacion = simpledialog.askstring(
            "Borrar base de datos",
            f"Escribe el nombre de la base de datos ({fichero}) para confirmar:",
            parent=win,
        )
        if confirmacion is None or confirmacion.strip() != fichero:
            messagebox.showinfo("Analitix", "Cancelado: no se ha borrado nada.", parent=win)
            return
        try:
            databases.delete_database(fichero)
        except OSError as exc:
            messagebox.showerror("Analitix", f"No se pudo borrar: {exc}", parent=win)
            return
        logger.warning("Base de datos de paciente borrada desde la lista")
        _cargar()

    botones = ttk.Frame(body)
    botones.pack(fill="x", pady=(10, 0))
    boton_abrir = ttk.Button(botones, text="Abrir", command=_abrir)
    boton_abrir.pack(side="left")
    ttk.Button(botones, text="Nueva base de datos...", command=_nueva).pack(
        side="left", padx=(6, 0)
    )
    ttk.Button(botones, text="Añadir existente...", command=_anadir).pack(side="left", padx=(6, 0))
    ttk.Button(botones, text="Salir", command=win.destroy).pack(side="right")
    gestion = ttk.Frame(body)
    gestion.pack(fill="x", pady=(6, 0))
    boton_copia = ttk.Button(gestion, text="Copia de seguridad...", command=_copia)
    boton_copia.pack(side="left")
    boton_borrar = ttk.Button(gestion, text="Borrar...", command=_borrar)
    boton_borrar.pack(side="left", padx=(6, 0))
    botones_con_seleccion.extend((boton_abrir, boton_copia, boton_borrar))
    _cargar()
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
                messagebox.showerror(
                    "Analitix",
                    f"No se encuentra el fichero de la base de datos:\n{path}",
                    parent=root,
                )
                entrada = None
                continue
            password = ask_password(root, f"Contraseña de la base de datos «{entrada['nombre']}»:")
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
        body,
        text="Cargando Analitix…",
        bg="white",
        fg="#2c3e50",
        font=("Segoe UI", 18, "bold"),
    ).pack()
    tk.Label(
        body,
        text="Preparando la interfaz y los gráficos, un momento por favor.",
        bg="white",
        fg="#555555",
        font=("Segoe UI", 10),
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
