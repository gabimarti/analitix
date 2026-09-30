# Avisos de seguridad orientativos: hemograma y neoplasias hematológicas

> Parte de [`docs/referencias_medicas/`](README.md) — ver también
> [`docs/DOCUMENTACION_TECNICA.md`](../DOCUMENTACION_TECNICA.md) (sección
> `hemogram_risk.py`, donde vive el aviso de linfocitosis sostenida).

De las ideas descritas en la "Recomendación honesta" (§ final), está
implementado el aviso de linfocitosis sostenida > 5×10⁹/L en ≥2 informes —
en `hemogram_risk.py` (`LYMPHOCYTOSIS_HIGH`,
`get_sustained_lymphocytosis_alert`) y
`data/descripciones/aviso_linfocitosis.txt`. Investigación europea
adicional que respalda el umbral (coincide con el propuesto aquí a
partir de la guía escocesa, ver § "4. Umbrales numéricos..." más abajo):

- **ESMO Clinical Practice Guidelines** (guía europea de referencia,
  autores de Alemania, Polonia, España, Italia, Dinamarca, Países Bajos,
  Suiza, Francia y Reino Unido): Eichhorst B, Robak T, Montserrat E, Ghia
  P, Niemann CU, Kater AP, Gregor M, Cymbalista F, Buske C, Hillmen P,
  Hallek M, Mey U. "Chronic lymphocytic leukaemia: ESMO Clinical Practice
  Guidelines for diagnosis, treatment and follow-up." *Ann Oncol*.
  2021;32(1):23-33. doi:10.1016/j.annonc.2020.09.019 (citación verificada
  vía PubMed/NCBI eutils, PMID 33091559).
- **iwCLL 2018**: Hallek M, Cheson BD, Catovsky D, et al. "iwCLL
  guidelines for diagnosis, indications for treatment, response
  assessment, and supportive management of CLL." *Blood*.
  2018;131(25):2745-2760. doi:10.1182/blood-2017-09-806398 — fuente del
  umbral diagnóstico LLC/MBL de ≥5×10⁹/L linfocitos B clonales, adoptado
  por la guía ESMO (Hallek es coautor de ambas).

Sigue vigente, y se documenta explícitamente en el propio aviso de la
app: el umbral de las guías se aplica a linfocitos B **clonales** (por
citometría de flujo), mientras que Analitix solo tiene el recuento total;
y las guías exigen valorar el resultado junto con síntomas/exploración
física que Analitix no registra — así que el aviso es puramente
informativo ("coméntalo con tu médico"), nunca una sospecha de LLC.

Más allá del aviso de linfocitosis ya implementado, no hay ningún score o
índice combinado de riesgo de neoplasia hematológica — no existe ninguno
validado en la literatura. Mismo principio que el resto de la app y en
particular que `lipid_risk.py`: esto es **apoyo informativo y de
seguimiento, nunca un diagnóstico ni un "detector de leucemia"**. Un
hemograma normal no descarta nada, y una alteración aislada
casi nunca significa cáncer — las propias guías citadas abajo lo dicen
explícitamente. El objetivo, si se implementa algo, es señalar cuándo
**vale la pena comentar el resultado con un médico**, no estimar una
probabilidad de enfermedad.

## Parámetros de Analitix implicados

Confirmado mirando `src/analitix/data/descripciones/` (no de memoria):
existen fichas para `hemoglobina`, `hematocrit`, `hematies`, `vcm`, `hcm`,
`chcm`, `rdw_cv`, `leucocits`/`leucocits_calculats`, `neutrofils`/
`neutrofils_total`, `limfocits`/`limfocits_total`, `monocits`/
`monocits_total`, `eosinofils`/`eosinofils_total`, `basofils`/
`basofils_total`, `plaquetes`, `vpm`.

**Limitación importante, confirmada mirando el mismo directorio**: Analitix
**no tiene** un `canonical_id` de recuento de blastos ni de células
inmaduras (`grep -il "blast"` sobre `data/descripciones/` no da ningún
resultado) — el único parámetro relacionado con morfología leucocitaria es
`morfologia_leucocitaria_predomini_de_limfocits_petits_amb_cromatina_condensada_i_escas.txt`,
una anotación de texto libre del laboratorio ("descripción... del aspecto
de los glóbulos blancos observados al microscopio; no es un valor
numérico"), y además `docs/DOCUMENTACION_TECNICA.md` ya documenta que este
tipo de comentario narrativo sin código LOINC **no se parsea de forma
fiable** (se guarda a veces con `value_num=None` o se descarta). Esto
importa mucho: los blastos circulantes son uno de los hallazgos más
específicos de leucemia aguda en un hemograma, y Analitix hoy no puede
verlos de forma estructurada — cualquier cosa que se implemente solo podrá
trabajar con los recuentos numéricos de las series roja/blanca/plaquetas,
nunca con morfología.

**Otra limitación pendiente de verificar antes de implementar nada**: no se
ha podido comprobar contra la base de datos real (cifrada, sin contraseña)
en qué unidad guarda este laboratorio los recuentos celulares. Los umbrales
NHS citados abajo usan unidades SI (×10⁹/L para leucocitos/plaquetas, g/L
para hemoglobina); si el laboratorio de Analitix usa otra convención (p.ej.
g/dL para hemoglobina, muy habitual en España, o ×10³/µL para recuentos),
haría falta convertir con cuidado — mismo tipo de comprobación que ya hace
`lipid_risk._mg_dl` para el perfil lipídico, para no mezclar cifras que no
son comparables.

## Guías y estudios verificados

### 1. NICE NG12 — "Suspected cancer: recognition and referral" (Reino Unido)

National Institute for Health and Care Excellence. *Suspected cancer:
recognition and referral* (NG12). Actualizado 2025. Sección 1.10
(leucemia). Mirror consultado (NIH/NCBI Bookshelf, texto verificado):
https://www.ncbi.nlm.nih.gov/books/NBK555330/

Cita textual de las recomendaciones de leucemia:

- **1.10.1 (adultos)** — considerar un hemograma muy urgente (en 48 horas)
  ante: *"pallor, persistent fatigue, unexplained fever, unexplained
  persistent or recurrent infection, generalised lymphadenopathy,
  unexplained bruising, unexplained bleeding, unexplained petechiae,
  hepatosplenomegaly"* (palidez, fatiga persistente, fiebre inexplicada,
  infección persistente o recurrente inexplicada, adenopatías
  generalizadas, hematomas inexplicados, sangrado inexplicado, petequias
  inexplicadas, hepatoesplenomegalia).
- **1.10.2 (niños y adolescentes)** — derivación inmediata a especialista
  ante: *"unexplained petechiae or hepatosplenomegaly"*.
- **1.10.3 (niños y adolescentes)** — hemograma muy urgente (48h) ante:
  *"pallor, persistent fatigue, unexplained fever, unexplained persistent
  infection, generalised lymphadenopathy, persistent or unexplained bone
  pain, unexplained bruising, unexplained bleeding"*.

**Por qué esto NO se traduce directamente en un cálculo para Analitix**:
estas recomendaciones indican **cuándo pedir** un hemograma a partir de
**síntomas clínicos** (fatiga, fiebre, sangrado, dolor óseo...) que
Analitix no registra en absoluto — la app solo tiene el resultado numérico
final, nunca el motivo de consulta ni la exploración física. NG12 no da,
en esta sección, un umbral numérico de "si el hemograma da tal resultado,
deriva" — ese es un problema distinto (ver punto 3).

### 2. Revisión clínica: valor predictivo de un hemograma alterado

Hamilton W. "Leukaemia diagnosis and primary care." *Br J Gen Pract*.
2024;74(739):54–55. DOI: 10.3399/bjgp24X736149.
https://pmc.ncbi.nlm.nih.gov/articles/PMC10824351/ (verificado el texto vía
fetch directo del artículo).

Puntos clave, citados textualmente donde procede:

- *"nearly all patients have an abnormal full blood count"* (en pacientes
  con leucemia ya diagnosticada) — el hemograma es sensible como prueba de
  cribado inicial.
- Pero el reto no es la prueba en sí: *"the reason for delays in diagnosis
  is the selection of who to test rather than not knowing how to test"* —
  es decir, el problema real es decidir a quién pedirle un hemograma
  (síntomas inespecíficos), no interpretar el resultado una vez que existe.
- Los síntomas típicos (fatiga, sudores nocturnos, dolor óseo/articular)
  tienen, individualmente, *"a very low risk of leukaemia, well below a
  positive predictive value of 1%"*.
- Datos de acceso reales: solo un tercio de los pacientes con leucemia
  recibieron un análisis de sangre tras su primera consulta por síntomas, y
  casi una cuarta parte de las leucemias agudas tuvo retrasos de hasta 4
  meses en conseguir ese análisis.

### 3. Estudio caso-control: síntomas antes del diagnóstico

Shephard EA, Neal RD, Rose PW, Walter FM, Hamilton W. "Symptoms of adult
chronic and acute leukaemia before diagnosis: large primary care
case-control studies using electronic records." *Br J Gen Pract*.
2016;66(644):e182-8. DOI: 10.3399/bjgp16X683989.
https://bjgp.org/content/66/644/e182 (cita/hallazgos verificados vía
búsqueda cruzada, la web del artículo en sí no sirvió el cuerpo completo al
fetch directo).

- 10 síntomas asociados de forma independiente a leucemia crónica; los 3
  más fuertes: adenopatías (OR 22, IC95% 13–36), pérdida de peso (OR 3.0,
  IC95% 2.1–4.2), hematomas (OR 2.3, IC95% 1.6–3.2).
- 13 síntomas asociados a leucemia aguda; los 3 más fuertes: epistaxis/
  sangrado de encías (OR 5.7), fiebre (OR 5.3), fatiga (OR 4.4).
- **Hallazgo central, muy relevante para Analitix**: *"No individual
  symptom or combination of symptoms had a PPV >1%"* — ningún síntoma ni
  combinación de síntomas superó el 1% de valor predictivo positivo. Los
  autores también apuntan que alteraciones hematológicas de la leucemia
  linfocítica crónica (CLL) pueden detectarse hasta 10 años antes del
  diagnóstico (linfocitosis monoclonal de células B como precursora), lo
  que sugiere que un **recuento de leucocitos/linfocitos elevado y
  sostenido en el tiempo** podría ser una señal más temprana que cualquier
  síntoma — pero esto es una observación de los autores sobre la
  posibilidad de alertas de software, no un score validado ni un umbral
  concreto que se pueda citar como tal.

### 4. Umbrales numéricos de hemograma en rutas de derivación reales del NHS

A diferencia de NG12 (basado en síntomas), estas guías sí dan **umbrales
numéricos sobre el propio resultado del hemograma**, más cercanos a lo que
Analitix podría calcular — aunque son guías locales/regionales, no un
estándar único a nivel de Reino Unido, y coinciden en un mensaje común: una
cifra aislada, sin más contexto clínico, no debe disparar una alerta por sí
sola.

**Escocia — Right Decisions / Scottish Referral Guidelines for Suspected
Cancer, "Haematological cancers"** (Centre for Sustainable Delivery, NHS
Scotland). https://www.rightdecisions.scot.nhs.uk/scottish-referral-guidelines-srgs-for-suspected-cancer/haematological-cancers/
(verificado vía fetch directo).

- **Emergencia (mismo día)**: hemograma/frotis informado como sugestivo de
  leucemia aguda o leucemia mieloide crónica.
- **Derivación urgente (USC)**: linfocitosis > 5×10⁹/L **junto con**
  cualquiera de: pérdida de peso, fiebre o sudoración nocturna profusa
  ("síntomas B"); adenopatías y/o esplenomegalia; o citopenia asociada
  (hemoglobina < 100 g/L, neutrófilos < 1.0×10⁹/L, o plaquetas <
  100×10⁹/L).
- **Aviso explícito de la propia guía** (cita relevante para el diseño de
  cualquier alerta en Analitix): las alteraciones analíticas aisladas
  (linfocitosis sola, o paraproteína elevada sola) **no deben** disparar
  una derivación urgente sin otras características clínicas presentes.

**Inglaterra — North Yorkshire and York, "Haematological cancer pathway"**
(York and Scarborough Teaching Hospitals NHS Foundation Trust, repositorio
HNY Policy and Pathway, última modificación 18/08/2026).
https://hnyppr.org.uk/web/north-yorkshire-and-york/w/haematological-cancer-pathway
(verificado vía fetch directo).

- **Leucemia linfocítica crónica**: derivar si hemoglobina < 10 g/dL o
  plaquetas < 100×10⁹/L, junto con síntomas (sudores nocturnos, cansancio,
  pérdida de peso inexplicada).
- **Leucemia aguda**: sin umbral numérico propio — contacto inmediato con
  el hematólogo de guardia ante un patrón de hemograma sugestivo (de nuevo,
  remite a la valoración clínica/del especialista, no a una cifra sola).
- Objetivo del propio sistema: ver y diagnosticar en un plazo de 28 días
  tras la derivación — dato de contexto, no aplicable a Analitix.

## Recomendación honesta

**No existe** en la literatura consultada un score o índice combinado,
validado y citable, que tome varios parámetros del hemograma rutinario y
devuelva una probabilidad o clasificación de riesgo de leucemia — a
diferencia del perfil lipídico (§1, ya implementado), donde sí hay índices
publicados con puntos de corte numéricos (Castelli I/II, TG/HDL). Lo que
existe son:

1. Guías de **cuándo pedir** un hemograma a partir de síntomas (NG12) —
   inaplicable a Analitix porque no registra síntomas.
2. Guías locales del NHS con **umbrales numéricos sobre el resultado**
   (linfocitosis, citopenias) — aplicables en principio a los datos que sí
   tiene Analitix, pero **siempre condicionadas a síntomas o hallazgos
   clínicos que la app tampoco registra** (síntomas B, adenopatías,
   esplenomegalia), y explícitamente no pensadas para disparar nada por sí
   solas.
3. Evidencia sólida de que los síntomas aislados tienen **PPV por debajo
   del 1%** — y por extensión, cualquier alerta basada solo en cifras de
   laboratorio, sin el contexto clínico que las acompaña en las guías
   reales, tendrá una especificidad todavía peor.

**Qué sería razonable implementar, si se retoma esta idea**: no un
"índice de riesgo de leucemia", sino, como mucho, una lista de **avisos de
seguridad puramente informativos** (en la línea de lo que ya hace la app
con el marcador ⚠ de fuera de rango) para patrones **poco frecuentes y
objetivamente descritos en estas guías** — p. ej. "linfocitos > 5×10⁹/L
sostenido en más de un informe" o "dos o más series celulares con
citopenia a la vez" — siempre con: (a) el texto explícito de que esto NO
sustituye la valoración clínica y de que las propias guías exigen contexto
que la app no tiene; (b) la cita completa a la guía de origen; (c) nunca
una cifra de "probabilidad" ni un semáforo que suene a diagnóstico. Antes
de escribir cualquier código habría que además: confirmar la unidad real
de estos parámetros en la base de datos (ver limitación de unidades más
arriba) y decidir qué hacer con el hecho de que Analitix no tiene datos de
blastos ni de síntomas — el propio README/documentación debería dejar
clarísimo que esta limitación existe.

**Qué NO se debería implementar**: cualquier cosa que combine varios
parámetros en un único número o porcentaje de "riesgo de leucemia" (no hay
ninguna fórmula así validada en la literatura, a diferencia del perfil
lipídico), cualquier alerta basada en morfología/blastos (Analitix no
extrae ese dato de forma fiable, ver limitación arriba), y cualquier
redacción que use la palabra "detectar" o "diagnosticar" en vez de
"comentar con tu médico si...".
