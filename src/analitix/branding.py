# ---------------------------------------------------------------------------
# Script: branding.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-09
# Última actualización: 2026-09-09
# ---------------------------------------------------------------------------
"""Icono de la aplicación y pantalla de bienvenida (splash screen)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from analitix.config import ICON_PATH, LOGO_PATH

# Tamaños típicos para icono de ventana/barra de tareas; Tk elige el más
# adecuado según el contexto (título de ventana, Alt+Tab, barra de tareas).
_ICON_SIZES = (16, 32, 48, 128)
SPLASH_MAX_SIZE = 260
SPLASH_WIDTH = 560

# Aviso legal/de uso mostrado en la pantalla de bienvenida (ver
# `show_splash`) — el usuario debe pulsar "Aceptar" para continuar, en cada
# arranque de la aplicación.
DISCLAIMER_TEXT = (
    "AVISO LEGAL Y DE USO\n\n"
    "Analitix es una aplicación de uso personal, creada para representar "
    "gráficamente los datos de tus propias analíticas de laboratorio con "
    "fines exclusivamente informativos y de seguimiento.\n\n"
    "Esta aplicación NO emite diagnósticos médicos, no sustituye la "
    "valoración de un profesional sanitario y no debe usarse como base "
    "para tomar decisiones de salud. La interpretación de cualquier "
    "resultado, gráfico o índice mostrado corresponde siempre a tu médico "
    "o al centro/hospital que te atiende, nunca a esta herramienta.\n\n"
    "El autor no se hace responsable del uso indebido de esta aplicación "
    "ni de las decisiones tomadas a partir de la información que muestra.\n\n"
    'Al pulsar "Aceptar" confirmas que has leído y entendido este aviso.'
)


def set_app_icon(window: tk.Misc) -> None:
    """Aplica `analitix_icon.png` como icono de `window` (y de sus hijos:
    `iconphoto(True, ...)` lo hereda toda ventana Toplevel posterior). Se
    generan varios tamaños a partir del PNG cuadrado de origen (1254x1254);
    Tk no reescala solo. Guarda la lista de `PhotoImage` en el propio widget
    para que no las recoja el recolector de basura (si se pierde la
    referencia de Python, el icono desaparece aunque Tk siga usándolo)."""
    base = Image.open(ICON_PATH)
    photos = [
        ImageTk.PhotoImage(base.resize((size, size), Image.Resampling.LANCZOS))
        for size in _ICON_SIZES
    ]
    window.iconphoto(True, *photos)
    window._analitix_icon_refs = photos  # type: ignore[attr-defined]


def ask_password(
    parent: tk.Misc, texto: str, repetir: bool = False, titulo: str = "Analitix"
) -> str | None:
    """Pide una contraseña en un diálogo modal propio (el de `simpledialog`
    era muy estrecho y cortaba nombres largos de base de datos): texto en
    varias líneas, márgenes amplios y, con `repetir`, las dos casillas en la
    misma ventana (antes eran dos diálogos y el segundo perdía el foco).
    Los errores (vacía, no coinciden) se muestran en la propia ventana.
    Devuelve la contraseña o `None` si se cancela."""
    win = tk.Toplevel(parent)
    win.title(titulo)
    win.transient(parent)
    win.resizable(False, False)
    body = ttk.Frame(win, padding=(24, 20))
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=texto, wraplength=380, justify="left").grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
    )
    campos = [("Contraseña", tk.StringVar())]
    if repetir:
        campos.append(("Repítela", tk.StringVar()))
    entries = []
    for fila, (etiqueta, var) in enumerate(campos, start=1):
        ttk.Label(body, text=etiqueta).grid(row=fila, column=0, sticky="w", pady=3)
        entry = ttk.Entry(body, textvariable=var, show="*", width=32)
        entry.grid(row=fila, column=1, sticky="we", padx=(10, 0), pady=3)
        entries.append(entry)
    error = ttk.Label(body, text="", foreground="#b00020", wraplength=380)
    error.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
    resultado: dict = {}

    def _aceptar(_event=None) -> None:
        valores = [var.get() for _etiqueta, var in campos]
        if not valores[0]:
            error.configure(text="La contraseña no puede estar vacía.")
        elif repetir and valores[0] != valores[1]:
            error.configure(text="Las contraseñas no coinciden.")
            entries[1].delete(0, "end")
            entries[1].focus_set()
        else:
            resultado["valor"] = valores[0]
            win.destroy()

    def _intro(event) -> None:
        # Intro en la primera casilla pasa a la segunda en vez de aceptar.
        if repetir and event.widget is entries[0]:
            entries[1].focus_set()
        else:
            _aceptar()

    botones = ttk.Frame(body)
    botones.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))
    ttk.Button(botones, text="Aceptar", command=_aceptar).pack(side="left", padx=(0, 6))
    ttk.Button(botones, text="Cancelar", command=win.destroy).pack(side="left")
    win.bind("<Return>", _intro)
    win.bind("<Escape>", lambda _e: win.destroy())
    win.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - win.winfo_reqwidth()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - win.winfo_reqheight()) // 3
    if parent.winfo_viewable():
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    else:  # ventana raíz oculta (al arrancar): centrada en la pantalla
        win.geometry(
            f"+{(win.winfo_screenwidth() - win.winfo_reqwidth()) // 2}"
            f"+{(win.winfo_screenheight() - win.winfo_reqheight()) // 3}"
        )
    win.lift()
    win.focus_force()
    entries[0].focus_set()
    win.grab_set()
    parent.wait_window(win)
    return resultado.get("valor")


def load_logo_photo(max_size: int) -> ImageTk.PhotoImage:
    """Carga `analitix_logo.png` reescalado (conserva proporción, nunca
    supera `max_size` px de ancho/alto) y listo para un `tk.Label(image=...)`
    o similar. Quien llama debe guardar la referencia devuelta (p. ej.
    `label.image = photo`) para que el recolector de basura no se la lleve
    mientras Tk la sigue usando."""
    logo = Image.open(LOGO_PATH)
    logo.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(logo)


def show_splash(root: tk.Tk) -> bool:
    """Muestra el logo y el aviso legal/de uso (`DISCLAIMER_TEXT`) en una
    ventana centrada de fondo blanco, en cada arranque de la aplicación.
    Bloquea con `root.wait_window` (no un `sleep`: Tk sigue procesando su
    bucle de eventos mientras tanto) hasta que el usuario pulsa "Aceptar" o
    cierra la ventana. Devuelve `True` solo si se aceptó — quien llama debe
    tratar `False` igual que si se hubiera cancelado el diálogo de
    contraseña (cerrar la aplicación sin continuar)."""
    accepted = False

    splash = tk.Toplevel(root)
    splash.title("Analitix")
    splash.resizable(False, False)
    splash.attributes("-topmost", True)
    splash.configure(bg="white")

    def _accept() -> None:
        nonlocal accepted
        accepted = True
        splash.destroy()

    splash.protocol("WM_DELETE_WINDOW", splash.destroy)

    photo = load_logo_photo(SPLASH_MAX_SIZE)
    logo_label = tk.Label(splash, image=photo, borderwidth=0, bg="white")
    logo_label.image = photo  # referencia viva
    logo_label.pack(pady=(24, 12))

    disclaimer_label = tk.Label(
        splash,
        text=DISCLAIMER_TEXT,
        bg="white",
        fg="#222222",
        font=("Segoe UI", 10),
        justify="center",
        wraplength=SPLASH_WIDTH - 60,
    )
    disclaimer_label.pack(padx=30, pady=(0, 20))

    tk.Button(
        splash,
        text="Aceptar",
        command=_accept,
        width=14,
        bg="#2c3e50",
        fg="white",
        activebackground="#34495e",
        activeforeground="white",
        relief="flat",
        font=("Segoe UI", 10, "bold"),
        cursor="hand2",
    ).pack(pady=(0, 24))

    splash.update_idletasks()
    width = max(splash.winfo_reqwidth(), SPLASH_WIDTH)
    height = splash.winfo_reqheight()
    x = (splash.winfo_screenwidth() - width) // 2
    y = (splash.winfo_screenheight() - height) // 2
    splash.geometry(f"{width}x{height}+{x}+{y}")

    root.wait_window(splash)
    return accepted
