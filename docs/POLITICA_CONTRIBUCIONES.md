# Política de contribuciones: seguridad, privacidad e integridad

Analitix trata **datos de salud**, que el RGPD considera una categoría
especial (art. 9). Por eso cada contribución, sea código, documentación,
un perfil de laboratorio o un dato clínico, se valora con tres criterios:
**seguridad**, **privacidad** e **integridad**.

Esta política dice qué es obligatorio, cómo se comprueba y qué no se
acepta. No sustituye a [`CONTRIBUTING.md`](../CONTRIBUTING.md), que explica
cómo participar, ni a [`SECURITY.md`](../SECURITY.md), que explica cómo
informar de una vulnerabilidad: los complementa.

> **En una frase:** los datos de quien usa Analitix no salen nunca de su
> equipo, nada de lo que entra en el repositorio identifica a nadie, y
> todo lo que la aplicación muestra tiene una fuente verificable y nunca es
> un diagnóstico.

---

## 1. Privacidad

### Principios

1. **Todo en local.** Analitix procesa y guarda los datos solo en el
   equipo del usuario, en una base de datos cifrada (SQLCipher).
   - Su única conexión a internet es la comprobación opcional de versiones
     nuevas, que no envía ningún dato.
   - No hay telemetría, analítica de uso, cuentas ni servicios en la nube.
2. **Mínimo imprescindible.** Cada pantalla, exportación o registro
   muestra solo los datos personales necesarios para su tarea.
3. **El usuario decide.** Ningún dato se exporta, comparte ni envía sin
   una acción explícita suya.

### Obligatorio en toda contribución

- **Ningún dato real en el repositorio.** Esto incluye PDF de informes,
  nombres, DNI/NIE, NHC, CIP, fechas de nacimiento, direcciones,
  resultados, capturas de pantalla con datos y nombres de fichero reales.
  - Tests, documentación, capturas y ejemplos usan siempre **datos
    sintéticos**, como "PACIENTE FICTICIO".
  - Los DNI de prueba usan el número `00000000` o una letra de control
    inválida.
- **Ninguna conexión de red nueva.** No se añaden llamadas a internet,
  APIs externas, servicios de IA, CDN ni descargas automáticas. Una
  conexión nueva solo se plantea si es imprescindible, opcional y
  desactivable, y sin enviar ningún dato. Se discute antes en una issue.
- **Registro (`analitix.log`) sin datos personales.**
  - Solo identificadores internos, huellas de fichero y mensajes de
    estado.
  - Nunca nombres, DNI, nombres de PDF ni valores de resultados.
- **Exportaciones explícitas.** Cualquier salida de datos (Excel, CSV, PDF)
  la inicia el usuario y queda en la ubicación que él elige.
- **Sin datos personales en los títulos de las ventanas.** El selector de
  paciente muestra solo el nombre (ver
  [`GUIA_DIALOGOS.md`](GUIA_DIALOGOS.md)).

### Al pedir ayuda o compartir un caso

- No adjuntes informes reales en issues ni en pull requests: son públicos.
- Si hace falta un PDF para reproducir un problema, anonimízalo (sustituye
  todos los datos identificativos y, si puedes, también los valores) o
  recréalo con datos ficticios. Un PDF real solo se comparte en privado
  y previo acuerdo.
- **No envíes datos reales a herramientas de IA** (asistentes de código,
  chats) para preparar una contribución. Si usas una, trabaja solo con
  datos sintéticos.

### Cómo se comprueba

- `scripts/check_privacy.py` y el workflow *Privacy and secrets*, en cada
  push y pull request. Bloquean ficheros de datos (`.pdf`, `.db`, `.xlsx`,
  `.csv`…) y DNI/NIE con letra válida.
- Revisión manual de cada pull request, sobre todo de capturas, ejemplos y
  mensajes de log.

---

## 2. Seguridad

### Principios

1. **Proteger los datos en reposo.** La base de datos está cifrada y la
   contraseña la elige el usuario; nada debe debilitar ese cifrado.
2. **No confiar en la entrada.** Un PDF es contenido externo: se lee como
   texto, nunca se ejecuta ni se interpreta como código.
3. **Cadena de suministro controlada.** Cada dependencia y cada Action es
   código de terceros que se ejecuta con acceso a los datos del usuario o
   al proceso de publicación.

### Obligatorio en toda contribución

- **No debilitar el cifrado** ni guardar datos fuera de la base cifrada.
  Tampoco se guardan ni se registran la contraseña ni la clave.
- **SQL solo en `repository.py` y siempre con parámetros.** Nunca se
  construyen consultas concatenando datos de entrada. Si hace falta
  interpolar algo, como el nombre de una tabla, se valida antes contra una
  lista cerrada.
- **Nada de `eval`, `exec`, `pickle` ni deserialización de datos no
  confiables.** Tampoco se ejecutan comandos con contenido procedente de
  un PDF o del usuario.
- **Ningún secreto en el repositorio**: claves, tokens ni contraseñas,
  tampoco de prueba. Push protection, secret scanning y gitleaks lo
  vigilan.
- **Dependencias nuevas, solo si son imprescindibles.**
  - Antes de añadir una, comprueba que no basten la biblioteca estándar o
    lo ya instalado.
  - Justifica por qué hace falta.
  - Comprueba que su licencia es compatible con la GPL-3.0 y que está
    mantenida.
  - Las GitHub Actions se fijan por hash de commit, y solo se permiten las
    de GitHub, las de creadores verificados y las de la lista explícita.
- **Las vulnerabilidades se notifican en privado**, nunca en una issue
  pública (ver [`SECURITY.md`](../SECURITY.md)).

### Cómo se comprueba

- `pip-audit`, también cada semana: vulnerabilidades conocidas en las
  dependencias.
- CodeQL: análisis estático de seguridad del código.
- Secret scanning, push protection y gitleaks: secretos.
- Dependabot: actualizaciones de dependencias y Actions.
- Reglas del repositorio:
  - en `main` solo se integra con los checks en verde;
  - las etiquetas de versión solo las crea el mantenedor;
  - las Releases son inmutables.
- Cada instalador publicado lleva su huella SHA-256 y una atestación de
  procedencia verificable (ver [`SECURITY.md`](../SECURITY.md)).

---

## 3. Integridad

La integridad tiene tres caras: que los **datos del usuario** no se
pierdan ni se corrompan, que la **información clínica** que se muestra sea
correcta y honesta, y que el **código y las versiones** sean lo que dicen
ser.

### 3.1 Integridad de los datos

- **Nunca adivinar.** Si un formato de informe no se reconoce, el fichero
  queda "para revisar"; no se crea ningún paciente ni se inventa ningún
  valor. Es preferible no importar un dato a importarlo mal.
- **Migraciones solo aditivas.** Una base de datos de una versión anterior
  tiene que abrirse en la nueva sin perder nada. No se borran ni se
  renombran columnas con datos. Cualquier cambio de esquema incluye una
  prueba con una base temporal.
- **Las operaciones destructivas se confirman.** Borrar, fusionar o
  sobrescribir datos pide confirmación y explica qué se pierde. Las
  fusiones que no se pueden deshacer se protegen con comprobaciones
  previas (por ejemplo, no fusionar dos pruebas que aparecen en el mismo
  informe).
- **La desinstalación no borra los datos del usuario.**

### 3.2 Integridad clínica

- **Apoyo informativo, nunca un diagnóstico.** Cualquier índice, umbral,
  clasificación o texto mantiene ese planteamiento y lo dice en pantalla.
  No se añaden puntuaciones de riesgo ni alertas que la evidencia no
  respalde.
- **Toda fórmula, umbral o valor clínico lleva su fuente verificable**:
  autores, revista, año y DOI o PMID. La cita va en el código, junto al
  valor, y en [`referencias_medicas/`](referencias_medicas/). Nunca se cita
  de memoria.
- **Discrepancias a la vista.** Si dos fuentes no coinciden, o un dato no
  se ha podido verificar en el texto completo, se indica explícitamente en
  la documentación. No se elige un valor en silencio.
- **Solo datos abiertos.** Analitix es libre y gratuito. Solo incorpora
  datos publicados en abierto o con permiso de redistribución, citados en
  cada caso. No se copian bases de datos cuyos términos lo prohíban.
- **Sin interpretaciones causales.** Los textos describen los datos
  ("dentro del rango en 8 de 10 analíticas"), no diagnostican ni sugieren
  causas.

### 3.3 Integridad del código y de las versiones

- **Pruebas en verde.** `python -m pytest` tiene que pasar. Toda lógica
  nueva, sobre todo los cálculos clínicos y el parser, incluye su test con
  datos sintéticos.
- **Cambios trazables.**
  - Las pull requests van contra `develop`, con una descripción clara de
    qué cambia y por qué.
  - `main` contiene solo la última versión publicada.
  - Si el cambio se nota al usar la aplicación, se añade su entrada en
    `[Sin publicar]` del [`CHANGELOG.md`](../CHANGELOG.md) y se actualiza
    la documentación.
- **Las versiones las compila GitHub, no un equipo personal.** El
  instalador se genera y se prueba en un entorno limpio a partir del
  commit exacto de la etiqueta, y nunca se sube a mano.
- **Autoría y licencia.**
  - Al contribuir, aceptas publicar tu aportación bajo la GPL-3.0.
  - Contribuye solo con código o contenido que tengas derecho a aportar.
  - Si usas herramientas de IA, revisa y entiende lo que envías: la
    responsabilidad de su corrección es de quien lo aporta.

---

## 4. Procedimiento de revisión

1. **Issue primero** para cambios grandes, conexiones de red, dependencias
   nuevas o cualquier cálculo clínico nuevo. Así se acuerda el enfoque
   antes de escribir código.
2. **Pull request contra `develop`**, con la lista de comprobación de la
   plantilla completada.
3. **Checks automáticos en verde**: tests, privacidad, secretos y análisis
   de seguridad.
4. **Revisión del mantenedor**, que comprueba los tres ejes de esta
   política:
   - privacidad: ¿algún dato real, una conexión o un log nuevos?;
   - seguridad: ¿SQL, entrada externa, dependencias?;
   - integridad: ¿fuentes citadas, sin diagnóstico, datos protegidos,
     tests?
5. **Integración en `develop`**. Llega a los usuarios en la siguiente
   versión publicada.

### Motivos de rechazo

Una contribución no se acepta, aunque funcione, si:

- incluye datos personales o de salud reales, o los expone, envía o
  registra;
- añade conexiones de red, telemetría o servicios externos no acordados;
- debilita el cifrado, introduce SQL sin parámetros o ejecuta contenido
  no confiable;
- presenta como diagnóstico algo que solo es orientativo, o usa valores
  clínicos sin fuente verificable o de origen no abierto;
- puede provocar pérdida o corrupción de datos del usuario sin
  salvaguardas;
- añade dependencias innecesarias o con licencias incompatibles.

Si ya se ha publicado un dato real por error, avisa en privado cuanto antes
(ver [`SECURITY.md`](../SECURITY.md)). Se retirará y, si hace falta, se
limpiará también del historial del repositorio.

---

## 5. Compromisos del mantenedor

- Revisar cada contribución con estos mismos criterios, también las
  propias.
- Responder a los avisos de seguridad en un plazo razonable (ver
  [`SECURITY.md`](../SECURITY.md)) y reconocer la aportación si quien
  informa lo desea.
- Mantener esta política al día y explicar cualquier excepción en la
  propia pull request.
