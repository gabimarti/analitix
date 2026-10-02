# Contribuir a Analitix

Gracias por el interés. Este proyecto nació para uso personal, pero está
abierto a cualquiera que quiera aportar algo — **no hace falta saber
programar**. Todo tipo de ayuda suma:

- **Pacientes y usuarios**: si usas (o probarías) la app con tus propios
  informes, tu experiencia de uso vale tanto como una revisión de código —
  qué se entiende mal, qué falta, qué gráfico o dato echas en falta para
  seguir tu evolución.
- **Profesionales de la salud** (laboratorio, medicina, enfermería...):
  ayuda a interpretar correctamente nombres de pruebas, unidades, rangos de
  referencia o abreviaturas del sector que el código pueda estar
  malinterpretando.
- **Desarrolladoras/es**: desde añadir soporte para el formato de PDF de
  otro laboratorio/hospital hasta arreglar un bug, mejorar el rendimiento o
  proponer una funcionalidad nueva. Los cambios de código deben mantener la
  suite automatizada (`python -m pytest`) en verde y explicar su propósito
  en el mensaje de commit o en la descripción del pull request.
- **Cualquiera**: reportar un error, sugerir una mejora de redacción en la
  documentación, o simplemente decir qué te gustaría que hiciera la
  aplicación.

> **Antes de contribuir, lee la
> [política de contribuciones](docs/POLITICA_CONTRIBUCIONES.md)**: las reglas
> obligatorias de **seguridad, privacidad e integridad** que se aplican a
> cualquier aportación, y los motivos por los que una contribución puede no
> aceptarse aunque funcione.

## Formas de participar

- **Escribe a [contact@analitix.slmail.me](mailto:contact@analitix.slmail.me)** (contacto preferente) para
  cualquier consulta sobre la aplicación, si prefieres comentarlo antes de
  abrir nada formal o para acordar el envío privado de un PDF de muestra.
- **Pregunta o propón una idea en el foro público**, [Discussions](https://github.com/gabimarti/analitix/discussions):
  para dudas de uso, ideas o comentarios que puedan servir a más gente.
- **Abre un issue** describiendo el problema, la idea o la pregunta.
- **Envía un pull request** si ya tienes un cambio de código o
  documentación, **contra la rama `develop`** (no `main`). `main` contiene
  solo la última versión publicada; `develop` se fusiona en `main` al
  publicar cada versión (ver la documentación técnica, §8.1).
- También me encontrarás en [GitHub](https://github.com/gabimarti) y en
  [X/Twitter](https://x.com/gmarti).

Si tu cambio añade o modifica una ventana o un cuadro de diálogo, sigue la
[guía de diseño de diálogos](docs/GUIA_DIALOGOS.md) para que toda la
aplicación se vea igual.

## Sobre añadir soporte para otro laboratorio/hospital

El reconocimiento de cada centro/laboratorio (etiquetas de
cabecera, secciones, marcado de fuera de rango...) vive en un perfil externo
`.toml` en `src/analitix/data/parser_profiles/`, no embebido en
`src/analitix/pdf_parser.py` — ver `parser_profiles.py` y la sección
correspondiente de `docs/DOCUMENTACION_TECNICA.md`. Hoy hay perfiles para el
**Consorci Sanitari del Maresme / Hospital de Mataró** (con motor de parseo
completo, probado contra varias plantillas suyas a lo largo de los años),
para el **Hospital Universitari Germans Trias i Pujol (HUGTIP)** (probado
contra 4 informes reales cubriendo 2 variantes de plantilla), para
**Synlab Diagnósticos Globales**, para **Quirón** y para **Laboratorio
Echevarne**. Si tu laboratorio usa un formato distinto:

1. Abre un issue contándolo — con eso ya es útil, no hace falta que sepas
   programar.
2. Si puedes, comparte 1-2 PDF de ejemplo (ver el aviso de privacidad más
   abajo) para poder desarrollar y verificar el soporte contra casos reales
   en vez de adivinar un formato a ciegas. Si tu centro usa una gramática de
   resultado parecida a la ya soportada (marcador de nota delante de cada
   fila, o un rango de referencia al final de la línea), puede bastar con un
   `.toml` nuevo, sin tocar el motor de parseo.
3. Si prefieres intentarlo tú mismo/a, incluso sin usar ningún asistente de
   IA: `docs/GUIA_NUEVO_PERFIL_PARSER.md` explica paso a paso cómo sacar el
   texto del PDF, identificar las etiquetas de cabecera y rellenar un
   `.toml` nuevo, con `docs/plantilla_perfil.toml` como plantilla comentada
   de partida.

**Aviso sobre los nombres de las pruebas (alias)**: el identificador
interno de cada prueba (`canonical_id`) se deriva del nombre del parámetro
tal como aparece en el PDF; `catalog.canonical_id_for` no traduce nada por
sí solo, solo normaliza acentos y mayúsculas y aplica los alias de
`src/analitix/data/test_aliases.csv` (que hoy ya cubren Mataró, HUGTIP,
Synlab/Eurofins, Quirón y Echevarne, en catalán y castellano). Si tu centro
nombra un parámetro existente con otra palabra u otro idioma, la primera
importación creará un `canonical_id` nuevo en vez de unirse al histórico —
es esperable. Ejecuta `scripts\alias_audit.bat` para que proponga las
equivalencias, **revísalas** y aplícalas desde "🔗 Normalizar pruebas" o
con el CSV. Procedimiento, riesgos de una fusión equivocada y cómo
revertirla: `docs/MANUAL_USUARIO.md` §2.19.1; detalles para
desarrolladores: `docs/DOCUMENTACION_TECNICA.md`, apartado "Alias de
pruebas: diseño, riesgos y mantenimiento".

## Pruebas automatizadas

Las pruebas están en `tests/` y no forman parte del runtime de Analitix. Se
instalan las dependencias de desarrollo y se ejecutan así desde la raíz:

```text
python -m pip install -r requirements-dev.txt
python -m pytest
```

Además, GitHub Actions ejecuta automáticamente la suite en cada `push` y
pull request mediante `.github/workflows/tests.yml`. Si el workflow falla,
hay que reproducir primero el fallo localmente antes de fusionar el cambio.

En Windows, `scripts\run_tests.bat` automatiza la preparación de
`venv-tests` y la ejecución de la suite. `scripts\update_main.bat` sirve
para actualizar el checkout principal tras una fusión; se detiene si detecta
cambios versionados locales.

Los casos deben usar datos sintéticos y bases de datos temporales. No se
aceptan PDF reales, nombres, identificadores, fechas de nacimiento ni
resultados de salud en el repositorio. El workflow
`.github/workflows/privacy.yml` (`scripts/check_privacy.py`) lo comprueba en
cada `push` y pull request: falla si se versiona un fichero de datos
(`.pdf`, `.db`, `.xlsx`, `.csv`…) o un DNI/NIE con letra de control válida.
Para DNI sintéticos usa el número `00000000` (`00000000T`) o una letra
inválida (`00000000A`). Para cambios del parser, cubre tanto
la nueva estructura como al menos una estructura ya soportada; para cambios
de base de datos, verifica también que una base temporal se pueda abrir y
que la migración sea compatible.

La documentación técnica contiene el mapa de cobertura y el procedimiento
manual complementario.

## ⚠️ Privacidad: nunca compartas datos de salud reales

Este proyecto trata informes de laboratorio, es decir, **datos de salud**.
Al reportar un problema o compartir un PDF de ejemplo:

- **No subas tus informes reales** a un issue o pull request público.
- Si necesitas ilustrar un problema con un PDF, **anonimízalo primero**
  (tacha nombre, DNI, NHC, fecha de nacimiento, dirección — cualquier dato
  que identifique a la persona) o, mejor aún, recréalo con datos
  ficticios que reproduzcan el mismo formato/estructura.
- Si prefieres compartir un PDF real sin anonimizar para que se pueda
  depurar con precisión, hazlo **en privado**: escribe a
  [contact@analitix.slmail.me](mailto:contact@analitix.slmail.me) (nunca en un issue público) y
  acordaremos cómo enviarlo de forma segura.

## Licencia

Al contribuir, aceptas que tu aportación se publique bajo la misma licencia
del proyecto, [GNU GPLv3](LICENSE).
