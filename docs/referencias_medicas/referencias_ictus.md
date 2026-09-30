# Referencias científicas — Riesgo de ictus (ACV) (línea futura)

> Parte de [`docs/referencias_medicas/`](README.md) — ver también
> [`docs/DOCUMENTACION_TECNICA.md`](../DOCUMENTACION_TECNICA.md) (el ácido
> úrico que aquí se descarta como marcador de ictus está implementado con
> otra indicación en la sección `uric_acid_risk.py`).

Investigación de apoyo para una futura ampliación de riesgo de ictus (ACV
isquémico/hemorrágico o AIT), con el mismo criterio que
`src/analitix/lipid_risk.py`: cada cifra, fórmula o umbral está verificado
contra una fuente real (búsqueda web, nunca de memoria) antes de citarlo
aquí. Documento de investigación, sin código todavía. Como el resto de
Analitix, esto sería **apoyo informativo y de seguimiento, nunca un
diagnóstico ni una estimación de riesgo clínicamente accionable por sí
sola** — ningún cálculo de esta lista sustituye la valoración de un
neurólogo/cardiólogo ni las escalas clínicas completas que usan.

## Parámetros de Analitix implicados

Confirmados en `src/analitix/data/descripciones/`:

- Perfil lipídico: `colesterol_serum` (total), `colesterol_hdl_serum`,
  `colesterol_ldl`, `colesterol_no_hdl_serum`, `colesterol_vldl`,
  `triglicerids_serum` — ya cubiertos para riesgo cardiovascular general en
  `lipid_risk.py` (Castelli I/II, TG/HDL, LDL Friedewald); este documento
  solo los menciona cuando aparecen como ingrediente de un score de ictus
  específico, sin repetir esa investigación.
- `hb_glicosilada_hba1c_sang` / `hb_glicosilada_hba1c_ifcc_sang` (HbA1c),
  `glucosa_serum`.
- `proteina_c_reactiva_serum` / `proteina_c_reactiva` (PCR).
- `fibrinogen` / `fibrinogen_derivat_plasma`.
- `nt_probnp_serum` (NT-proBNP).
- `temps_de_protrombina_rati_plasma` (INR/rati),
  `temps_tromboplastina_parcial_activada_s_plasma` (TTPA).
- Función renal: `creatinina_serum`, `filtrat_glomerular_estimat_serum`,
  `urea_serum`.
- Hemograma: `hemoglobina`, `hematocrit`, `hematies`, `vcm`, `hcm`, `chcm`,
  `rdw_cv`, `leucocits`, `neutrofils_total`, `limfocits_total`,
  `monocits_total`, `eosinofils_total`, `basofils_total`, `plaquetes`,
  `vpm`.
- Electrolitos: `potassi`, `sodi`.
- Ácido úrico: el `canonical_id` real en `data/descripciones/` es
  **`urat_serum`** ("urato"), no `acid_uric_serum` como se había supuesto —
  confirmado listando el directorio.

**Confirmado que Analitix NO guarda hoy** (buscado explícitamente):
homocisteína, lipoproteína(a) [Lp(a)], apolipoproteína B/A1, dímero D,
sexo, tensión arterial, tabaquismo, antecedentes de fibrilación auricular
u otros antecedentes clínicos. `birth_date` sí se guarda (campo "Data
naixement" del PDF), pero no se usa en ningún cálculo de esta sección —
misma limitación ya documentada para FIB-4 (`referencias_hepatico.md`) y
CKD-EPI 2021 (`referencias_renal.md`).

---

## 1. Scores compuestos de riesgo de ictus

Conclusión adelantada tras investigar los cuatro modelos más relevantes:
**ninguno es calculable solo con datos de laboratorio** (ni siquiera
añadiendo edad/sexo) — todos exigen como mínimo la tensión arterial, y la
mayoría también tabaquismo y/o antecedentes clínicos. Esto reproduce, para
ictus, la misma limitación que ya existe para el riesgo cardiovascular
general (SCORE2/Framingham).

### 1.1 CHA2DS2-VASc

**Cita original:** Lip GYH, Nieuwlaat R, Pisters R, Lane DA, Crijns HJGM.
"Refining clinical risk stratification for predicting stroke and
thromboembolism in atrial fibrillation using a novel risk factor-based
approach: the Euro Heart Survey on Atrial Fibrillation." *Chest*.
2010;137(2):263-272. DOI: 10.1378/chest.09-1584. PMID: 19762550.

**Población de validación:** Euro Heart Survey on Atrial Fibrillation,
cohorte europea multicéntrica (varios países ESC).

**Componentes (8, todos clínicos/demográficos salvo un matiz en diabetes):**
insuficiencia cardiaca/disfunción de VI, hipertensión (diagnóstico/
tratamiento), edad ≥75 (puntúa doble), diabetes mellitus, ictus/AIT/
tromboembolismo previo (puntúa doble), enfermedad vascular (IAM previo,
EAP, placa aórtica), edad 65-74, sexo femenino.

**Matiz sobre "diabetes":** la definición operacional habitual en guías ESC
de FA y protocolos de ensayos posteriores es "glucosa en ayunas ≥126 mg/dL
(7 mmol/L) o tratamiento con hipoglucemiante/insulina" — es decir, admite
un valor de laboratorio (glucosa) pero combinado siempre con un dato de
tratamiento (clínico). No se pudo verificar si esta definición aparece
literalmente en el texto del paper original de 2010 (bloqueado por
paywall); se cita como definición operacional estándar de guías, no como
texto confirmado línea por línea del artículo.

**Limitación fundamental para Analitix, más allá de las variables:** el
score está **derivado y validado exclusivamente en pacientes con
fibrilación auricular ya diagnosticada** — su uso en población general sin
FA conocida no está validado (hay estudios exploratorios que lo prueban,
pero no es un uso aprobado del score). Analitix no tiene forma de saber si
un paciente tiene FA diagnosticada a partir de una analítica de sangre.

**Implementable con datos de laboratorio solos: NO.** 6 de 8 componentes
son clínicos/de antecedentes (no derivables de un PDF de analítica), y el
score en sí no es aplicable sin diagnóstico previo de FA.

### 1.2 Framingham Stroke Risk Profile (FSRP)

**Citas verificadas:**
- Wolf PA, D'Agostino RB, Belanger AJ, Kannel WB. "Probability of stroke: a
  risk profile from the Framingham Study." *Stroke*. 1991;22(3):312-318.
  DOI: 10.1161/01.str.22.3.312.
- D'Agostino RB, Wolf PA, Belanger AJ, Kannel WB. "Stroke risk profile:
  adjustment for antihypertensive medication. The Framingham Study."
  *Stroke*. 1994;25(1):40-43. DOI: 10.1161/01.str.25.1.40. PMID: 8266381.
- Revisión moderna: Dufouil C, Beiser A, McLure LA, et al. "Revised
  Framingham Stroke Risk Profile to Reflect Temporal Trends." *Circulation*.
  2017;135(12):1145-1159. DOI: 10.1161/CIRCULATIONAHA.115.021275.
  PMID: 28159800.

**Población de validación:** cohorte de Framingham (Massachusetts, EE.UU.,
predominantemente blanca); la revisión de 2017 se validó externamente en
cohortes 3C (Francia) y REGARDS (EE.UU., incluye población afroamericana).

**Variables (versión 1994):** edad, presión arterial sistólica (tratada y
no tratada, variable central — el propio paper de 1994 existe para ajustar
por tratamiento antihipertensivo), historia de diabetes (antecedente
clínico, sin definición de laboratorio en esta versión), tabaquismo actual,
enfermedad cardiovascular previa, fibrilación auricular (requiere ECG),
hipertrofia ventricular izquierda por ECG (requiere prueba, no analítica de
sangre).

**Novedad de la revisión 2017 (Dufouil):** por primera vez define diabetes
con un valor de laboratorio explícito — "glucosa plasmática en ayunas
≥7 mmol/L (126 mg/dL), glucosa casual ≥11.1 mmol/L, o uso de
insulina/hipoglucemiante" — y elimina la LVH por ECG. Aun así mantiene la
PAS como variable obligatoria.

**Implementable con datos de laboratorio solos: NO.** La PAS es la variable
de mayor peso y es obligatoria; tabaquismo, ECV previa y FA son también
clínicos y obligatorios. Solo el componente diabetes (versión 2017) admite
un proxy de laboratorio (glucosa), pero no basta por sí solo.

### 1.3 Pooled Cohort Equations (ACC/AHA)

**Cita:** Goff DC Jr, Lloyd-Jones DM, Bennett G, et al. "2013 ACC/AHA
Guideline on the Assessment of Cardiovascular Risk." *Journal of the
American College of Cardiology*. 2014;63(25 Pt B):2935-2959. DOI:
10.1016/j.jacc.2013.11.005. PMID: 24239921 (co-publicado en *Circulation*.
2014;129(25 Suppl 2):S49-S73, texto completo no accesible por paywall en
esta investigación).

**Población de validación:** cohortes estadounidenses combinadas (ARIC,
Cardiovascular Health Study, CARDIA, Framingham Original y Offspring) —
válido para hombres y mujeres blancos y afroamericanos de 40-79 años;
**explícitamente no validado sin recalibración para otras etnias**
(hispanos, asiáticos, etc.), y no es población europea.

**Variables:** edad, sexo, raza (coeficientes específicos blanca/
afroamericana), **colesterol total (lab)**, **colesterol HDL (lab)**,
presión arterial sistólica (obligatoria), tratamiento antihipertensivo,
diabetes (sí/no, clínico), tabaquismo actual.

**Endpoint:** riesgo a 10 años de ASCVD combinado (IAM no fatal + ictus no
fatal + muerte cardiovascular) — **no es un score aislado de ictus**. No se
encontró una "Stroke Pooled Cohort Equation" oficial derivada por separado
de las mismas cohortes (se declaró explícitamente esta ausencia en vez de
inventarla); solo existen estudios que aplican las PCE estándar a
poblaciones con ictus previo (prevención secundaria), lo cual es un uso
distinto.

**Implementable con datos de laboratorio solos: PARCIAL.** Colesterol
total y HDL son de laboratorio, pero PAS, tratamiento antihipertensivo,
diabetes y tabaquismo son obligatorios y no sustituibles — y el resultado
sería riesgo de ASCVD combinada, no de ictus específicamente.

### 1.4 SCORE2 / SCORE2-OP (ESC)

**Cita:** SCORE2 working group and ESC Cardiovascular Risk Collaboration.
"SCORE2 risk prediction algorithms: new models to estimate 10-year risk of
cardiovascular disease in Europe." *European Heart Journal*.
2021;42(25):2439-2454. DOI: 10.1093/eurheartj/ehab309. PMID: 34120177.
(SCORE2-OP: misma revista/número, DOI: 10.1093/eurheartj/ehab312.)

**Población de validación:** 45 cohortes de 13 países **europeos**
(677,684 individuos, 30,121 eventos), calibrado en 4 regiones de riesgo
europeas — la más aplicable geográficamente a Analitix de los 4 modelos,
pero con la misma limitación de fondo.

**Variables del SCORE2 base (sin diabetes, que tiene su propio modelo
SCORE2-Diabetes):** edad, sexo, tabaquismo actual, presión arterial
sistólica (obligatoria), **colesterol total (lab)**, **colesterol HDL
(lab)**.

**Endpoint:** igual que las PCE, compuesto de mortalidad cardiovascular +
IAM no fatal + ictus no fatal — no aísla el ictus. SCORE2-Diabetes (*Eur
Heart J*. 2023;44(28):2544) añade HbA1c y eGFR/creatinina como variables
de laboratorio adicionales, pero mantiene PAS y tabaquismo obligatorios.

**Implementable con datos de laboratorio solos: PARCIAL**, igual límite que
las PCE: 2 de 5 variables base son de laboratorio, PAS y tabaquismo son
obligatorios y no derivables de una analítica, y el resultado es riesgo de
ECV compuesta, no de ictus aislado.

---

## 2. Marcadores individuales con evidencia sólida de asociación con ictus

### 2.1 PCR / hs-CRP — atención a la distinción de ensayo

**Rango analítico y por qué importa para `proteina_c_reactiva_serum`:**
- PCR estándar: diseñada para inflamación/infección aguda, rango útil
  aproximado 8-1000 mg/L (límite de detección bajo ~0.3 mg/L en ensayos
  modernos).
- hs-CRP: rango analítico ~0.3-10 mg/L, diseñada específicamente para
  estratificación de riesgo cardiovascular en inflamación crónica de bajo
  grado.
- Un estudio comparativo de ensayos (Roche, n=570) encontró correlación de
  Spearman 0.988 entre ambos métodos en el rango bajo, con diferencia media
  de solo 0.19 mg/L. Fuente: *Journal of Applied Laboratory Medicine*,
  https://academic.oup.com/jalm/article/7/6/1255/6711152; y NCBI StatPearls,
  "C-Reactive Protein: Clinical Relevance and Interpretation",
  https://www.ncbi.nlm.nih.gov/books/NBK441843/.
- **Conclusión práctica para Analitix:** si el valor de PCR estándar cae
  por debajo de ~10 mg/L y no hay proceso agudo concurrente, es
  numéricamente equiparable a hs-CRP; pero Analitix no tiene forma de saber
  si el laboratorio usó el ensayo hs-CRP o el estándar, ni de descartar un
  proceso agudo concurrente — aplicar el umbral hs-CRP ≥2 mg/L de JUPITER
  sin esa verificación sería un error de interpretación.

**Ensayo JUPITER:** Ridker PM et al. "Rosuvastatin to Prevent Vascular
Events in Men and Women with Elevated C-Reactive Protein." *N Engl J Med*.
2008;359:2195-2207. DOI: 10.1056/NEJMoa0807646.
- Criterio de inclusión: LDL <130 mg/dL **y** hs-CRP ≥2.0 mg/L.
- Población: multinacional (26 países, ~6,515 participantes europeos,
  resto Norteamérica y otros), 17,802 participantes sanos sin ECV previa ni
  diabetes.
- Ictus no fatal como componente del endpoint: HR 0.52 (IC 95% 0.33-0.80,
  p=0.003), ~48% de reducción relativa con rosuvastatina.
- Es un ensayo de intervención (estatina) con criterio de inclusión
  hs-CRP ≥2.0 mg/L, no un estudio de asociación pura ni un punto de corte
  de riesgo aislado.

**Emerging Risk Factors Collaboration:** Kaptoge S, Di Angelantonio E,
Lowe G, et al. "C-reactive protein concentration and risk of coronary
heart disease, stroke, and mortality: an individual participant
meta-analysis." *Lancet*. 2010;375(9709):132-140. DOI:
10.1016/S0140-6736(09)61717-7. PMID: 20031199.
- 116 estudios prospectivos, ~1.2 millones de participantes, mayoritariamente
  Europa y Norteamérica, sin ECV previa al inicio.
- Ictus isquémico como endpoint explícito: 27% mayor riesgo por SD más alta
  de log-CRP.
- **Sin umbral numérico validado** — asociación continua, no hay punto de
  corte clínico específico para ictus en este meta-análisis.

### 2.2 Fibrinógeno

**Fibrinogen Studies Collaboration:** Danesh J et al. "Plasma fibrinogen
level and the risk of major cardiovascular diseases and nonvascular
mortality: an individual participant meta-analysis." *JAMA*.
2005;294(14):1799-1809. PMID: 16219884.
- Población: 154,211 participantes, 31 estudios prospectivos
  (predominantemente Europa y Norteamérica), sin ECV previa; 2,775 casos de
  ictus.
- Asociación cuantitativa: HR ajustado por edad/sexo = 2.06 (IC 95%
  1.83-2.30) por cada incremento de 1 g/L en fibrinógeno habitual; tras
  ajustar por factores de riesgo vascular establecidos, HR ~1.8.
- **Sin umbral numérico validado** — riesgo relativo continuo por g/L, no
  un punto de corte diagnóstico; los propios autores piden más
  investigación para establecer causalidad.

### 2.3 NT-proBNP

Evidencia de **asociación indirecta**, bien documentada pero sin score ni
umbral consensuado:
- Estudio Crypto-AF (Barcelona): NT-proBNP >283 pg/mL combinado con PALS
  <25% se asoció a mayor detección de FA paroxística de alto riesgo
  embólico en seguimiento (35% vs 5.1%, OR 2.33 [1.05-5.13]) — umbral de un
  solo estudio, no validado externamente.
- Meta-análisis (7 estudios, 2,171 pacientes con ictus criptogénico):
  NT-proBNP con AUC 0.80 (IC 95% 0.76-0.83), sensibilidad 81%,
  especificidad 68% para detectar FA subyacente tras ictus criptogénico.
  DOI: 10.3390/pathophysiology31030024 (PMC11270372).
- Estudio pooled BIOSIGNAL/Graz (*Stroke*, DOI:
  10.1161/STROKEAHA.124.049249): relación tiempo-dependiente entre
  NT-proBNP y detección de FA post-ictus.
- **Interpretación honesta:** NT-proBNP eleva la sospecha de FA subclínica
  (que a su vez causa ictus embólico), pero no hay un único umbral
  universal — varía entre estudios. No citar un solo número como
  definitivo.

### 2.4 HbA1c / diabetes

**AHA/ASA 2024 Guideline for the Primary Prevention of Stroke:**
Bushnell C, Kernan WN, Sharrief AZ, et al. *Stroke*. 2024;55(12):e344-e424.
DOI: 10.1161/STR.0000000000000475. PMID: 39429201.
- Diabetes (tipo 1, tipo 2, y prediabetes) es un factor de riesgo
  independiente de ictus; la diabetes se estima que duplica el riesgo.
- Recomienda cribado de prediabetes/diabetes con HbA1c en adultos ≥18 años
  con sobrepeso/obesidad o ECV aterosclerótica (Clase I, C-LD).
- **Hallazgo contraintuitivo importante:** el control glucémico intensivo
  (HbA1c ≤6.5%) **no** ha demostrado beneficio para prevención de ictus
  (Clase III — sin beneficio). En pacientes con diabetes y alto riesgo CV o
  ECV establecida con HbA1c ≥7%, la guía recomienda GLP-1 (Clase I, A) para
  reducir riesgo de ictus, pero esto es sobre tratamiento farmacológico, no
  sobre el valor de HbA1c como marcador de riesgo per se.
- **Umbral numérico:** solo el diagnóstico estándar de diabetes
  (HbA1c ≥6.5%); no hay una curva dosis-respuesta de HbA1c validada
  específicamente para riesgo de ictus más allá del diagnóstico
  diabetes sí/no.

### 2.5 INR / anticoagulación en fibrilación auricular

Verificado de forma independiente para este documento (más allá de lo ya
investigado sobre rangos terapéuticos generales de INR en
`referencias_tiroides_inflamacion_coagulacion.md`):

**Hart RG, Pearce LA, Aguilar MI.** "Meta-analysis: antithrombotic therapy
to prevent stroke in patients who have nonvalvular atrial fibrillation."
*Ann Intern Med*. 2007;146(12):857-867. DOI:
10.7326/0003-4819-146-12-200706190-00007. PMID: 17577005.
- 29 ensayos aleatorizados, 28,044 participantes (edad media 71 años),
  1966-2007, predominio Europa/Norteamérica.
- Warfarina en dosis ajustada (INR objetivo habitual 2.0-3.0) redujo el
  ictus en 64% (IC 95% 49-74%) vs. control/placebo.
- Antiagregantes redujeron el ictus en 22% (IC 95% 6-35%) vs. control;
  warfarina fue 37% superior a antiagregantes (IC 95% 23-48%).
- Contrapartida: hemorragia intracraneal el doble que con aspirina
  (+0.2%/año).

**2023 ACC/AHA/ACCP/HRS Guideline for the Diagnosis and Management of
Atrial Fibrillation.** *Circulation*. DOI: 10.1161/CIR.0000000000001193.
PMID: 38033089 (actualiza la guía 2014, DOI: 10.1161/CIR.0000000000000041).
- Para FA no valvular con ictus/AIT previo o CHA2DS2-VASc ≥2:
  anticoagulación oral recomendada; warfarina con INR objetivo 2.0-3.0
  listada como opción (nivel de evidencia A).

**Conclusión:** evidencia sólida y umbral numérico citable — INR
terapéutico 2.0-3.0 en FA no valvular reduce el riesgo de ictus, respaldado
por meta-análisis de ensayos y guía de sociedad profesional vigente. Pero
esto es sobre **tratamiento** de un paciente ya diagnosticado de FA y
anticoagulado, no un umbral de riesgo aplicable a un INR aislado sin saber
la indicación del paciente — reafirma la conclusión ya alcanzada en
`referencias_tiroides_inflamacion_coagulacion.md`: no colorear
automáticamente el INR sin conocer la indicación clínica.

---

## 3. Marcadores con evidencia débil, contradictoria o sin umbral aplicable

### 3.1 Ácido úrico (`urat_serum`)

Asociación positiva consistente en dos meta-análisis grandes, pero con
relación **no lineal (en J)** y sin umbral de riesgo validado:
- Dong Y, Shi H, Chen X, et al. "Serum uric acid and risk of stroke: a
  dose-response meta-analysis." *J Clin Biochem Nutr*. 2021;68(3):221-227.
  DOI: 10.3164/jcbn.20-94. PMID: 34025024. 21 cohortes, 818,098
  participantes. RR = 1.22 (IC 95% 1.15-1.30) alto vs. bajo; nadir de
  riesgo en 3-5 mg/dL.
- Qiao T, Wu H, Peng W. "The Relationship Between Elevated Serum Uric Acid
  and Risk of Stroke in Adult: An Updated and Dose-Response Meta-Analysis."
  *Front Neurol*. 2021;12:674398. DOI: 10.3389/fneur.2021.674398.
  PMID: 34526951. 19 cohortes, ~68,549 participantes. Por 1 mg/dL de
  aumento: ictus isquémico HR 1.15 (1.10-1.21), hemorrágico HR 1.07
  (1.00-1.15, límite de significación).
- **Nota — no confundir dos endpoints distintos:** existe una "paradoja del
  ácido úrico" en el **pronóstico post-ictus** (ácido úrico alto asociado a
  mejor recuperación funcional, efecto antioxidante agudo), que es un
  endpoint distinto de la incidencia de ictus y no debe mezclarse.
- **Veredicto:** asociación consistente pero relación en J, sin umbral de
  riesgo validado — no implementar como score directo.
- **Nota:** `urat_serum` sí está implementado en Analitix, pero con una
  indicación completamente distinta a la de ictus — como marcador de
  hiperuricemia (`uric_acid_risk.py`, pestaña "🩹 Ácido úrico"), usando el
  umbral oficial de la American College of Rheumatology (≥6.8 mg/dL) para
  hiperuricemia asintomática, no ningún umbral relacionado con riesgo de
  ictus. Esta sección sigue vigente para su conclusión: no usar el ácido
  úrico como marcador de riesgo de ictus.

### 3.2 Potasio sérico (`potassi`)

**Evidencia contradictoria en dirección según la población** — no
implementar:
- Johnson LS et al. "Serum Potassium Is Positively Associated With Stroke
  and Mortality in the Large, Population-Based Malmö Preventive Project
  Cohort." *Stroke*. 2017;48(11):2973-2978. DOI:
  10.1161/STROKEAHA.117.018148. PMID: 28974633. Población general sueca
  sana, n=21,353, seguimiento 26.9 años: potasio **más alto** asociado a
  **más** riesgo (HR 1.33 por mmol/L).
- Green DM et al. (Cardiovascular Health Study). "Serum potassium level and
  dietary potassium intake as risk factors for stroke." *Neurology*.
  2002;59(3):314-320. DOI: 10.1212/WNL.59.3.314. PMID: 12177362. En
  usuarios de diuréticos >65 años, potasio **bajo** (<4.1 mEq/L) asociado a
  **más** riesgo (RR 2.5) — dirección **opuesta** al estudio anterior.
- Smith NL et al. "Serum potassium and stroke risk among treated
  hypertensive adults." *Am J Hypertens*. 2003;16(10):806-813. DOI:
  10.1016/S0895-7061(03)00983-X. PMID: 14553958. Hipopotasemia
  (≤3.4 mmol/L) en hipertensos tratados asociada a más riesgo (OR
  isquémico 2.04, hemorrágico 3.29) — misma dirección opuesta a Malmö.
- **Veredicto:** el sentido de la asociación se invierte según la
  población (sana vs. hipertensa tratada/con diuréticos); no hay consenso
  ni umbral único. No implementar.

### 3.3 Sodio sérico (`sodi`)

**Evidencia escasa, un solo estudio relevante con endpoint compuesto** —
no implementar:
- Wannamethee SG et al. "Mild hyponatremia, hypernatremia and incident
  cardiovascular disease and mortality in older men." *Nutr Metab
  Cardiovasc Dis*. 2016;26(1):12-19. DOI: 10.1016/j.numecd.2015.07.008.
  PMID: 26298426. Varones británicos 60-79 años, n=3,099, seguimiento 11
  años, 528 eventos CV mayores (IAM + ictus + muerte CV **combinados**, no
  ictus aislado). Relación en U: hiponatremia (<136 mEq/L) HR 1.55,
  sodio bajo-normal (136-138) HR 1.40, hipernatremia (≥145) también
  elevada, vs. referencia 139-143 mEq/L.
- **Nota — no confundir con pronóstico post-ictus:** la abundante
  literatura sobre hiponatremia y mal pronóstico *tras* un ictus (SIADH,
  síndrome pierde-sal cerebral en fase aguda) es un endpoint distinto
  (pronóstico, no riesgo prospectivo) y no debe usarse aquí.
- **Veredicto:** evidencia débil, sin umbral de riesgo de ictus específico
  validado. No implementar.

### 3.4 RDW (`rdw_cv`)

Asociación consistente en grandes meta-análisis, pero **sin punto de corte
único validado externamente**:
- Song SY et al. "Baseline Red Blood Cell Distribution Width as a
  Predictor of Stroke Occurrence and Outcome: A Comprehensive Meta-Analysis
  of 31 Studies." *Front Neurol*. 2019;10:1237. DOI:
  10.3389/fneur.2019.01237. PMID: 31849813. 31 estudios, 3,487,896
  pacientes. RDW elevado como factor de riesgo de ictus isquémico: OR/RR
  1.528 (IC 95% 1.372-1.703); también asociado a peor resultado funcional y
  mayor mortalidad.
- Xie KH et al. "Red cell distribution width: a novel predictive biomarker
  for stroke risk after transient ischaemic attack." *Ann Med*.
  2022;54(1):1167-1177. DOI: 10.1080/07853890.2022.2059558. PMID: 35471128.
  Cohorte china, n=360 con AIT: RDW≥13.95% → OR 2.52 de progresión a ictus
  isquémico. AUC 0.731, superior al score clínico ABCD² (0.613) — pero
  validado solo en esta cohorte pequeña, sin replicación externa del mismo
  corte.
- **Veredicto:** asociación consistente en múltiples cohortes grandes, pero
  el único punto de corte numérico encontrado (13.95%) proviene de un
  estudio pequeño no replicado — usar como mucho como factor de alerta
  cualitativo (mismo patrón que el resto de índices de hemograma en
  `referencias_hemograma.md`), nunca como score cuantitativo de riesgo.

### 3.5 Plaquetas (`plaquetes`) y VPM (`vpm`)

Evidencia mixta, con matices importantes de causalidad:
- Sadeghi F et al. "Platelet count and mean volume in acute stroke: a
  systematic review and meta-analysis." *Platelets*. 2020;31(6):731-739.
  DOI: 10.1080/09537104.2019.1680826. PMID: 31657263. 34 estudios: recuento
  plaquetario **menor** en ictus agudo vs. controles (comparación
  transversal), VPM **mayor** en ictus agudo. **Limitación clave:** son
  comparaciones en el momento agudo del ictus, no predicción con valor
  basal previo — posible causalidad inversa (el propio ictus activa/consume
  plaquetas).
- Bath P, Algert C, Chapman N, Neal B (PROGRESS Collaborative Group).
  "Association of mean platelet volume with risk of stroke among 3134
  individuals with history of cerebrovascular disease." *Stroke*.
  2004;35(3):622-626. DOI: 10.1161/01.STR.0000116105.26237.EC.
  PMID: 14976328. Ensayo PROGRESS, n=3,134, **todos con ictus/AIT previo**
  (prevención secundaria, no primaria): VPM basal predijo ictus recurrente,
  +11% de riesgo relativo (IC 95% 3%-19%) por cada fL de aumento.
- **Veredicto:** VPM tiene evidencia prospectiva real, pero solo demostrada
  en prevención **secundaria** (pacientes que ya tuvieron ictus/AIT) — no
  hay score validado para población general/prevención primaria. El
  recuento plaquetario aislado tiene evidencia débil y probablemente
  reactiva (no predictiva). No implementar ninguno como score de riesgo
  primario.

---

## Recomendación final

| Elemento | Implementable hoy | Motivo |
|---|---|---|
| CHA2DS2-VASc | No | Requiere FA diagnosticada + antecedentes clínicos; 6/8 variables no analíticas |
| Framingham Stroke Risk Profile | No | Presión arterial sistólica obligatoria (variable de mayor peso); tabaquismo/ECV previa también obligatorios |
| Pooled Cohort Equations (ACC/AHA) | Parcial, no aislable | Colesterol total+HDL sí son de lab, pero PAS/tabaquismo/diabetes clínica son obligatorios; predice ASCVD compuesta, no ictus aislado; población EE.UU. |
| SCORE2/SCORE2-OP | Parcial, no aislable | Mismo patrón que PCE; población europea (más aplicable geográficamente), pero PAS y tabaquismo siguen siendo obligatorios |
| hs-CRP (JUPITER, ERFC) | No como score de riesgo | Asociación real con ictus, pero sin umbral aislado aplicable y con el problema añadido de no saber si el PCR de Analitix es hs-CRP o estándar |
| Fibrinógeno | No | Asociación real (HR ~1.8-2.06/g/L) pero sin umbral numérico validado |
| NT-proBNP | No | Asociación indirecta vía FA subclínica, sin umbral universal |
| HbA1c/diabetes | Parcial | Solo el diagnóstico de diabetes (HbA1c ≥6.5%) está respaldado como factor de riesgo; no hay curva dosis-respuesta validada de HbA1c para riesgo de ictus, y bajar la HbA1c agresivamente no reduce el riesgo (AHA/ASA 2024) |
| INR/anticoagulación en FA | No como umbral de riesgo | Evidencia sólida (Hart 2007, guía 2023) pero sobre tratamiento de un paciente ya diagnosticado y anticoagulado, no sobre interpretar un INR aislado sin conocer la indicación |
| Ácido úrico (`urat_serum`) | No | Asociación consistente pero relación en J, sin umbral validado |
| Potasio (`potassi`) | No | Evidencia contradictoria en dirección según población |
| Sodio (`sodi`) | No | Evidencia débil, un solo estudio con endpoint compuesto |
| RDW (`rdw_cv`) | No como score, sí como texto cualitativo | Asociación consistente en grandes meta-análisis, pero corte (13.95%) no validado externamente |
| Plaquetas/VPM | No | VPM solo validado en prevención secundaria; recuento plaquetario con evidencia débil/reactiva |

**Conclusión general: no hay ningún cálculo de riesgo de ictus
implementable hoy en Analitix con garantías científicas equivalentes a
Castelli I/II, APRI o eAG.** A diferencia de esas ideas ya implementadas o
investigadas, aquí:
1. Los cuatro scores compuestos investigados necesitan **tensión arterial**
   como mínimo (dato que Analitix no guarda y nunca vendrá de un PDF de
   analítica de sangre), y la mayoría también tabaquismo y antecedentes
   clínicos (FA, ictus/AIT previo, ECV previa) — mismo bloqueador ya
   identificado para el riesgo cardiovascular general: registrar tensión
   arterial no está implementado.
2. Los marcadores individuales con asociación real y sólida (hs-CRP,
   fibrinógeno, NT-proBNP) no tienen un umbral numérico único y
   consensuado que se pueda convertir en una clasificación de riesgo — solo
   en "a mayor valor, mayor riesgo relativo", que no es suficiente para un
   semáforo o índice como los ya implementados.
3. HbA1c/diabetes sí tiene una base sólida como factor de riesgo, pero el
   umbral aplicable es el mismo umbral diagnóstico de diabetes que ya usa
   la app para otros fines (`referencias_hierro_glucosa.md`), no un umbral
   nuevo específico de ictus — no aporta un cálculo adicional.
4. INR y anticoagulación en FA reafirman (no contradicen) la conclusión ya
   alcanzada en `referencias_tiroides_inflamacion_coagulacion.md`: no
   colorear el INR contra un umbral fijo sin conocer la indicación clínica
   del paciente.
5. Ácido úrico, potasio, sodio, RDW y plaquetas/VPM tienen evidencia débil,
   contradictoria, no lineal, o solo válida en prevención secundaria —
   ninguno debe convertirse en un aviso o índice de riesgo de ictus.

**Si en el futuro se implementa el registro de tensión arterial y datos
demográficos (sexo, tabaquismo)**, el candidato más razonable para
revisar de nuevo sería **SCORE2/SCORE2-OP** (población europea, la más
aplicable geográficamente de las cuatro), aunque seguiría prediciendo ECV
compuesta y no ictus aislado. Hasta entonces, lo único defendible es
mostrar hs-CRP, fibrinógeno y NT-proBNP como series de Evolución con una
nota descriptiva de su asociación general con riesgo vascular (mismo
patrón ya usado para PCR/VSG en `referencias_tiroides_inflamacion_coagulacion.md`),
nunca como un score, semáforo o índice numérico de riesgo de ictus.
