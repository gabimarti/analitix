# Aviso de seguridad orientativo: subida brusca de creatinina (AKI)

> Parte de [`docs/referencias_medicas/`](README.md) — ver también
> [`docs/DOCUMENTACION_TECNICA.md`](../DOCUMENTACION_TECNICA.md) (sección
> `renal_risk.py`).

Nota de investigación, complementaria a `referencias_renal.md`, que
documenta la clasificación KDIGO **crónica** (G1-G5 + A1-A3, estable en el
tiempo). Esta idea es distinta y complementaria: un aviso sobre un **cambio
brusco** de creatinina entre informes, aprovechando que Analitix ya calcula
variación porcentual entre el último valor y el anterior en sus gráficos
(`charts._pct_change_text`). Mismo principio que el resto del proyecto:
apoyo informativo y de seguimiento, **nunca un diagnóstico** de fallo renal
agudo (AKI).

## Parámetros de Analitix implicados

Confirmado mirando `src/analitix/data/descripciones/`: existen fichas para
`creatinina_serum`, `filtrat_glomerular_estimat`/`filtrat_glomerular_estimat_90_ml_min`/
`filtrat_glomerular_estimat_serum`, `urea_serum`, `potassi`, `sodi`, y
variantes de albuminuria (`albumina_creatinina`,
`albumina_creatinina_orina_esporadica`, `albuminuria`, `microalbuminuria`).
El único parámetro relevante para AKI por creatinina es `creatinina_serum`
— los demás son los mismos que ya usa la idea de KDIGO crónico de §3.

## Guías y estudios verificados

### 1. Definición KDIGO 2012 (el estándar clínico de origen)

Kidney Disease: Improving Global Outcomes (KDIGO) Acute Kidney Injury Work
Group. *KDIGO Clinical Practice Guideline for Acute Kidney Injury*. Kidney
Int Suppl. 2012;2(1):1-138. Resumido y verificado vía fuentes secundarias
que citan la guía con precisión (KDOQI US Commentary,
https://www.ajkd.org/article/S0272-6386(13)00471-X/fulltext, y múltiples
artículos que reproducen la tabla de criterios).

AKI se define por **cualquiera** de estos tres criterios:
- Subida de creatinina sérica ≥ 0.3 mg/dL (≈26 µmol/L) en 48 horas.
- Subida ≥ 1.5× el valor basal en 7 días.
- Diuresis < 0.5 mL/kg/h durante 6 horas (no aplicable a Analitix: no
  registra diuresis).

Estadificación por magnitud de la subida: estadio 1 (1.5-1.9× basal, o
+0.3 mg/dL), estadio 2 (2.0-2.9× basal), estadio 3 (≥3× basal, o
creatinina ≥4.0 mg/dL, o necesidad de diálisis).

**Este criterio, tal cual, no encaja con el caso de uso de Analitix**: está
pensado para vigilancia hospitalaria estrecha (horas/días), y las
analíticas que Analitix importa suelen estar separadas por semanas o meses.

### 2. NICE NG148 — contexto de AKI en atención primaria/comunitaria

National Institute for Health and Care Excellence. *Acute kidney injury:
prevention, detection and management* (NG148). Última actualización 2023.
https://www.nice.org.uk/guidance/ng148 (contenido verificado vía mirror
NIH/NCBI Bookshelf y resumen de la propia guía).

Puntos relevantes: el AKI es cada vez más frecuente en atención primaria en
personas **sin enfermedad aguda evidente**, y la detección se basa
sobre todo en la monitorización de la creatinina; en personas con
enfermedad renal crónica ya conocida y sin enfermedad aguda evidente, una
subida de creatinina puede indicar un AKI superpuesto, no solo progresión
de la enfermedad crónica — relevante porque el paciente de Analitix con
ERC ya diagnosticada (si la clasificación KDIGO crónica de §3 se llega a
implementar) es justo el perfil en el que un cambio brusco adicional
merece atención aparte.

### 3. El algoritmo nacional del NHS de Inglaterra — la pieza clave para Analitix

Sawhney S, Fluck N, Marks A, et al. "Acute kidney injury—how does automated
detection perform?" *Nephrol Dial Transplant*. 2015;30(11):1853-1861. DOI:
10.1093/ndt/gfv094. https://pmc.ncbi.nlm.nih.gov/articles/PMC4617372/
(verificado vía fetch directo del artículo, tabla 1).

Este artículo describe el algoritmo de alerta de AKI que el NHS England
implementó de forma obligatoria en los laboratorios hospitalarios
(basado en KDIGO, pero adaptado para funcionar sobre datos de laboratorio
reales con analíticas espaciadas de forma irregular — exactamente el
problema de Analitix). El algoritmo compara cada nueva creatinina contra
tres ventanas de referencia distintas, y dispara la alerta si **cualquiera**
de las tres se cumple:

1. **Ventana 8-365 días** (la que importa aquí): creatinina actual ≥ 1.5×
   la **mediana** de todas las creatininas de ese paciente entre 8 y 365
   días antes.
2. Ventana 1-7 días: creatinina actual ≥ 1.5× la creatinina más baja de los
   últimos 7 días.
3. Ventana 48 horas: creatinina actual > 26 µmol/L (≈0.3 mg/dL) por encima
   de la más baja de las últimas 48 horas.

**Por qué esto sí es aplicable a Analitix, a diferencia de KDIGO "puro"**:
el criterio 1 (8-365 días, comparando contra la *mediana* de analíticas
anteriores, no contra el valor inmediatamente anterior) es el único de los
tres diseñado para el mismo patrón de datos que tiene Analitix —
analíticas de rutina espaciadas semanas o meses, no vigilancia horaria.
Los criterios 2 y 3 (7 días, 48 horas) no tienen sentido con analíticas tan
espaciadas y no deberían usarse aquí.

**Limitación explícita, documentada por la propia literatura de AKI
comunitario** (ver p. ej. Sawhney et al. y la revisión "Review no. 3:
handling of longitudinal creatinine data to define acute kidney injury",
PMC13242417): la definición de la creatinina "basal" cambia mucho el
resultado — usar la mediana de un año entero (como hace el criterio 1) es
en sí mismo un compromiso, no una medida exacta, precisamente por la baja
frecuencia de las analíticas en atención primaria/comunitaria. Distintas
elecciones de ventana/basal dan tasas de detección de AKI muy distintas
entre sí (un estudio en urgencias encontró prevalencias de 5.9% a 24.0%
según qué definición de basal se usara). Esto refuerza que cualquier aviso
basado en esto en Analitix debe presentarse como una señal débil y
orientativa, nunca como una alerta clínica equivalente a la que recibe un
médico del sistema del NHS (que además siempre se interpreta junto con el
cuadro clínico completo del paciente, no de forma aislada).

## Recomendación honesta

**Sí hay una base real y citable** para algo mucho más modesto que
"detección de AKI": un aviso del tipo *"la creatinina de este informe es
≥1.5× la mediana de tus creatininas del último año — puede valer la pena
comentarlo con tu médico"*, inspirado directamente en el criterio 1 (8-365
días) del algoritmo del NHS England (Sawhney et al. 2015), que es el único
de los tres criterios KDIGO/NHS pensado para datos tan espaciados como los
de Analitix. Esto es coherente con la infraestructura que Analitix ya
tiene (`charts._pct_change_text` ya calcula variaciones porcentuales entre
informes) — sería extender esa misma lógica con un umbral y una mediana en
vez de solo el punto inmediatamente anterior.

**Qué NO se debería implementar**: cualquier cosa que se llame "detección
de AKI" o "estadio de fallo renal agudo" sin más matices — ni los
criterios de 48 horas ni de 7 días de KDIGO (no tienen sentido con
analíticas espaciadas) ni ninguna alerta que ignore que la propia
definición de "basal" es ambigua en este contexto (ver limitación
anterior). El texto de cualquier aviso debe dejar clarísimo que es una
señal aproximada basada en un criterio adaptado de vigilancia hospitalaria,
no una alerta médica validada para este caso de uso.

## Implementación

`src/analitix/renal_risk.aki_ratio` calcula exactamente el criterio 1
descrito arriba: creatinina actual ÷ mediana de las creatininas de ese
paciente entre 8 y 365 días antes, marcado (⚠) a partir de 1.5 — como un
índice más, con su propia serie temporal e histórico, dentro de la pestaña
"🩺 Función renal". El texto de la app ("Creatinina actual / mediana del
último año", nunca "AKI" ni "fallo renal agudo") y su ficha de descripción
(`data/descripciones/idx_aki_creatinina.txt`) siguen la recomendación
honesta de arriba: se presenta como señal débil, con la limitación de la
"basal" ambigua explicada en el propio texto.
