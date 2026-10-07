# Guía de diseño de la interfaz

Normas de aspecto y comportamiento para toda la interfaz de Analitix:
pantallas (pestañas de los menús), cuadros de diálogo y ventanas. Toda
pantalla o ventana nueva, y todo cambio en una existente, debe seguirlas,
para que la aplicación se vea y se comporte igual en todas partes. Si algo
necesita saltarse una norma, explica el motivo en un comentario junto al
código y añádelo a «Excepciones» al final de esta guía.

Toda la interfaz está en `src/analitix/gui.py`. Antes de escribir
maquetación a mano, busca si ya hay un helper para ello (§2); si un mismo
patrón aparece en más de dos sitios, conviértelo en helper y documéntalo
aquí.

## 1. Principios

- **Lo mismo se hace igual en todas partes.** Dos pantallas con la misma
  función (p. ej. Evolución y Comparativa, o dos paneles clínicos) tienen
  la misma estructura, los mismos márgenes y los mismos anchos.
- **Alineación a la izquierda.** Títulos, etiquetas, listas y botones de
  una columna empiezan en el mismo borde izquierdo.
- **Nada ensancha una columna sin querer.** Un texto largo se parte en
  líneas (`wraplength`) en vez de empujar la maquetación.
- **Colores del tema, siempre.** Nunca colores fijos en widgets: los
  `bootstyle` de §5, y `_style_plain_widget` para los widgets clásicos de Tk.
- **Comprobar con medidas, no a ojo** (§9).

## 2. Constantes y helpers

| Elemento | Uso |
| --- | --- |
| `PAD = 12` | Margen exterior estándar (px) de pantallas y diálogos. |
| `LIST_COLUMN_CHARS = 38` | Ancho de la lista de la columna izquierda; fija el ancho de toda la columna. |
| `self._new_dialog(título)` | Crea cualquier cuadro de diálogo (§7). |
| `self._center_dialog(dialog)` | Centra el diálogo sobre la ventana principal. |
| `self._same_width(b1, b2, ...)` | Mismo ancho para un grupo de botones (§6). |
| `self._list_column(left, texto, height=...)` | Etiqueta + lista de la columna izquierda (§4). |
| `self._fixed_column(left)` | Columna izquierda sin lista, con el mismo ancho (§4). |
| `self._scrollable_frame(padre)` | Zona desplazable para listas de casillas. |
| `self._checkbox_tree(tree)` + `self._sync_checks(tree)` | Tabla (`ttk.Treeview`) con casillas ☐/☑ para marcar varias filas (§8). |
| `self._style_plain_widget(w)` | Colores del tema para `tk.Listbox`/`tk.Text`. |
| `self._build_disclaimer_button(...)` | Botón «⚠️ Aviso e información científica» de los paneles. |

## 3. Estructura de una pantalla

Cada pestaña es un `ttk.Frame` dentro de `self.content`, registrado en
`_show_page` y con su entrada en el menú (`_build_menu`).

- **Título** de la pantalla: `ttk.Label(..., font=("Segoe UI", 14, "bold"))`,
  con `padx=PAD`.
- **Subtítulo de sección**: `font=("Segoe UI", 11, "bold")`.
- **Texto explicativo**: `bootstyle="secondary"`, `wraplength=700`,
  `justify="left"`.
- **Grupos de opciones** (Configuración, Exportar): `ttk.Labelframe` con
  `padding=PAD`.
- Márgenes: `padx=PAD` respecto al borde de la ventana y `pady=PAD` arriba
  y abajo del bloque principal. Entre elementos de un mismo bloque, 4–8 px.
- La barra de estado inferior (paciente activo y laboratorios) es común a
  toda la aplicación: esa información no se repite dentro de una pantalla.

## 4. Pantallas de lista + gráfico (Análisis y Paneles clínicos)

Evolución, Comparativa y todos los paneles clínicos tienen una **columna
izquierda** (lista y botones) y el gráfico a la derecha. Si la lista permite
marcar varias opciones (Comparativa), son casillas en una columna
`_fixed_column` (§8), con el mismo ancho:

```python
left = ttk.Frame(body)
left.pack(side="left", fill="y")
self.list_x = self._list_column(left, "Índice (⚠ = ...):", height=10)
ttk.Button(left, text="Ver evolución", bootstyle="primary", command=...).pack(pady=(8, 4), fill="x")
ttk.Button(left, text="ℹ️ ¿Qué es este índice?", bootstyle="info", command=...).pack(fill="x")
```

- La etiqueta y la lista **siempre** con `_list_column`. La etiqueta se
  parte al ancho de la lista, de modo que la columna mide siempre
  `LIST_COLUMN_CHARS` y etiqueta, lista y botones quedan alineados. Antes,
  una etiqueta más larga que la lista (Comparativa, paneles) ensanchaba la
  columna: la lista quedaba centrada, con margen a la izquierda, y los
  botones salían más anchos que en Evolución.
- Si la columna no tiene lista (solo botones), llama a
  `self._fixed_column(left)` para que mida lo mismo.
- Botones de la columna con `fill="x"`: la acción principal arriba
  (`bootstyle="primary"`, `pady=(8, 4)`) y «ℹ️ ¿Qué es...?» debajo
  (`bootstyle="info"`). Así todos tienen el ancho de la columna.
- En la lista, «⚠» delante de lo que alguna vez estuvo fuera de rango, con
  la marca explicada en la etiqueta.
- Paneles clínicos, de arriba abajo: título, estado, subtítulo «Último ...
  disponible», botón de aviso científico (`_build_disclaimer_button`),
  resumen (`tk.Text` de solo lectura) y el bloque lista + gráfico.

## 5. Colores (`bootstyle`)

| Estilo | Uso |
| --- | --- |
| `primary` | Acción principal de una pantalla o diálogo. |
| `success` | Acciones que crean o guardan datos (importar, guardar analítica, exportar a Excel). |
| `info` | Información y ayuda («ℹ️ ¿Qué es...?», editar ficha, textos de estado). |
| `warning` | Avisos y acciones delicadas pero reversibles (aviso científico, cambiar contraseña, reimportar todo). |
| `danger` | Acciones destructivas (eliminar, vaciar). Con `-outline` si comparten fila con otras. |
| `secondary` / `secondary-outline` | Acciones secundarias y textos explicativos. |
| *(sin estilo)* | Cancelar, Cerrar, Actualizar. |

### 5.1 Colores de estado (gráficos, Resumen, PDF)

Paleta apta para daltonismo, definida solo en `charts.py` (colores de
Okabe & Ito; ver el comentario junto a las constantes):

| Constante | Color | Uso |
| --- | --- | --- |
| `COLOR_NORMAL` | verde azulado `#009E73` | Dentro de rango; «se acerca al rango» en Qué ha cambiado. |
| `COLOR_ALTO` | bermellón `#D55E00` | Por encima del rango; «se aleja del rango»; texto de lo alterado (`COLOR_ALTERADO`). |
| `COLOR_BAJO` | azul `#0072B2` | Por debajo del rango (misma polaridad que el mapa de calor). |
| `COLOR_BRUSCO` | granate `#882255` | Cambio brusco dentro de rango. |

Reglas:

- **El color nunca va solo**: alto/bajo llevan ▲/▼ (`SIMBOLO_ESTADO`) y
  texto; en Qué ha cambiado, ✗/✓; lo alterado en listas, ⚠.
- **No usar emojis de color** (🔴/🟠/🟢) para estados: no se distinguen con
  daltonismo.
- Nada de parejas verde/rojo o rojo/naranja como única diferencia. Un
  color nuevo se toma de Okabe-Ito o de las paletas de Paul Tol, y si va
  como texto sobre blanco, con contraste ≥ 4.5:1.
- **Intensidad, no tono, para la gravedad**: una desviación leve usa el
  mismo color aclarado (`charts._tint`) con contorno del color pleno; el
  color pleno queda para las grandes. El texto (etiquetas, ▲/▼) va siempre
  en color pleno, por contraste.
- Un objetivo del médico, si existe, **sustituye** al rango en el gráfico y
  se rotula siempre «Objetivo indicado por su médico».

## 6. Botones

- **Los botones de un mismo grupo tienen el mismo ancho**: el del texto más
  largo (`self._same_width(boton1, boton2, ...)`). Un grupo son los botones
  de una misma fila y del mismo lado (los de la izquierda y los de la
  derecha de una fila son grupos distintos), o los apilados de un mismo
  bloque (p. ej. Excel y CSV, o los tres informes PDF). Los apilados en una
  columna con `fill="x"` ya cumplen la norma.
- Texto: un verbo que diga qué hace («Guardar», «Fusionar», «Ver
  evolución»). Termina en «...» si abre un diálogo o pide confirmación
  antes de actuar.
- Una acción **destructiva o irreversible** se confirma antes con
  `messagebox.askyesno(...)`, que explica qué se pierde.

## 7. Cuadros de diálogo y ventanas

### 7.1 Estructura: siempre `_new_dialog`

```python
dialog, body = self._new_dialog("Título del diálogo")
ttk.Label(body, text="Explicación breve...", wraplength=520, justify="left").pack(anchor="w", pady=(0, 6))
# ... contenido, SIEMPRE dentro de `body` ...
botones = ttk.Frame(body)
botones.pack(fill="x", pady=(PAD, 0))
boton_cancelar = ttk.Button(botones, text="Cancelar", command=dialog.destroy)
boton_cancelar.pack(side="right")
boton_ok = ttk.Button(botones, text="Aceptar", bootstyle="primary", command=_aceptar)
boton_ok.pack(side="right", padx=(0, 8))
self._same_width(boton_cancelar, boton_ok)
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
  otro color.
- Los márgenes interiores ya los da `body`: no añadas `padding=PAD` a las
  etiquetas ni `padx=PAD` a cada fila. Para sangrar opciones dentro de un
  grupo (casillas, botones de opción), usa `padx=8`.
- `self._center_dialog(dialog)` se llama al final, con todo el contenido
  ya creado.

### 7.2 Botones del pie

- Todos en **una fila al pie**, alineados a la **derecha**.
- **Cancelar** en el extremo derecho, sin `bootstyle`.
- La **acción principal** a la izquierda de Cancelar, con
  `bootstyle="primary"` y `padx=(0, 8)`, y el mismo ancho que Cancelar
  (`_same_width`).
- Las **acciones secundarias** («Marcar todos», «Desmarcar todo») a la
  izquierda de la fila, con `bootstyle="secondary-outline"` y el mismo
  ancho entre ellas.
- Diálogos **solo informativos** (fichas, avisos científicos): un único
  botón **Cerrar** a la derecha, sin estilo.

## 8. Textos, widgets y privacidad

- Lenguaje llano y frases cortas. Explicación breve arriba, con
  `wraplength` (520 en diálogos, 700 en pantallas) y `justify="left"`.
- Los avisos de interpretación clínica mantienen siempre la idea «apoyo
  informativo y de seguimiento, nunca un diagnóstico».
- Mensajes emergentes: `messagebox.showinfo/showwarning/showerror/askyesno`
  siempre con `parent=` (el diálogo o la ventana principal), para que
  salgan encima de ella y no detrás.
- Siempre widgets **ttk**. Las únicas excepciones son `tk.Listbox` y
  `tk.Text`, que no tienen versión ttk; a estos se les aplica
  `self._style_plain_widget(widget)`.
- Listas largas o texto extenso: con `ttk.Scrollbar`. Solo entonces tiene
  sentido `_new_dialog(..., resizable=True)`.
- **Para elegir varias opciones de una lista larga, casillas
  (`ttk.Checkbutton`) dentro de `self._scrollable_frame(padre)`**, nunca
  una selección múltiple con Ctrl: un solo clic sin Ctrl desmarca todo lo
  elegido. Si la lista es larga, añade «Desmarcar todo» (y, si tiene
  sentido, un atajo como «Marcar alterados»).
- **Tablas en las que se marcan varias filas**: `self._checkbox_tree(tree)`
  al crearlas y `self._sync_checks(tree)` al final de cada recarga. Un clic
  marca o desmarca la fila (☐/☑) y `tree.selection()` sigue devolviendo las
  marcadas; la flecha ▸ de las filas desplegables solo despliega.
- Informes PDF: siempre en A4.
- Muestra solo los datos personales imprescindibles para la tarea (p. ej.
  el selector de paciente activo enseña solo el nombre). Ningún dato del
  paciente en el título de la ventana ni en el log.

## 9. Comprobar un cambio de interfaz

Sin capturas de pantalla: construye `AnalitixApp` con una base de datos
temporal y la ventana oculta (`withdraw()` + `update_idletasks()`), y
comprueba por introspección:

- columnas izquierdas: `left.winfo_reqwidth()` igual en todas las pantallas
  e igual al de su lista;
- grupos de botones: el mismo `cget("width")`;
- diálogos: `dialog.winfo_children()` es un único `TFrame` y los botones
  siguen el orden de §7.2.

Ejecuta además la suite completa (`python -m pytest`).

## Excepciones

- **«Acerca de»**: maquetación propia, centrada (logo, versión, autor),
  pero también dentro de un único `ttk.Frame`.
- **Informes PDF en Exportar**: usan `danger`/`danger-outline` por el rojo
  habitual de los PDF, no porque sean destructivos.
- **Entrada manual**: «Quitar fila seleccionada» (izquierda) y «Guardar
  analítica» (derecha) son grupos distintos y conservan su ancho natural.
