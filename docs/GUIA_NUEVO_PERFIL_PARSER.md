# Guía: añadir un perfil de reconocimiento para un laboratorio nuevo

Esta guía explica, paso a paso y **sin necesitar ningún asistente de IA**,
cómo crear el fichero `.toml` que enseña a Analitix a reconocer los informes
de un laboratorio/hospital nuevo. Está pensada para quien tenga PDF de un
centro que la app todavía no reconoce (aparecen marcados "pendiente de
revisión" al importarlos) y quiera intentar darles soporte a mano.

No hace falta ser programador/a, pero sí hay que sentirse cómodo/a editando
texto plano y siguiendo instrucciones de línea de comandos. Si en algún punto
te atascas, abre un issue contando hasta dónde has llegado — no hace falta
completar la guía entera para que sea útil (ver `CONTRIBUTING.md`).

**Antes de nada, el aviso de privacidad de siempre**: los PDF que uses para
esto son datos de salud reales tuyos o de alguien. Trabaja con ellos en tu
propio ordenador; **nunca los subas a un issue, pull request o cualquier otro
sitio público**, ni copies datos reales (nombre, DNI, NHC, fecha de
nacimiento, valores de analítica) al fichero `.toml` ni a ningún sitio que
vaya a acabar en el repositorio. El `.toml` solo necesita el **texto de las
etiquetas** del informe (p. ej. `"Nom del pacient:"`), que es texto de la
plantilla del laboratorio, no un dato personal.

## 0. Qué es este fichero y cuándo hace falta uno

Cada centro/laboratorio tiene su propio perfil `.toml` en
`src/analitix/data/parser_profiles/`, que le dice al motor de parseo
(`pdf_parser.py`) qué buscar en ese informe concreto: cómo se llama la
etiqueta "Nombre del paciente", si la fila de un resultado lleva un marcador
especial delante, etc. El motor de parseo en sí (la lógica que separa
nombre/valor/unidad/rango de cada línea) es el mismo para todos los
perfiles — normalmente **no hace falta tocar código Python**, solo describir
la plantilla de tu centro en el `.toml`.

Esto solo funciona si la **gramática de la fila de resultado** de tu centro
se parece a alguna de las ya soportadas:

- **Estilo "Maresme"**: cada fila de resultado lleva un marcador `"(n)"`
  delante (p. ej. `"(1) Glucosa sèrum 108 mg/dL 74 - 106"`) **o** el rango de
  referencia va entre paréntesis al final (`"Glucosa sèrum 108 mg/dL
  ( 74 - 106 )"`).
- **Estilo "HUGTIP"**: sin marcador ni paréntesis — la fila simplemente
  termina en un rango suelto (`"Glucosa sèrum 108 mg/dL 74 - 106"`).

Si tu centro encaja en alguno de los dos, sigue esta guía. Si las filas de
resultado tienen una estructura totalmente distinta (por ejemplo, valores en
columnas por posición en vez de en una línea de texto seguida), hace falta
motor de parseo nuevo — eso sí requiere tocar `pdf_parser.py`, mejor abrir un
issue contándolo con un par de líneas de ejemplo.

## 1. Sacar el texto plano del PDF

Analitix ya usa `pdfplumber` para leer los PDF (viene instalado si ya
ejecutaste `scripts\install_windows.bat`). Puedes reutilizar la misma función
que usa la app para volcar el texto línea a línea, sin tener que instalar
nada nuevo. Desde la carpeta del proyecto, con el entorno virtual activado:

**Windows:**
```
venv\Scripts\python -c "import sys; sys.path.insert(0, 'src'); from analitix.pdf_parser import extract_lines; [print(l) for l in extract_lines(r'ruta\a\tu\informe.pdf')]" > texto_extraido.txt
```

**Linux:**
```
venv/bin/python3 -c "import sys; sys.path.insert(0, 'src'); from analitix.pdf_parser import extract_lines; [print(l) for l in extract_lines('ruta/a/tu/informe.pdf')]" > texto_extraido.txt
```

Esto crea `texto_extraido.txt` con el contenido del PDF, una línea por fila.
Ábrelo con cualquier editor de texto y léelo de arriba a abajo: así es
exactamente como lo va a ver el motor de parseo (no necesariamente parecido a
cómo se ve el PDF renderizado — el orden y los saltos de línea a veces
sorprenden).

**Recuerda**: `texto_extraido.txt` tiene datos reales dentro. Bórralo cuando
termines, o al menos no lo dejes en una carpeta que vaya a subirse a ningún
sitio (el `.gitignore` del proyecto ya evita que un fichero `.txt` suelto en
la raíz se suba por descuido, pero mejor no confiar solo en eso).

## 2. Identificar la cabecera del informe

En `texto_extraido.txt`, busca las líneas que traen estos datos y apunta el
**texto de la etiqueta tal cual aparece, con mayúsculas/minúsculas y
acentos**, pero no el valor:

| Dato | Ejemplo de etiqueta que podrías ver |
|---|---|
| Nombre completo del paciente | `Nombre:`, `Paciente:`, `Nom i cognoms:` |
| Nº de petición/informe | `Nº Petición:`, `Petició:` |
| Fecha de nacimiento | `Fecha de nacimiento:`, `Data naixement:` |
| DNI/NIF | `DNI:`, `NIF:` |
| Nº de historia clínica (NHC) | `NHC:`, `Nº Historia:` |
| Fecha de la petición/solicitud | `Fecha de petición:`, `Solicitud:` |
| Fecha de validación del informe | `Fecha de validación:`, `Finalització:` |
| Fecha de la muestra/recepción | `Fecha de extracción:`, `Recepció:` |

No todos los centros traen los 8 campos — con nombre y una fecha cualquiera
ya es utilizable (el resto queda vacío, sin más).

**Ojo con las líneas que comparten varias etiquetas** (muy típico en
informes densos, p. ej. `"Nombre: Juan Pérez  Sexo: H  NHC: 12345"`): apunta
también la etiqueta que va DESPUÉS de la que te interesa (aquí, `"Sexo:"`),
la necesitarás en el paso 4 para que el valor de `"Nombre:"` no se coma el
resto de la línea.

## 3. Decidir la "firma" del perfil

La firma es cómo Analitix reconoce que un PDF es de tu centro sin haberlo
abierto todavía. Dos formas, usa la que te resulte más fiable:

- **Por texto de marca** (`requires_any`): una o varias cadenas que
  aparezcan en TODOS los informes de tu centro y en ningún otro — el nombre
  del hospital/laboratorio suele bastar. Es la opción más simple.
- **Por etiqueta de cabecera propia** (`header_label_any`): si el nombre del
  centro no es fiable (algún PDF antiguo lo trae con la codificación rota,
  por ejemplo), se puede reconocer en su lugar por si aparece alguna de sus
  propias etiquetas de cabecera (de las que ya vas a definir en el paso 2).

## 4. Rellenar la plantilla

Copia `docs/plantilla_perfil.toml` (en esta misma carpeta) a
`src/analitix/data/parser_profiles/tu_centro.toml` (nombre corto, sin
espacios ni acentos, todo minúsculas — p. ej. `hospital_de_ejemplo.toml`) y
rellena cada campo con lo que apuntaste en los pasos 2-3. El fichero de
plantilla trae comentarios explicando cada campo y ejemplos reales de los
dos perfiles ya soportados.

Puntos que se suelen pasar por alto:

- El campo `priority` decide el orden en que se prueban los perfiles cuando
  hay varios — uno con una firma muy específica (el nombre exacto del
  centro) puede ir con prioridad baja (se prueba antes); dejar el valor por
  defecto (`100`) casi siempre vale.
- Los patrones de `header_labels` son expresiones regulares, no texto
  literal — algunos caracteres (`.`, `(`, `)`, `/`) tienen significado
  especial y hay que escaparlos con `\` si quieres que se busquen tal cual.
  Si no conoces regex, la forma más segura es copiar el patrón de un campo
  parecido de un perfil ya existente (`consorci_sanitari_maresme.toml` o
  `hugtip.toml`, en la misma carpeta) y cambiar solo las palabras.
- Si tu laboratorio pone la traducción de cada etiqueta en otro idioma junto
  a la original (p. ej. `"Nom / Nombre:"`), fíjate cómo lo resuelven los
  perfiles existentes con `(?:\s*/\s*[A-Za-zÀ-ÿ.º ]+)?` en vez de escribir
  cada traducción una a una.
- Si alguna determinación sale **sin rango en su propia línea** (el rango
  va debajo, o no hay), por defecto se descarta: usa `unranged_result_re` y
  `following_range_labels` (explicados en la plantilla).
- Si la extracción rompe siempre igual alguna línea (p. ej. el nombre sale
  pegado al valor, `"sèrum23 U/L"`), repárala con `[[line_substitutions]]`
  (`pattern` regex + `replacement`), como en `consorci_sanitari_maresme.toml`.
- Si tu centro usa el **mismo nombre en sangre y en orina** (p. ej. "Glucosa"
  en la sección de orina), añade la tabla `[section_name_suffixes]` con el
  nombre exacto de la sección y la palabra a añadir (`"orina"`), como en
  `consorci_sanitari_maresme.toml`; si no, las dos pruebas se mezclarían.

## 5. Probar el perfil contra tu PDF real

Sin escribir nada en la base de datos todavía, puedes comprobar qué
extraería Analitix de tu PDF con este script (cámbialo por la ruta real):

**Windows:**
```
venv\Scripts\python -c "import sys; sys.path.insert(0, 'src'); from pathlib import Path; from analitix.pdf_parser import parse_report; r = parse_report(Path(r'ruta\a\tu\informe.pdf')); print('Perfil detectado:', r['format_id']); print('Cabecera:', {k: (v is not None) for k, v in r['header'].items()}); print('Nº de resultados:', len(r['results']))"
```

Si `format_id` sale `unknown`, la firma del paso 3 no se está reconociendo —
revisa que el texto coincida exactamente (mayúsculas/acentos aparte, la
comparación ya ignora acentos) con lo que hay en el PDF real.

Si `format_id` ya es el tuyo pero `Cabecera` sale con varios `False` o
`Nº de resultados` es 0, revisa los patrones uno a uno. Para ver el detalle
de un resultado concreto (sin volcar todo el informe), añade al final del
mismo script algo como:

```python
for x in r['results'][:5]:
    print(x['raw_name'], '|', x['value_num'], x['unit'], '|', x['ref_low'], x['ref_high'])
```

(recuerda: esta salida tiene datos reales de la persona del informe — no la
copies a ningún sitio fuera de tu ordenador).

## 6. Cuando ya funciona

- Ejecuta la suite de tests (`python -m pytest`, o `scripts\run_tests.bat`
  en Windows) para comprobar que no has roto nada de lo ya soportado.
- Si sabes programar un poco, añade uno o dos casos a
  `tests/test_pdf_parser.py` con **datos inventados** (nunca los reales del
  PDF que usaste) que reproduzcan la gramática de tu centro — mira
  `test_parse_lines_with_hugtip_profile` como ejemplo de cómo se hace.
- Abre un pull request con el `.toml` nuevo (y los tests, si los añadiste).
  El PDF real que usaste para desarrollarlo **no se sube nunca** — solo el
  `.toml`, que no contiene ningún dato personal.

## Y si el formato no encaja con ninguna gramática conocida

Si tras leer `texto_extraido.txt` ves que la fila de resultado no se parece
a ninguno de los dos estilos del paso 0 (por ejemplo, cada resultado ocupa
varias líneas sin ningún patrón claro, o los valores van alineados en
columnas por posición horizontal en vez de seguidos en la misma línea de
texto), esta guía no llega tan lejos — hace falta motor de parseo nuevo, no
solo un `.toml`. Abre un issue contando qué has encontrado (con 4-5 líneas
de ejemplo del formato, sin datos personales) y seguimos desde ahí.
