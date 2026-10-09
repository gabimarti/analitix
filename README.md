<p align="center">
  <img src="src/analitix/res/analitix_logo.png" width="160" alt="Analitix">
</p>

<h1 align="center">Analitix</h1>

<p align="center">
  <a href="https://github.com/gabimarti/analitix/actions/workflows/tests.yml"><img src="https://github.com/gabimarti/analitix/actions/workflows/tests.yml/badge.svg" alt="Estado de los tests"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Versión de Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-blue?style=flat-square" alt="Licencia"></a>
  <img src="https://img.shields.io/badge/plataforma-Windows-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Plataforma">
  <img src="https://img.shields.io/badge/datos-100%25%20locales-2ea44f?style=flat-square" alt="Datos 100% locales">
</p>

---

Aplicación de escritorio (Windows, compatible best-effort con Linux) que lee
tus propios informes de laboratorio en PDF desde `informes_analiticas/`,
guarda sus resultados en una base de datos SQLite cifrada en tu propio
ordenador (SQLCipher, sin ningún servidor) y te permite ver
cómo evolucionan tus valores en el tiempo frente a sus rangos de referencia.

¿Por qué existe? Te lo cuento en [**Por qué nació Analitix**](docs/HISTORIA.md).
Novedades de cada versión en el [registro de cambios](CHANGELOG.md).

**Qué hace:**
- Extrae automáticamente los resultados de los PDF de laboratorio soportados
  (ver [«Formatos de informe soportados»](#formatos-de-informe-soportados))
  y los guarda cifrados en local.
- Muestra gráficos de evolución y comparativas de cada prueba frente a su
  rango de referencia, con el último valor destacado y colores aptos para
  daltonismo (el estado se indica también con ▲/▼, nunca solo con color).
- Calcula índices y paneles clínicos informativos (p. ej. riesgo
  cardiovascular, función renal, función hepática) a partir de fórmulas y
  umbrales publicados, citando siempre su fuente.
- Exporta a Excel/CSV/PDF para llevarte tus propios datos (ver un
  [informe PDF de ejemplo](docs/ejemplos/informe_alterados_ficticio.pdf)
  con datos ficticios).

**Qué NO hace:**
- No emite diagnósticos ni sustituye la valoración de un profesional
  sanitario.
- No envía tus datos a ningún sitio: todo el procesamiento es local. La
  **única conexión a internet** es la comprobación opcional de versiones
  nuevas (menú Ayuda → Buscar actualizaciones..., o al iniciar si lo
  activas en Configuración), que solo consulta en GitHub el número de la
  última versión publicada.
- No reconoce automáticamente el formato de cualquier laboratorio — solo los
  que tienen un perfil de análisis creado (ver más abajo); el resto queda
  marcado para revisión manual, sin inventar ni adivinar resultados.

> ## ⚠️ Uso personal, no médico
>
> Analitix está pensado para **uso personal**: te ayuda a llevar tu propio
> seguimiento de analíticas, no a diagnosticarte. Cualquier valor fuera de
> rango, gráfico, índice o "riesgo" que muestre la app es solo orientativo —
> **la última palabra la tiene siempre un profesional sanitario colegiado**,
> con el contexto clínico completo. Ante cualquier duda sobre un resultado,
> consulta con tu médico o con el laboratorio que emitió el informe. Más
> detalle en el aviso que muestra la propia app al arrancar y en el manual
> de usuario.
>
> El uso de Analitix es **responsabilidad exclusiva de quien la utiliza**: lee el
> [aviso legal y exención de responsabilidad](DISCLAIMER.md).

<p align="center">
  <img src="docs/images/evolucion.png" width="49%" alt="Gráfico de evolución de una prueba en Analitix">
  <img src="docs/images/mapa_calor.png" width="49%" alt="Mapa de calor del historial en Analitix">
</p>
<p align="center">
  <img src="docs/images/resumen_cambios.png" width="49%" alt="Qué ha cambiado respecto al informe anterior">
  <img src="docs/images/panel_riesgo_cv.png" width="49%" alt="Panel clínico de riesgo cardiovascular">
</p>

> Capturas con datos **ficticios** ("PACIENTE FICTICIO" y valores inventados, no reales).

## Documentación

- [`docs/MANUAL_USUARIO.md`](docs/MANUAL_USUARIO.md) — instalación,
  actualización y guía de uso de cada pestaña de la aplicación.
- [`docs/DOCUMENTACION_TECNICA.md`](docs/DOCUMENTACION_TECNICA.md) —
  arquitectura, librerías, esquema de base de datos y descripción de cada
  módulo, pensada para quien quiera modificar o ampliar el código.
- [`docs/referencias_medicas/`](docs/referencias_medicas/) — fuentes
  científicas (artículos, guías clínicas) que respaldan los cálculos e
  índices clínicos de la app, y de las ideas todavía no implementadas.

## Inicio rápido

**Sin conocimientos técnicos (Windows):** instala Analitix con
`Analitix-Setup-<versión>.exe`, que no necesita Python. El asistente pregunta
dónde guardar tus datos y crea ahí una carpeta `Analitix` con
`informes_analiticas` (tus PDF) y `data` (la base de datos cifrada).
Detalles, aviso de Windows SmartScreen, actualización y desinstalación en el
[manual de usuario](docs/MANUAL_USUARIO.md) §1.1.

**Desde el código fuente:** antes de ejecutar nada, coloca todos tus informes de laboratorio en PDF
dentro de la carpeta `informes_analiticas/` — preferiblemente en una
subcarpeta propia dentro de ella (p. ej. `informes_analiticas/tu_nombre/`),
sobre todo si vas a guardar ahí los informes de más de una persona.

```
scripts\install_windows.bat
scripts\run_windows.bat
```

La primera vez se pide crear una contraseña maestra que cifra toda la base
de datos (`data\analitix.db`); sin ella los datos no son legibles y no hay
forma de recuperarla si se olvida. Detalles completos en el manual de
usuario enlazado arriba.

## Contribuir

Este proyecto está abierto a cualquiera que quiera aportar algo, **no hace
falta saber programar**: pacientes y usuarios contando su experiencia de
uso, profesionales de la salud ayudando a interpretar pruebas/unidades,
gente reportando errores o simplemente con ideas. Ver
[`CONTRIBUTING.md`](CONTRIBUTING.md) para las distintas formas de
participar (incluye un aviso importante sobre privacidad si vas a
compartir un PDF de ejemplo) y la
[política de contribuciones](docs/POLITICA_CONTRIBUCIONES.md) con las reglas
de seguridad, privacidad e integridad que debe cumplir toda aportación.
Para cualquier consulta sobre la aplicación, escribe a
[contact@analitix.slmail.me](mailto:contact@analitix.slmail.me).

Autor: Gabriel Marti — [gabimarti.github.io](https://gabimarti.github.io/).

## Formatos de informe soportados

El reconocimiento de cada centro/laboratorio (etiquetas de cabecera,
secciones, marcado de fuera de rango...) vive en un perfil externo `.toml`
en `src/analitix/data/parser_profiles/`, no embebido en el código — ver
`docs/DOCUMENTACION_TECNICA.md` para el detalle. Hoy hay soporte real para:

- **Consorci Sanitari del Maresme / Hospital de Mataró**, con motor de
  parseo completo probado contra varias variantes de plantilla suyas a lo
  largo de los años.
- **Hospital Universitari Germans Trias i Pujol (HUGTIP)**, probado contra
  4 informes reales cubriendo 2 variantes de plantilla (una compacta en
  catalán, otra bilingüe catalán/castellano) — puede seguir sin generalizar
  a variantes no vistas todavía.
- **Synlab / SNB (Eurofins) Diagnósticos Globales**.
- **Quirón**, con dos gramáticas de fila distintas dentro del mismo
  documento (resultados de laboratorio propio y resultados interfaced de
  un proveedor externo).
- **Laboratorio Echevarne**.

PDF de otros laboratorios u hospitales probablemente no se reconozcan
correctamente — la app no falla ni pierde datos en ese caso (quedan
marcados `status="review"` para revisión manual, sin crear ningún paciente
ni informe a partir de un formato no reconocido, o se pueden introducir a
mano en la pestaña "Entrada manual"), pero no se extraen sus resultados
automáticamente.

El diseño del parser está pensado para admitir un centro nuevo (si su
gramática de fila de resultado es compatible con la ya soportada) añadiendo
solo un `.toml`, sin tocar el motor de parseo ni romper los centros ya
soportados — ver [`CONTRIBUTING.md`](CONTRIBUTING.md) si quieres ayudar a
añadir soporte para otro laboratorio, y la sección `parser_profiles.py` de
`docs/DOCUMENTACION_TECNICA.md` como punto de partida técnico.
[`docs/GUIA_NUEVO_PERFIL_PARSER.md`](docs/GUIA_NUEVO_PERFIL_PARSER.md)
explica cómo crear ese `.toml` paso a paso sin necesitar ningún asistente de
IA, con [`docs/plantilla_perfil.toml`](docs/plantilla_perfil.toml) como
plantilla de partida.

## Licencia

Software libre bajo los términos de la [GNU General Public License v3.0](LICENSE).
Ver también el [aviso legal y exención de responsabilidad](DISCLAIMER.md) y la
[política de seguridad](SECURITY.md) para informar de vulnerabilidades.

## Desarrollo

Las pruebas automatizadas están aisladas en `tests/` y no se ejecutan al
iniciar la aplicación. Para preparar el entorno de desarrollo y ejecutarlas:

```
python -m pip install -r requirements-dev.txt
python -m pytest
```

La suite usa únicamente datos sintéticos y bases temporales. Consulta
[`docs/DOCUMENTACION_TECNICA.md`](docs/DOCUMENTACION_TECNICA.md) para el
alcance de la cobertura y [`CONTRIBUTING.md`](CONTRIBUTING.md) para las
reglas de contribución.

En Windows también se puede ejecutar `scripts\run_tests.bat`, que crea o
actualiza el entorno local `venv-tests` sin afectar al entorno de producción.
Para actualizar el checkout principal después de fusionar cambios en GitHub,
ejecuta `scripts\update_main.bat` desde esa carpeta. El script solo hace
`pull --ff-only` si no hay cambios versionados pendientes.

Para generar el instalador de Windows (`dist\Analitix-Setup-<versión>.exe`)
ejecuta `scripts\build_windows.bat` (requiere Inno Setup 6: `winget install
JRSoftware.InnoSetup`); usa su propio entorno `venv-build`. El ejecutable se
compila del mismo código fuente: ver
[`docs/DOCUMENTACION_TECNICA.md`](docs/DOCUMENTACION_TECNICA.md) §8.
