# Referencias: Tiroides, Inflamación, Coagulación

> Parte de [`docs/referencias_medicas/`](README.md) — ver también
> [`docs/DOCUMENTACION_TECNICA.md`](../DOCUMENTACION_TECNICA.md) (secciones
> `thyroid_risk.py` e `inflammation_risk.py`; coagulación no está
> implementada).

Investigación de apoyo para tiroides, inflamación y coagulación, con el
mismo criterio que `src/analitix/lipid_risk.py`: cada cifra verificada con
búsqueda web antes de escribirla, nunca de memoria.

## 8. Tiroides

El punto 4 de la "Recomendación" de abajo — el gráfico combinado TSH+T4L,
sin ningún cálculo nuevo — está implementado en
`src/analitix/thyroid_risk.py` (pestaña "🦋 Tiroides").
**La clasificación por cuadrante (puntos 1-3 de la "Recomendación") sigue
sin implementar**, deliberadamente: sigue siendo el criterio clínico
diagnóstico estándar, no una aproximación de riesgo, y su umbral depende
del embarazo, dato que Analitix no registra — ver el aviso explícito en
el propio módulo y en la pestaña.

**Parámetros de Analitix implicados**: `tirotropina_tsh_serum` (TSH),
`tiroxina_lliure_t4l` (T4 libre), `ac_anti_peroxidasa_tiroidal_serum`,
`ac_anti_tiroglobulina_atg_serum`.

### Rangos de referencia habituales

Según los materiales para pacientes de la American Thyroid Association
(ATA) y revisiones asociadas, el rango "normal" habitual en adultos no
gestantes es **TSH ≈ 0.4–4.0/4.5 mUI/L** y **T4 libre ≈ 0.7–1.8 ng/dL**,
aunque **el propio material de la ATA insiste en que el rango del
laboratorio que ha hecho la prueba debe prevalecer siempre** sobre
cualquier cifra general, porque varía según el método analítico usado.
Fuente: American Thyroid Association, *Clinical Thyroidology for the
Public*, "TSH and Free T4" —
https://www.thyroid.org/patient-thyroid-information/ct-for-patients/february-2024/vol-17-issue-2-p-5-6/
y https://www.thyroid.org/patient-thyroid-information/ct-for-patients/february-2018/vol-11-issue-2-p-3-4/

**Esto es relevante para Analitix**: a diferencia de los índices lipídicos
(donde no hay "rango del informe" porque el índice no lo calcula el
laboratorio), aquí el propio informe **ya trae** `ref_low`/`ref_high` para
TSH y T4L. Si se implementa una clasificación por cuadrante, **debe
calcularse contra el rango impreso en cada informe concreto** (igual que ya
hace `pdf_parser.compute_flag` con cualquier otro parámetro), no contra una
cifra fija tipo "4.0" hardcodeada — así se evita automáticamente el
problema de que el rango varíe por laboratorio, método, edad o embarazo.

### Tabla de interpretación por cuadrante

Confirmada contra varias fuentes independientes (Mayo Clinic Proceedings,
NCBI Bookshelf, y una revisión específica de hipertiroidismo subclínico):

| TSH | T4 libre | Interpretación |
|---|---|---|
| Alta | Baja | Hipotiroidismo primario manifiesto ("overt") |
| Alta | Normal | Hipotiroidismo subclínico (TSH 4.5–10 = leve; >10 = marcado) |
| Baja | Normal | Hipertiroidismo subclínico |
| Baja | Alta | Hipertiroidismo manifiesto |

Fuentes:
- Cooper DS, Biondi B. "Subclinical thyroid disease." Mayo Clin Proc /
  Lancet review — resumen accesible en
  https://www.mayoclinicproceedings.org/article/S0025-6196(11)62389-6/fulltext
- NCBI Bookshelf, "Screening and Treatment of Subclinical Hypothyroidism or
  Hyperthyroidism" — https://www.ncbi.nlm.nih.gov/books/NBK83492/ (define
  subclínico como TSH anormal + T4L y T3 normales, y confirma la relación
  fisiológica log-lineal inversa entre TSH y T4L: un pequeño descenso de T4L
  produce un ascenso grande de TSH, y viceversa).
- Bahn RS et al. (revisión de manejo de hipertiroidismo subclínico) —
  https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3693616/

### Por qué esto es más delicado que los otros índices

A diferencia de Castelli I/II o TG/HDL (que son *factores de riesgo*, no una
clasificación diagnóstica en sí), la tabla de arriba **es literalmente el
criterio clínico estándar** para diagnosticar disfunción tiroidea — no una
aproximación orientativa inventada para este proyecto. Mostrarla en la app,
aunque sea con el mismo aviso "apoyo informativo, no diagnóstico" que ya usa
el resto de Analitix, se acerca mucho más a "decirle al usuario qué tiene"
que cualquier otro cálculo de esta lista. Matices que habría que comunicar
explícitamente en la UI si se implementa:
- **El rango de referencia varía por laboratorio, edad y, sobre todo,
  embarazo**: la propia ATA recomienda límites de TSH distintos por
  trimestre de gestación (p. ej. límite superior ~2.5 mUI/L en el primer
  trimestre en guías históricas de la ATA de 2012, frente a ~4.0–4.5 mUI/L
  en población no gestante) — Analitix no registra si la paciente está
  embarazada, así que una clasificación automática podría ser directamente
  incorrecta en ese caso sin que la app tenga forma de saberlo. Habría que
  advertirlo de forma muy visible, no en una nota pequeña.
- La clasificación por cuadrante es válida como "patrón bioquímico
  compatible con...", no como diagnóstico: hace falta confirmación en 3-6
  meses y valoración clínica completa (síntomas, anticuerpos,
  antecedentes) antes de que un médico la use realmente.
- El texto de la app debería describir el **patrón** ("TSH elevada con T4
  libre normal"), no nombrar la entidad clínica como conclusión propia
  (evitar que la app "diga" el diagnóstico).

### Recomendación

Implementable, pero con más cautela que el resto de la lista:
1. Clasificar siempre contra el rango del propio informe (`ref_low`/
   `ref_high` ya guardados), nunca contra un umbral fijo — reduce el riesgo
   de un cuadrante mal calculado en una plantilla con reactivo distinto.
2. Aviso explícito y visible sobre embarazo (rango distinto, no
   verificable por la app) y sobre la necesidad de repetición/confirmación
   antes de cualquier conclusión clínica.
3. Los anticuerpos (`ac_anti_peroxidasa_tiroidal_serum`/
   `ac_anti_tiroglobulina_atg_serum`) no entran en esta tabla — son
   marcadores de autoinmunidad (Hashimoto/Graves), útiles para dar
   contexto en la ficha descriptiva pero no para el cuadrante TSH/T4L.
4. El gráfico combinado TSH+T4L en un mismo panel (relación inversa
   fisiológica) es la parte de más bajo riesgo de esta idea — es solo
   visualización, no clasificación — y podría implementarse primero,
   dejando el texto de interpretación automática por cuadrante para una
   segunda fase si el usuario, tras verlo, sigue queriendo esa parte.

## 9. Inflamación

Implementado en `src/analitix/inflammation_risk.py` (pestaña "🔥
Inflamación", menú Paneles clínicos) — sin ningún índice combinado, tal y
como concluía esta investigación: solo las dos series superpuestas y un
aviso de discordancia.

**Parámetros de Analitix implicados**: `proteina_c_reactiva_serum` (PCR),
`vsg_velocitat_de_sedimentacio_globular` (VSG).

### Cinéticas distintas — confirmado

- **PCR**: reactante de fase aguda con cinética bien definida — empieza a
  subir en 12-24 h, pico a los 2-3 días, semivida ~19 h, vuelve a valores
  normales en 3-7 días tras resolverse el proceso.
- **VSG**: sube y baja mucho más despacio, porque depende indirectamente
  del fibrinógeno (mayor semivida que la PCR) — útil para procesos
  inflamatorios crónicos y para su seguimiento a más largo plazo, poco útil
  para valorar respuesta a tratamiento a corto plazo (a diferencia de la
  PCR, que sí sirve para eso).

Fuentes: Litao MKS, Kamat D. "Erythrocyte Sedimentation Rate and
C-Reactive Protein: How Best to Use Them in Clinical Practice." Pediatr
Ann. 2014 — https://pubmed.ncbi.nlm.nih.gov/25290132/; Lapić I, Padoan A,
Bozzato D, Plebani M. "Erythrocyte Sedimentation Rate and C-Reactive
Protein in Acute Inflammation: Meta-Analysis of Diagnostic Accuracy
Studies." Am J Clin Pathol. 2020;153(1):14-29. doi:10.1093/ajcp/aqz142 —
https://academic.oup.com/ajcp/article/153/1/14/5584484 (autoría verificada:
Lapić et al., no "Vanderschueren S et al." como aparece citado en alguna
fuente secundaria) — confirma explícitamente que **ambos marcadores
pueden discordar** por múltiples factores fisiológicos no patológicos, y
que esa discordancia en sí misma puede ser clínicamente informativa.
Corroborado por el College of American Pathologists, "C-Reactive Protein
and Erythrocyte Sedimentation Rate Test Use":
https://documents.cap.org/documents/C-ReactiveProteinandErythrocyteSedimentationRateTestUse.pdf

### No existe un índice combinado estándar

Confirmado: no se ha encontrado ningún índice PCR+VSG validado y de uso
extendido (a diferencia de Castelli I/II o TG/HDL, que sí combinan dos
valores en un número con puntos de corte publicados) — tiene sentido dado
que miden procesos fisiológicos distintos con cinéticas distintas, mezclar
sus valores en un cociente no tendría una interpretación fisiológica clara.
La literatura respalda mostrarlas **superpuestas en el tiempo, no
fusionadas**, precisamente porque su discordancia (una sube y la otra no,
o al revés) puede ser tan informativa como su valor absoluto.

### Recomendación (implementada)

Ningún índice nuevo. El valor está en la **visualización** y en el aviso
de discordancia, no en un cálculo: `inflammation_risk.py` reutiliza
`charts.comparison_figure` (el mismo motor de dos paneles apilados de
Comparativa) para mostrar PCR y VSG superpuestas, con un botón dedicado en
su propia pestaña en vez de depender de que el usuario las seleccione a
mano en Comparativa. La nota descriptiva de la cinética de cada una vive
en `data/descripciones/idx_inflamacion.txt` (formato dual lenguaje llano +
técnico, mismo patrón que hemograma/hierro). El NLR (índice
neutrófilos/linfocitos, §4 de la lista) es otro marcador inflamatorio de
coste cero que ya sale calculado en el hemograma — ver
`referencias_hemograma.md`.

## 10. Coagulación

**Parámetros de Analitix implicados**: `temps_de_protrombina_rati_plasma`
(INR/rati), `temps_tromboplastina_parcial_activada_s_plasma` (TTPA).

### Rango de referencia de laboratorio vs. rango terapéutico

Importante distinguir dos cosas distintas:
- El **rango de referencia de laboratorio** para el INR (pensado para
  población *no* anticoagulada) suele rondar 0.8–1.2, y es el que ya trae
  cada informe (`ref_low`/`ref_high`) — ese ya se usa bien hoy.
- El **rango terapéutico objetivo** en un paciente que toma un
  anticoagulante antagonista de la vitamina K (acenocumarol/warfarina) es
  un número completamente distinto, fijado por el médico según la
  indicación clínica — no es un "rango normal poblacional", es un objetivo
  de tratamiento individual.

### Rangos terapéuticos confirmados

- **Indicación estándar** (fibrilación auricular, tromboembolismo venoso):
  **INR objetivo 2.0–3.0**. Confirmado en las guías CHEST (American College
  of Chest Physicians), 9ª edición, *Antithrombotic Therapy and Prevention
  of Thrombosis* (2012) — resumen ejecutivo:
  https://www.acc.org/latest-in-cardiology/journal-scans/2012/02/21/21/25/executive-summary-antithrombotic-therapy-and-prevention-of-thrombosis
  — y reafirmado por actualizaciones posteriores AHA/ACC/HRS (2019) para
  fibrilación auricular.
- **Válvula cardíaca mecánica** (objetivo más alto): según CHEST 9ª
  edición, *Antithrombotic and Thrombolytic Therapy for Valvular Disease*
  — https://pubmed.ncbi.nlm.nih.gov/22315272/ y
  https://journal.chestnet.org/article/S0012-3692(12)60132-9/fulltext —
  **INR objetivo 2.5 para válvula aórtica, 3.0 para mitral o doble
  válvula** (con aspirina a dosis baja añadida en pacientes de bajo riesgo
  hemorrágico). La guía posterior ACC/AHA 2020 sobre valvulopatías matiza
  con rangos: aórtica de bajo riesgo 2.0–3.0 (objetivo 2.5), mitral o
  aórtica de alto riesgo 2.5–3.5 (objetivo 3.0).

### Por qué no conviene hardcodear un único umbral

El objetivo correcto **depende de la indicación de cada paciente concreto**
(fibrilación auricular vs. válvula mecánica vs. tromboembolismo venoso,
cada una con su propio objetivo), algo que Analitix no registra hoy (no
sabe *por qué* un paciente está anticoagulado). Colorear automáticamente el
INR como "alto"/"bajo" contra un único rango fijo (p. ej. 2.0–3.0) sería
directamente incorrecto para un paciente con válvula mecánica cuyo objetivo
real es 3.0, y el usuario no tiene forma de decírselo a la app hoy.

### Recomendación

**No implementar un umbral fijo de INR**. La idea original (punto 10 de
la documentación de líneas futuras) ya lo señalaba: el caso de uso real aquí es un
**rango de referencia personalizado por paciente y parámetro**, editable a
mano por el usuario (p. ej. desde "Entrada manual" o una nueva opción en la
ficha del paciente), que sustituya al rango impreso en el informe solo para
ese parámetro y ese paciente cuando aplique — esto es una funcionalidad
genérica de la app (útil no solo para INR, sino para cualquier parámetro
con objetivo terapéutico individual), no algo específico de coagulación.
Hasta que exista esa funcionalidad, lo más honesto es no clasificar el INR
automáticamente y, como mucho, mostrar como texto informativo (no como
`flag_calc`) los rangos objetivo estándar citados arriba, dejando claro que
el que aplica a cada paciente lo determina su médico.
