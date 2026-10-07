# Tendencia robusta y tiempo en rango — fuentes, decisiones y limitaciones

**Implementado** en [`src/analitix/charts.py`](../../src/analitix/charts.py)
(`_fit_trend`, `_trend_direction`, `_trend_text`, `_kdigo_note`,
`time_in_range`); se muestra bajo cada gráfico de **Evolución**,
**Comparativa** y **paneles clínicos**, y en la columna "Tendencia" del
**Resumen**.

Apoyo informativo, nunca un diagnóstico. Una tendencia "demostrable" quiere
decir que, con estos datos, es probable que el valor esté cambiando, no que
el cambio sea malo; "sin tendencia demostrable" tampoco quiere decir que no
cambie nada, sino que con estos datos no se puede afirmar.

Cada fuente se ha comprobado en PubMed o Crossref (título, revista, año y
DOI/PMID).

## 1. Tendencia: pendiente robusta de Theil-Sen con intervalo de confianza

**Qué calcula.** La pendiente es la **mediana de las pendientes entre todos
los pares de analíticas** (en unidades por día, mostrada por año). Su
intervalo de confianza del 95 % sale de la distribución de la τ de Kendall:
con n analíticas y N pares, σ = √(n(n−1)(2n+5)/18), y los límites son las
pendientes ordenadas de posiciones (N − 1,96·σ)/2 y (N + 1,96·σ)/2. La recta
dibujada pasa por mediana(y) − pendiente · mediana(x).

- Sen PK. Estimates of the regression coefficient based on Kendall's tau.
  *J Am Stat Assoc* 1968;63(324):1379-89. doi:10.1080/01621459.1968.10480934.

**Por qué sustituye a la recta de mínimos cuadrados anterior.** Con 5-25
analíticas, un único valor raro (un día puntual, un cambio de laboratorio)
arrastraba la recta; la mediana de pendientes apenas se mueve. Y el
intervalo de confianza responde a la pregunta que de verdad importa: ¿el
cambio es demostrable o puede ser solo variación?

**Decisiones de Analitix** (elecciones prudentes de interfaz, no clínicas):

- Si el intervalo incluye el 0 → **"sin tendencia demostrable"**.
- Con menos de **5 analíticas** o menos de **2 años** → **"pocos datos para
  confirmarla"**: la pendiente de una serie corta e irregular es poco
  estable, aunque su intervalo excluya el 0. La columna del Resumen muestra
  "—".
- Se mantiene el criterio anterior de "estable" (un cambio en todo el
  periodo menor que el 5 % del rango de referencia).
- Sin corrección por empates en la varianza (resultado algo más
  conservador).

**Limitaciones.**

- Supone un cambio aproximadamente lineal; un cambio de tratamiento a mitad
  de la serie lo rompe.
- Mezclar laboratorios con métodos distintos (p. ej. creatinina por Jaffé y
  enzimática) puede crear una tendencia que no es del paciente: el filtro de
  Análisis → Laboratorios incluidos permite separarlos.
- Las analíticas no son independientes ni equiespaciadas; el intervalo es
  orientativo.

## 2. Umbral de velocidad solo para el filtrado glomerular (KDIGO)

La guía KDIGO define la **progresión rápida** de la enfermedad renal crónica
como un **descenso sostenido del FG estimado de más de 5 mL/min/1,73 m² al
año**.

- Kidney Disease: Improving Global Outcomes (KDIGO) CKD Work Group. KDIGO
  2012 Clinical Practice Guideline for the Evaluation and Management of
  Chronic Kidney Disease. Chapter 1: Definition and classification of CKD.
  *Kidney Int Suppl* 2013;3(1):19-62. doi:10.1038/kisup.2012.64. La
  definición se mantiene en la actualización KDIGO 2024 (*Kidney Int*
  2024;105(4S):S117-S314, doi:10.1016/j.kint.2023.10.018) y la National
  Kidney Foundation la usa como criterio de derivación al nefrólogo.

Analitix solo muestra la nota cuando la pendiente de Theil-Sen es menor que
−5/año **y** todo su intervalo de confianza está por debajo de 0 (descenso
demostrable), con al menos 5 analíticas en 2 años. El texto es informativo
("coméntalo con tu médico"), no una clasificación.

**Por qué no hay umbrales para otras pruebas.** No existen umbrales de
velocidad individual validados:

- **PSA**: la "velocidad del PSA" (Carter HB et al., *JAMA*
  1992;267(16):2215-20, PMID 1372942) se ha desaconsejado: añade biopsias
  sin beneficio (Vickers AJ et al., *J Clin Oncol* 2009;27(3):398-403,
  doi:10.1200/JCO.2008.18.1685; Vickers AJ et al., *J Natl Cancer Inst*
  2011;103(6):462-9, doi:10.1093/jnci/djr028).
- **HbA1c**: las medidas de variabilidad de HbA1c solo se asocian a riesgo
  en estudios de grupo, sin umbral individual (Gorst C et al., *Diabetes
  Care* 2015;38(12):2354-69, doi:10.2337/dc15-1188).

## 3. Tiempo en rango (método de Rosendaal)

**Qué calcula.** Entre cada par de analíticas consecutivas se supone que el
valor cambia en **línea recta**, y se cuenta qué fracción de los días cae
dentro del rango; el % final es días dentro / días contados. Es el método
estándar del "tiempo en rango terapéutico" del INR en anticoagulación,
diseñado precisamente para mediciones a intervalos irregulares.

- Rosendaal FR, Cannegieter SC, van der Meer FJ, Briët E. A method to
  determine the optimal intensity of oral anticoagulant therapy. *Thromb
  Haemost* 1993;69(3):236-9. PMID 8470047.
- El mismo concepto de "tiempo en rango" es hoy la medida de referencia de
  la monitorización continua de glucosa: Battelino T et al. Clinical
  targets for continuous glucose monitoring data interpretation:
  recommendations from the International Consensus on Time in Range.
  *Diabetes Care* 2019;42(8):1593-1603. doi:10.2337/dci19-0028.

**Qué aporta.** "Dentro del rango en 5 de 11 analíticas" cuenta analíticas,
no tiempo: si hubo tres analíticas seguidas en un mes malo, pesan igual que
tres años buenos. El % del tiempo resume años de seguimiento en una cifra
que tiene en cuenta cuánto duró cada situación. Con un objetivo indicado
por el médico, se mide respecto a ese objetivo.

**Decisiones de Analitix.**

- No se interpola en **huecos de más de un año** sin analíticas (no se sabe
  qué pasó en medio); se indica si los hay.
- Solo se muestra si lo contado suma **al menos un año**.
- Cada tramo usa el rango de cada analítica, normalizado (0 = límite
  inferior, 1 = superior; con un solo límite, el valor dividido por él);
  un tramo entre dos analíticas con rangos de distinto tipo no se cuenta.
- Se calcula sobre el periodo que muestra el gráfico (por defecto, los
  últimos 5 años).

**Limitaciones.** La interpolación lineal es una suposición: entre dos
analíticas el valor real pudo subir y bajar. Con analíticas muy espaciadas
el % es una aproximación gruesa.

## 4. Evaluado y descartado en esta ronda

Detección de puntos de cambio (sin potencia con 5-25 analíticas),
correlación entre dos pruebas de una misma persona (correlaciones espurias
entre series con tendencia) y diagramas de caja (no aportan con tan pocos
valores). Los gráficos de control CUSUM con la variación biológica
publicada son candidatos para una ronda futura.
