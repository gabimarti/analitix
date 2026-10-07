# Tensión arterial — fuentes, decisiones y limitaciones

**Implementado** en [`src/analitix/blood_pressure.py`](../../src/analitix/blood_pressure.py)
(`home_week_summary`, `bp_category`, `bp_summary_text`) y
[`src/analitix/charts.py`](../../src/analitix/charts.py) (`bp_figure`); se muestra en
**Paneles clínicos → Tensión arterial** y, opcionalmente, en el **informe PDF
personalizado**. Las mediciones se registran en **Entrada manual → Tensión
arterial...**.

Apoyo informativo, nunca un diagnóstico. Cada fuente se ha comprobado (título,
revista, año y DOI/PMID) y los textos citados se han cotejado con el original.

## 1. Media de la automedida en casa (protocolo ESH 2021)

- Stergiou GS, Palatini P, Parati G, et al. 2021 European Society of
  Hypertension practice guidelines for office and out-of-office blood pressure
  measurement. *J Hypertens* 2021;39(7):1293-1302.
  doi:10.1097/HJH.0000000000002843. PMID 33710173.

Recuadro 6 (pauta): mediciones durante 7 días (al menos 3), por la mañana y por
la noche, dos tomas cada vez con 1 minuto entre ellas. Recuadro 7
(interpretación), literal: *"Assess HBPM of 7 days (at least 3 days with at
least 12 readings). Discard the first day and calculate the average of all the
other readings. Individual readings have little diagnostic accuracy. Average
home BP ≥135/85 mmHg indicates hypertension."*

**Cómo lo aplica Analitix.** Toma las mediciones **en casa** de los 7 días que
terminan en la última, descarta el primer día con lecturas y promedia el resto.
La media solo se clasifica si quedan **al menos 3 días y 12 lecturas**; si no,
se muestra la media sin clasificar y se explica qué falta. Las tomas en la
consulta no entran en esta media.

**Guía para medir** (botón «¿Cómo medirla?» y manual): recuadro 4 de la misma
guía (procedimiento: habitación tranquila; sin tabaco, cafeína, comida ni
ejercicio 30 minutos antes; 3-5 minutos sentado y relajado; sin hablar;
espalda apoyada, piernas sin cruzar, brazo desnudo apoyado a la altura del
corazón; tensiómetro de brazo validado y manguito adecuado) y recuadro 6
(pauta: 7 días, al menos 3; mañana y noche, antes de la medicación y de las
comidas; dos mediciones con 1 minuto entre ellas; en el seguimiento a largo
plazo, dos mediciones una o dos veces por semana o, como mínimo, al mes).

**Medias de periodos** (intervalo y comparación del panel): medias
descriptivas de todas las mediciones en casa del periodo, sin clasificar,
porque la guía solo clasifica la media de una semana de automedida.

## 2. Categorías (ESC 2024)

- McEvoy JW, McCarthy CP, Bruno RM, et al. 2024 ESC Guidelines for the
  management of elevated blood pressure and hypertension. *Eur Heart J*
  2024;45(38):3912-4018. doi:10.1093/eurheartj/ehae178. PMID 39210715.

Tabla 5, literal: no elevada *"Office BP <120/70, Home BP <120/70, 24 h ABPM
<115/65"*; elevada *"Office BP 120/70–<140/90, Home BP 120/70–<135/85, 24 h
ABPM 115/65–<130/80"*; hipertensión *"Office BP ≥140/90, Home BP ≥135/85, 24 h
ABPM ≥130/80"*.

**Cómo lo aplica Analitix.** Se usan los umbrales **de casa** para la media de
automedida; manda la peor de las dos cifras (sistólica o diastólica). En el
gráfico, las líneas de 135/85 (discontinua) y 120/70 (punteada) orientan, pero
**una lectura suelta nunca se clasifica**.

## 3. Datos que se muestran sin clasificar

- **Presión de pulso** (sistólica − diastólica) y **pulso medio** de la semana:
  datos descriptivos, sin semáforo. Hay estudios que asocian una presión de
  pulso domiciliaria alta con más eventos en personas mayores, pero no hay un
  umbral de guía para usarlo de forma individual.

## 4. Lo que Analitix no hace, a propósito

- Clasificar lecturas sueltas (la guía lo desaconseja).
- Calcular el *morning surge* (requiere monitorización ambulatoria nocturna).
- Sugerir causas (por ejemplo, hiperaldosteronismo) o indicar objetivos de
  tratamiento: son decisiones clínicas.
- Umbrales propios de variabilidad o de diferencia mañana-noche: solo hay
  asociación en estudios, sin umbral validado.

## 5. Limitaciones

- La calidad depende de cómo se mida (tensiómetro validado de brazo, manguito
  adecuado, 5 minutos sentado, sin hablar). Analitix no puede comprobarlo.
- Arritmias como la fibrilación auricular falsean los tensiómetros
  oscilométricos.
- El riesgo cardiovascular (SCORE2) y el cruce con la función renal llegarán
  en una fase posterior, con sus propias fuentes.
