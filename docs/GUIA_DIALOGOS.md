# Guía de diseño de diálogos y ventanas

Toda ventana o cuadro de diálogo nuevo de Analitix debe seguir estas
reglas, para que la aplicación se vea y se comporte igual en todas partes.
Si una ventana necesita saltarse alguna, explica el motivo en un comentario
junto al código.

## 1. Estructura: siempre `_new_dialog`

```python
dialog, body = self._new_dialog("Título del diálogo")
ttk.Label(body, text="Explicación breve...", wraplength=520, justify="left").pack(anchor="w", pady=(0, 6))
# ... contenido, SIEMPRE dentro de `body` ...
botones = ttk.Frame(body)
botones.pack(fill="x", pady=(PAD, 0))
ttk.Button(botones, text="Cancelar", command=dialog.destroy).pack(side="right")
ttk.Button(botones, text="Aceptar", bootstyle="primary", command=_aceptar).pack(side="right", padx=(0, 8))
self._center_dialog(dialog)
self.wait_window(dialog)  # solo si el diálogo devuelve un resultado
```

- `AnalitixApp._new_dialog(title, resizable=False)` crea la ventana:
  - modal (`transient` + `grab_set`);
  - sin redimensionar por defecto;
  - Escape cierra la ventana, igual que Cancelar.
  
  Devuelve `(dialog, body)`, donde `body` es un único `ttk.Frame` con
  margen `PAD`.
- **Todo el contenido va dentro de `body`, nunca directamente sobre el
  `tk.Toplevel`.** El fondo del `Toplevel` es el gris del sistema y no el
  del tema, así que un widget ttk colocado ahí se ve como un recuadro de
  otro color. Era el fallo de "Laboratorios incluidos" y de los dos
  diálogos de fusión.
- Los márgenes interiores ya los da `body`: no añadas `padding=PAD` a las
  etiquetas ni `padx=PAD` a cada fila. Para sangrar opciones dentro de un
  grupo (casillas, botones de opción), usa `padx=8`.
- `self._center_dialog(dialog)` se llama al final, con todo el contenido
  ya creado, para centrar la ventana sobre la principal.

## 2. Botones

- Todos en **una fila al pie** (`botones = ttk.Frame(body)`), alineados a
  la **derecha**.
- **Cancelar** va en el extremo derecho, con el estilo por defecto (sin
  `bootstyle`).
- La **acción principal** va a la izquierda de Cancelar, con
  `bootstyle="primary"` y `padx=(0, 8)`. Su texto es el verbo de lo que
  hace ("Aceptar", "Fusionar", "Guardar").
- Las **acciones secundarias** ("Marcar todos", "Restablecer") van a la
  izquierda de la fila, con `bootstyle="secondary-outline"`.
- Una acción **destructiva o irreversible** se confirma antes con
  `messagebox.askyesno(...)`, que explica qué se pierde.
- Diálogos **solo informativos** (fichas, avisos científicos): un único
  botón **Cerrar** a la derecha, con el estilo por defecto.

## 3. Textos

- Una explicación breve arriba, en lenguaje llano, con `wraplength=520` y
  `justify="left"`.
- Los avisos de interpretación clínica mantienen siempre la idea "apoyo
  informativo y de seguimiento, nunca un diagnóstico".
- Mensajes emergentes: `messagebox.showinfo/showwarning/showerror/askyesno`
  siempre con `parent=` (el diálogo o la ventana principal), para que
  salgan encima de ella y no detrás.

## 4. Widgets

- Siempre widgets **ttk**. Las únicas excepciones son `tk.Listbox` y
  `tk.Text`, que no tienen versión ttk; a estos hay que aplicarles
  `self._style_plain_widget(widget)` para que usen los colores del tema.
- Listas largas o texto extenso: con `ttk.Scrollbar`. Solo entonces tiene
  sentido `_new_dialog(..., resizable=True)`.

## 5. Privacidad

- Muestra solo los datos personales imprescindibles para la tarea. Por
  ejemplo, el selector de paciente activo enseña solo el nombre; la ficha
  completa está en la pestaña Pacientes.
- Ningún dato del paciente en el título de la ventana ni en el log (ver
  `logging_setup.py` en la documentación técnica).

## 6. Comprobar un diálogo nuevo

Sin capturas de pantalla: abre el diálogo con la ventana principal oculta
(`withdraw()`) y comprueba por introspección que `dialog.winfo_children()`
es un único `TFrame` y que los botones siguen el orden de §2.

## Estado actual

- Usan `_new_dialog` (revisado el 2026-10-01; antes, varios tenían
  etiquetas o botones directamente sobre la ventana):
  - "Seleccionar paciente activo";
  - "Laboratorios incluidos";
  - "Elegir paciente a conservar";
  - "Elegir nombre a conservar";
  - "Ficha del paciente";
  - "Acerca de este parámetro";
  - los avisos científicos de los paneles.
- **Excepción documentada: "Acerca de"**. Tiene una maquetación propia,
  centrada (logo, versión, autor), pero también va dentro de un único
  `ttk.Frame`.
