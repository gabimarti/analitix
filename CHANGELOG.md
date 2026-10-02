# Registro de cambios

Todos los cambios relevantes de la aplicación Analitix se documentan en este
fichero. Solo recoge cambios del programa (lo que nota quien lo usa); los de
la operativa de desarrollo o la gestión del repositorio no se anotan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el proyecto usa [Versionado Semántico](https://semver.org/lang/es/) (ver
[`docs/DOCUMENTACION_TECNICA.md`](docs/DOCUMENTACION_TECNICA.md) §8.2).

## [Sin publicar]

### Añadido

- «Acerca de» muestra el correo de contacto del proyecto (contact@analitix.slmail.me).
- Rango personal opcional en el gráfico de Evolución (interruptor «Mostrar mi rango personal»): tu propio rango «normal», calculado con tus analíticas anteriores dentro de rango y la variación biológica publicada (método de Coşkun 2021).

## [0.10.0] - 2026-10-01

### Cambiado

- Todos los cuadros de diálogo siguen el mismo diseño: fondo del tema (antes, algunos mostraban textos con fondo distinto al de la ventana), botones al pie a la derecha, centrados sobre la ventana principal y Escape para cerrar. Directrices en `docs/GUIA_DIALOGOS.md`.
- Todos los gráficos de evolución (Evolución, Comparativa, paneles clínicos e informe PDF) aplican el mínimo de analíticas de Configuración: por debajo muestran un aviso y con una sola analítica no se dibuja el gráfico, solo el valor. Antes ese mínimo solo agrupaba la lista de Evolución y podían aparecer gráficos de un único punto.
- El registro `analitix.log` ya no guarda el nombre de los PDF con aviso o error (suele ser el del paciente), sino el inicio de su huella MD5.

### Añadido

- Índice TyG (triglicéridos-glucosa) en el panel de glucosa, solo como tendencia y sin umbral.
- Banda de variación esperable (RCV) en el último punto de los gráficos de Evolución y de los paneles.
- Análisis → Laboratorios incluidos...: elegir de qué laboratorios salen los datos de gráficos, paneles clínicos, Resumen e informe PDF (por defecto, todos), para series más coherentes; el filtro activo se indica siempre en la barra inferior y en el PDF. La exportación Excel/CSV no se filtra.
- Resumen en texto bajo cada gráfico de evolución (pantalla, paneles clínicos y PDF): en cuántas analíticas ha estado dentro del rango y cómo está la última respecto a su límite.
- «Qué ha cambiado» indica si cada cambio es probablemente real o cabe en la variación esperable (valor de referencia del cambio, RCV), con variación biológica de estudios publicados citados; no se valora entre laboratorios distintos.
- Menú Ayuda con enlaces al manual de usuario, la documentación técnica, las referencias científicas y el registro de cambios.
- Política de seguridad (`SECURITY.md`) con el procedimiento para informar de vulnerabilidades de forma privada.
- Cada Release incluye `SHA256SUMS.txt` y una atestación de procedencia del instalador para verificar la descarga (ver `SECURITY.md`).
- Controles automáticos del repositorio: comprobación de datos personales y secretos en cada cambio, auditoría de vulnerabilidades de dependencias (`pip-audit`, también semanal) y actualizaciones con Dependabot.
- Procedimiento de ramas: `main` contiene solo la última versión publicada y el desarrollo se hace en `develop` (ver `CONTRIBUTING.md`).

## [0.9.0] - 2026-09-30

Primera versión pública.

### Añadido

- Importación automática de informes de laboratorio en PDF desde una carpeta elegible, con opción de incluir subcarpetas e importación incremental por huella del fichero.
- Laboratorios y centros soportados mediante perfiles `.toml` externos: **Consorci Sanitari del Maresme / Hospital de Mataró**, **Hospital Universitari Germans Trias i Pujol (HUGTIP)**, **Synlab / SNB (Eurofins) Diagnósticos Globales**, **Quirón** y **Laboratorio Echevarne**.
- Los PDF de formato no reconocido quedan marcados para revisión manual: no se crea ningún paciente ni informe y no se adivina ningún resultado.
- Gestión de pacientes: ficha editable (sexo, DNI, CIP, NHC y NHC secundario, tabaquismo), fusión de duplicados y eliminación.
- Paciente activo único para toda la aplicación, elegido al iniciar en un diálogo que solo muestra el nombre.
- Entrada manual de analíticas, con notas opcionales por informe.
- Gráficos de evolución con banda de referencia, tendencia lineal con proyección, variación porcentual, tooltips y forma del punto según el laboratorio.
- Comparativa de dos parámetros en paneles apilados con eje temporal compartido.
- Resumen tipo semáforo del último informe, con columnas de variación y tendencia (%/año), y vista «Qué ha cambiado» con barras divergentes.
- Mapa de calor del historial: parámetros frente a analíticas, coloreado según la posición dentro del rango de referencia.
- Paneles clínicos informativos con la fuente citada: riesgo cardiovascular, salud hepática (De Ritis, APRI, FIB-4), función renal (KDIGO, urea/creatinina, deterioro agudo), hemograma (NLR, PLR, LMR, Mentzer, aviso de linfocitosis sostenida), metabolismo del hierro, inflamación (PCR + VSG), ácido úrico, calcio corregido, glucosa media estimada (eAG) y tiroides.
- Fichas descriptivas de cada parámetro e índice, en lenguaje llano y con detalle técnico.
- Normalización de pruebas entre laboratorios y plantillas mediante alias, con detalle por laboratorio, salvaguardas que bloquean o avisan de fusiones dudosas y herramienta de auditoría de alias.
- Exportación a Excel y CSV, e informes PDF de seguimiento (completo o solo parámetros alterados) con portada y gráficos.
- Explorador de la base de datos en modo solo lectura y detección de informes huérfanos.
- Instalador para Windows que no necesita Python, con carpeta de datos elegible (también desde Configuración) y autocomprobación `--self-test`.
- Comprobación opcional de versiones nuevas en GitHub (menú Ayuda o al iniciar).
- Aviso legal de uso personal y no médico, que hay que aceptar en cada arranque, y documento [`DISCLAIMER.md`](DISCLAIMER.md).

### Seguridad

- Base de datos SQLite cifrada con SQLCipher mediante una contraseña maestra, que se puede cambiar sin perder datos.
- Todo el procesamiento es local. La única conexión a internet es la comprobación opcional de versiones, que solo consulta el número de la última versión publicada.
- Los registros de actividad no contienen datos de pacientes ni resultados.
- Se neutralizan las fórmulas en las exportaciones a Excel y CSV.
- Se rechazan las contraseñas con un formato reservado por el motor de cifrado.

## Desarrollo previo a la versión 0.9.0

Resumen de los cambios hechos durante el desarrollo, antes de la primera
versión publicada.

<details>
<summary>Ver el historial de desarrollo (septiembre de 2026)</summary>

### 2026-09-30

#### Añadido

- Ejecutable e instalador para Windows (PyInstaller + Inno Setup), por usuario, en español y catalán.
- Carpeta de datos elegida al instalar; si no hay ninguna, se usa `Documentos\Analitix`.
- Autocomprobación del ejecutable con `--self-test`.
- Versión 0.9.0 visible en el título de la ventana y en «Acerca de».
- Configuración muestra la ubicación de la base de datos e incluye el botón «Abrir carpeta de datos».
- En la versión instalada se puede cambiar la ubicación de los datos (copia sin borrar el origen y reinicio).
- Casilla «Incluir subcarpetas» en Importar, activada por defecto y recordada.
- Alias en dos capas: los de la aplicación y los del usuario, que tienen prioridad.
- Flujo de GitHub Actions que compila, prueba y publica una versión al etiquetar `vX.Y.Z`, con las notas tomadas de este registro de cambios.
- Comprobación opcional de versiones nuevas (Ayuda → Buscar actualizaciones..., o al iniciar si se activa en Configuración).
- Normalizar pruebas: cada prueba se despliega en una fila por nombre y laboratorio.
- Aviso legal (`DISCLAIMER.md`), historia del proyecto y este registro de cambios.

#### Cambiado

- Un único paciente activo para toda la aplicación, elegido al iniciar en un diálogo que solo muestra el nombre; la pestaña Pacientes queda para ver y editar fichas.
- Las acciones de GitHub se actualizan a versiones con Node 24.
- Documentación actualizada: instalación paso a paso, SmartScreen, actualización, desinstalación, compilación y numeración de versiones.

#### Corregido

- El instalador respeta el parámetro `/DATADIR` aunque exista una instalación previa.

#### Seguridad

- La neutralización de fórmulas en las exportaciones se aplica también al valor en texto de cada resultado.

### 2026-09-29

#### Añadido

- Se bloquea la fusión de pruebas que aparecen en un mismo informe.
- Aviso al fusionar pruebas con distinto LOINC o con unidades distintas.
- Columna «Laboratorios» en Normalizar pruebas.
- La auditoría de alias marca las propuestas conflictivas e incluye una sección de grupos mixtos.
- Nueva opción de perfil `section_name_suffixes`: las pruebas de orina del Maresme se separan de sus homónimas en sangre.
- Fichas descriptivas específicas para los parámetros en orina.

#### Corregido

- Los hematíes de orina ya no entran en el panel de hemograma ni en el índice de Mentzer.

#### Cambiado

- Documentación actualizada (manual, documentación técnica, guía y plantilla de perfil).

### 2026-09-28

#### Añadido

- Nuevas opciones de perfil: `line_substitutions`, `unranged_result_re` y `following_range_labels`.
- Rangos de referencia por franjas de edad, resueltos con la fecha de nacimiento del paciente.

#### Corregido

- Los valores con comparador pegado (`<5`, `>90`) se guardan como texto y no generan pruebas falsas.
- Se elimina el asterisco inicial de las determinaciones calculadas.
- Se ignora «37 ºC» en la línea de LDH.
- Valores de AST y GGT leídos incorrectamente por espacios superpuestos en la plantilla antigua.
- Los límites sueltos sin `<` o `>` se interpretan como mínimo o máximo según el contexto.
- Se recuperan los rangos cortados tras el guion en la plantilla antigua del Maresme.
- Se recuperan filas sin rango en su línea (Synlab, HUGTIP).

#### Cambiado

- Documentación actualizada (valores censurados, rangos por edad, nuevas opciones de perfil).

### 2026-09-25

#### Añadido

- Reconocimiento de los informes firmados por SNB/Eurofins en el perfil de Synlab.
- Nuevos datos guardados: sexo y CIP autonómico del paciente, y huella MD5 y número de asistencia de cada informe.
- Ficha de paciente editable, con datos de tabaquismo.
- Laboratorio de origen por informe: forma del punto según el laboratorio en Evolución y columna en la ficha.
- Mapa de calor del historial (fuera de rango, todos o por panel).
- Subpestaña «Qué ha cambiado» en Resumen, con barras divergentes medidas en anchos de rango.
- Herramienta `alias_audit` y alias adicionales entre laboratorios.
- Ordenación por columnas en Normalizar pruebas.
- Ventana de carga con logo y barra de progreso animada.
- Capturas de la documentación generadas con un paciente ficticio.

#### Corregido

- Se usa la fecha de recepción de la muestra en varias plantillas; nuevo orden de prioridad de fechas: muestra, petición, validación.
- Las fusiones manuales de pacientes ya no se deshacen al reimportar.
- El «NºHistoria» de Synlab ya no se guarda como NHC.
- El NHC principal ya no se repite como NHC secundario.
- Separados los parámetros en porcentaje de los recuentos absolutos.
- Unidades equivalentes reconocidas y conversión de PCR y albúmina.
- Las listas de pruebas muestran el nombre más frecuente de cada una.

#### Cambiado

- La huella de fichero pasa a MD5; los PDF ya importados se reprocesan una vez.

### 2026-09-24

#### Añadido

- Perfiles de parser para Synlab, Quirón y Laboratorio Echevarne.
- Nuevas capacidades del motor: rango entre corchetes, resultados con orden invertido, relleno de puntos y tolerancia de extracción configurable.
- El registro de importación muestra el perfil detectado en cada fichero.
- Alias entre laboratorios para urea, creatinina, urato, plaquetas, neutrófilos y linfocitos.

#### Corregido

- El punto como separador de millares se distingue del separador decimal.
- Se reconoce la fecha de muestra aunque aparezca después de los resultados.
- Se limpian los caracteres nulos que aparecían en el texto extraído de algunos PDF.

#### Cambiado

- Arranque más rápido: la interfaz se carga después del aviso legal.
- Documentación revisada, con enlaces cruzados y descripción solo del estado actual.

#### Seguridad

- Se rechazan las contraseñas con formato de clave reservado por el motor de cifrado.
- Eliminada una dependencia declarada que no se usaba.

### 2026-09-23

#### Añadido

- Paciente activo para Entrada manual: no se recuerda entre sesiones y el formulario queda deshabilitado si no hay ninguno.
- Campo de notas opcional en Entrada manual.
- Columna «Tendencia» en Resumen, con flecha y magnitud en %/año.
- Segunda variante de plantilla bilingüe en el perfil HUGTIP.
- Guía y plantilla comentada para crear un perfil de parser nuevo.

#### Corregido

- Fondo mal integrado en el diálogo «Acerca de».
- Fechas en catalán con elisión («d'abr.»).
- Las líneas de método y las notas a pie ya no se registran como resultados.
- Se leía un valor erróneo cuando el nombre de la prueba contenía un dígito suelto.

#### Cambiado

- README renovado: logo, insignias, apartados «Qué hace» y «Qué NO hace», y aviso de uso personal.

#### Seguridad

- El registro de las entradas manuales no incluye el contenido de las notas.

### 2026-09-22

#### Cambiado

- `run_windows.bat` inicia la aplicación sin dejar abierta la ventana de consola.

### 2026-09-21

#### Añadido

- Aviso informativo de linfocitosis sostenida en Hemograma.
- Paneles de Calcio corregido, Glucosa media estimada (eAG) y Tiroides (TSH + T4L).
- Gráfico combinado de glucosa y eAG.
- Pestaña «Resumen» tipo semáforo del último informe.
- Exportación a PDF en dos modalidades (completo y alterados), con portada, logo, pie de página y tablas separadas por rango.
- Botón «Aviso e información científica» en todos los paneles clínicos.

#### Cambiado

- Eliminada la descripción repetida bajo los gráficos; los botones de información tienen ahora el mismo estilo.
- Los gráficos de varios paneles tienen desplazamiento vertical y se reducen ligeramente cuando falta espacio.

#### Corregido

- Texto cortado y espacio excesivo en los gráficos de dos paneles.
- Los parámetros con un solo valor ya no generan gráfico en el PDF.

### 2026-09-18

#### Añadido

- Panel de Salud hepática (De Ritis, APRI, FIB-4), con la edad calculada en la fecha de cada informe.
- Panel de Función renal (clasificación KDIGO, cociente urea/creatinina, aviso de deterioro agudo).
- Panel de Hemograma (NLR, PLR, LMR, índice de Mentzer, categoría de VCM).
- Paneles de Metabolismo del hierro, Inflamación (PCR + VSG) y Ácido úrico.
- Nuevo menú «Paneles clínicos», separado de «Análisis».
- La pantalla de bienvenida incluye un aviso legal que hay que aceptar obligatoriamente.
- Nombre del paciente visible en los paneles clínicos.
- Fichas descriptivas en lenguaje llano con detalle técnico, y nuevas referencias médicas.

#### Cambiado

- Ventana principal más grande; el diálogo de información se ajusta al contenido y tiene desplazamiento.

#### Corregido

- La ficha de «saturació» describía la saturación de oxígeno en lugar de la de transferrina.
- Corregida la autoría de una referencia bibliográfica.

### 2026-09-17

#### Añadido

- Perfiles de parser por centro en ficheros `.toml` externos, con detección automática del perfil.
- Soporte para informes del HUGTIP.
- Fechas con el mes en catalán.
- Aviso de posible paciente duplicado en formatos sin fecha de nacimiento.

#### Corregido

- Los formatos no reconocidos ya no crean pacientes fantasma.
- Reconocido el título «Reedició Informe».
- Se aceptan rangos con límite inferior negativo.
- Ya no aparecen falsos informes huérfanos al trabajar con varias subcarpetas.
- Los gráficos se vacían al cambiar de paciente.

#### Cambiado

- Documentación actualizada: aviso de uso personal y lista de centros reconocidos.

### 2026-09-15

#### Añadido

- Suite de pruebas automatizadas con pytest.

#### Cambiado

- Las citas de los índices lipídicos se trasladan del código a las fichas descriptivas.

### 2026-09-10

#### Añadido

- Panel de Riesgo cardiovascular: LDL por Friedewald, Castelli I/II, TG/HDL y umbrales ATP III, con las fuentes citadas.
- Fichas descriptivas de los índices lipídicos.
- Carpeta pública `docs/referencias_medicas/` con las fuentes científicas.
- Selector de carpeta en la pestaña Importar.

#### Cambiado

- Riesgo cardiovascular: título de página, aviso sobre la población de origen de los umbrales y aclaración del alcance temporal.

### 2026-09-09

#### Añadido

- Pestaña Entrada manual para registrar analíticas sin PDF.
- Normalizar pruebas: fusión de variantes de nombre con alias permanente.
- Fusión de pacientes y columna con el número de informes.
- NHC secundario, con migración automática del esquema.
- Detección y eliminación de informes huérfanos.
- Icono de la aplicación y pantalla de bienvenida.
- Navegación por menú y diálogo «Acerca de».
- Margen vertical y variación porcentual en los gráficos.
- Fichas descriptivas de los parámetros.
- Licencia GPLv3.

#### Corregido

- Resultados duplicados al reimportar PDF renombrados.
- El NHC anterior ya no se pierde al reimportar.
- Lectura del valor y del rango del colesterol HDL (el límite es un mínimo).
- Exportación a Excel con columnas vacías.

#### Seguridad

- El registro de actividad ya no incluye el nombre del paciente.
- Se neutralizan las fórmulas en las exportaciones a Excel y CSV.

### 2026-09-08

#### Añadido

- «Reimportar todo (forzar)», eliminación de paciente y vaciado completo de la base de datos.
- Barra de progreso durante la importación.
- Registro de actividad en fichero rotativo, sin datos de pacientes.
- Explorador de la base de datos en modo solo lectura.
- Las vistas de análisis y exportación se bloquean hasta seleccionar un paciente.
- Emparejamiento de pacientes por DNI o NHC cuando no se reconoce el nombre.

#### Corregido

- Los ficheros marcados para revisión se reintentan automáticamente, sin duplicar datos.
- Reconocida una etiqueta de nombre alternativa, también con ruido previo en el texto.
- Fechas de la plantilla antigua (año de dos dígitos) que hacían fallar Evolución.

### 2026-09-07

#### Añadido

- Primera versión: importación de informes PDF de laboratorio con soporte de varias plantillas del Consorci Sanitari del Maresme.
- Base de datos SQLite cifrada con SQLCipher y contraseña maestra.
- Catálogo de pruebas con identificador canónico y CSV de alias editable.
- Escaneo incremental de la carpeta de informes por huella del fichero.
- Pestañas Importar, Pacientes, Evolución, Comparativa y Exportar (Excel/CSV).
- Gráficos con rango de referencia, etiquetas en los puntos fuera de rango y tooltips.
- Línea de tendencia con proyección a 90 días y aviso de pocos datos, con umbral configurable.
- Pestaña Configuración: carpeta de informes, cambio de contraseña, avisos y estadísticas.
- Marcado para revisión de los PDF sin paciente o sin resultados reconocidos.
- Documentación técnica y manual de usuario.

#### Corregido

- Caracteres duplicados en los valores fuera de rango de algunos PDF.
- Banda de referencia cortada y texto de tendencia superpuesto al gráfico.
- Nombres con guion o con espacio generaban pacientes duplicados.

</details>
