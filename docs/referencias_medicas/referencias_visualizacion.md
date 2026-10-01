# Cómo se presentan los resultados — evidencia sobre visualización para pacientes

Este documento recoge los estudios en los que se apoyan las decisiones de
presentación de Analitix: cómo se muestran los resultados, no qué se
calcula con ellos.

**Advertencia general.** La evidencia es escasa. Casi toda procede de un
mismo grupo de investigación (Zikmund-Fisher y colaboradores, Universidad
de Michigan) y de experimentos en línea con resultados hipotéticos de una
sola determinación. Ninguna revisión encuentra estudios sólidos sobre
gráficos **de evolución en el tiempo** dirigidos a pacientes:

- van der Mee et al. *J Med Internet Res* 2024;26:e53993.
  doi:10.2196/53993.
- Turchioe et al. *Appl Clin Inform* 2019;10(4):751-770.
  doi:10.1055/s-0039-1697592. Las rectas numéricas y las barras se
  entienden mejor que los gráficos de líneas, y los valores en el límite
  son los que peor se interpretan.

Lo que sigue es, por tanto, orientativo y no un formato validado.

## Resumen en texto de cada parámetro — implementado

Debajo de cada gráfico de evolución (Evolución, Comparativa, paneles
clínicos e informe PDF) aparece una frase descriptiva del tipo "Dentro del
rango en 8 de 10 analíticas; la última (2025-01-01), un 8 % por encima del
límite superior (110)". La genera `charts.series_summary`.

- Morrow et al. *J Exp Psychol Appl* 2019;25(1):41-61.
  doi:10.1037/xap0000203, PMID 30688498. En personas mayores, el contexto
  verbal ayudó a recordar la idea principal del resultado más que el
  gráfico.
- Shaffer et al. *JAMIA Open* 2026;9(2):ooag034.
  doi:10.1093/jamiaopen/ooag034. Con series de tensión arterial, el
  resumen solo en texto funcionó igual que el semáforo o el degradado de
  color.
- van der Mee 2024 (arriba) recomienda añadir texto en lenguaje llano.

Criterios de redacción:

- La frase es **descriptiva y nunca causal**: no dice por qué ni qué
  significa clínicamente.
- Cuenta cada analítica según el rango de referencia de **su propio
  informe**, que es el mismo criterio del resto de la app.
- El % se mide respecto al límite superado y no respecto al centro del
  rango, para no sugerir que el centro sea "óptimo".

## Aviso de pocos datos — implementado

Con una sola analítica no se dibuja ningún gráfico, porque un punto suelto
parecería una evolución. Por debajo del mínimo configurable (4 por
defecto), el gráfico lleva un aviso. Es una decisión de interfaz basada en
la falta de evidencia descrita arriba, no un umbral clínico.

## Cambio real o variación esperable (RCV) — implementado

Ver [`referencias_rcv.md`](referencias_rcv.md). Ningún estudio ha
comprobado cómo entienden los pacientes la presentación del RCV. Por eso
se muestra con mensajes prudentes: "probablemente real", nunca
"patológico".

## Pendientes, con su evidencia (no implementados todavía)

- **Recta numérica con etiqueta verbal** ("ligeramente alto") para el
  futuro gráfico de bala.
  - Zikmund-Fisher et al. *JAMIA* 2017;24(3):520-528.
    doi:10.1093/jamia/ocw169, PMID 28040686.
  - Brewer et al. *Med Decis Making* 2012;32(4):545-553.
    doi:10.1177/0272989X12441395.
- **Objetivo indicado por el médico que sustituye al rango del
  laboratorio** (por ejemplo, para el LDL). Scherer et al. *J Med Internet
  Res* 2018;20(10):e11027. doi:10.2196/11027, PMID 30341053. Mostrar solo
  el objetivo mejoró la comprensión; añadirlo junto al rango estándar no
  ayudó.
- **Paleta apta para daltonismo y codificación redundante** (símbolo o
  texto además del color).
  - Turchioe 2019 (arriba).
  - Fraccaro et al. *BMC Med Inform Decis Mak* 2018;18:11.
    doi:10.1186/s12911-018-0589-7.
- **Descartado: un segundo umbral de "a partir de aquí suele preocupar al
  médico"** ("harm anchor"; Zikmund-Fisher et al. *J Med Internet Res*
  2018;20(3):e98, doi:10.2196/jmir.8889). Ese umbral lo tendría que fijar
  Analitix, y podría dar una falsa tranquilidad.
