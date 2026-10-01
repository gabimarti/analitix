# Referencias verificadas — metabolismo del hierro y metabolismo glucídico

> Parte de [`docs/referencias_medicas/`](README.md) — ver también
> [`docs/DOCUMENTACION_TECNICA.md`](../DOCUMENTACION_TECNICA.md) (secciones
> `iron_risk.py` y `glycemic_risk.py`).

Mismo criterio que `src/analitix/lipid_risk.py`: toda fórmula/umbral aquí
está verificado contra una fuente real (no de memoria) con su URL. El
metabolismo del hierro está implementado en `src/analitix/iron_risk.py`
(pestaña "🩸 Metabolismo del hierro"); el metabolismo glucídico (eAG desde
HbA1c) está implementado en `src/analitix/glycemic_risk.py` (pestaña
"🍬 Glucosa media estimada (eAG)").

## Metabolismo del hierro — implementado

Se implementaron ferritina y TSAT (con su fórmula de relleno cuando el
informe no la trae calculada), tal y como recomendaba esta investigación:
mostrando los valores clasificados por separado y la tabla combinada de
abajo como referencia en texto, **sin automatizar** el diagnóstico
diferencial. Verificado además contra los 39 PDF reales del proyecto que
`ferro`/`ferritina`/`transferrina` existen con y sin el sufijo "sèrum"
según la época de la plantilla (mismo parámetro, `canonical_id` distinto,
fusionados en el código), y que la TSAT también aparece bajo el
`canonical_id` genérico `saturacio` en la plantilla de 2014.

Parámetros de Analitix implicados: `ferro_serum` (hierro sérico, µg/dL),
`ferritina_serum` (ferritina, ng/mL ≈ µg/L), `transferrina_serum`
(transferrina, mg/dL), `saturacio_transferrina_serum` (saturación de
transferrina, %, normalmente ya calculada por el laboratorio).

### Fórmula de saturación de transferrina (fallback si el informe no la trae)

`TSAT (%) = [Hierro (µg/dL) ÷ (Transferrina (mg/dL) × 1.41–1.42)] × 100`

El factor 1.41–1.42 viene de la capacidad de fijación de hierro de la
transferrina (~1.40–1.49 mg de hierro por gramo de transferrina) — ver
Wikipedia, "Total iron-binding capacity" (base bioquímica del factor,
consistente entre fuentes):
https://en.wikipedia.org/wiki/Total_iron-binding_capacity
La fórmula exacta con el factor 1.42 aparece también en un apéndice de
protocolo de ensayo clínico público (NCT03920657, Appendix G):
"Transferrin saturation calculation [Serum iron / (serum transferrin x
1.42)] x 100". Como la inmensa mayoría de los informes del laboratorio ya
traen `saturacio_transferrina_serum` calculada, esta fórmula solo sería
necesaria como relleno para algún informe antiguo/atípico que la omita —
mismo patrón que el LDL por Friedewald en `lipid_risk.py`.

**Umbrales orientativos de saturación de transferrina:**
- Bajo (sugiere ferropenia): < 20%. University of Iowa, Department of
  Pathology, "Iron Panel (IRON, TRANSFERRIN, TIBC and % SATURATION)":
  https://www.healthcare.uiowa.edu/path_handbook/handbook/test1151.html
- Alto (sugiere sobrecarga de hierro / hemocromatosis): > 45–50% es motivo
  de estudio; en hemocromatosis hereditaria establecida suele ser > 60%, y
  > 90% en sobrecarga avanzada. Medscape, "Transferrin Saturation:
  Reference Range, Interpretation, Collection and Panels":
  https://emedicine.medscape.com/article/2087960-overview
- Rango de referencia general (sin enfermedad): hombres 20–50%, mujeres
  15–50% (mismo Iowa Path Handbook, enlace arriba).

### Umbrales orientativos de ferritina

- Ferropenia **sin inflamación/infección** (población sana): ferritina
  < 15 µg/L en adultos no embarazadas, < 12 µg/L en niños menores de 5
  años. WHO, "WHO guideline on use of ferritin concentrations to assess
  iron status in individuals and populations", Geneva, 2020 (umbrales de
  1993 revalidados por opinión de expertos, certeza de evidencia baja/muy
  baja — el propio documento lo señala como limitación):
  https://www.ncbi.nlm.nih.gov/books/NBK569877/
- Ferropenia **con inflamación/infección** (ferritina puede estar
  falsamente normal o alta): usar un umbral más alto, < 70 µg/L en adultos
  (< 30 µg/L en niños) — mismo documento OMS 2020. Recomienda además medir
  PCR (que Analitix ya guarda como `proteina_c_reactiva_serum`, ver §9 de
  la lista de ideas) en paralelo para saber si aplica el umbral "con
  inflamación".
- Sobrecarga de hierro / hemocromatosis: ferritina elevada junto con TSAT
  elevada (patrón opuesto al de ferropenia) — ver algoritmo combinado
  abajo. Fuente general del carácter de reactante de fase aguda de la
  ferritina: Kell DB, Pretorius E. "Serum ferritin is an important
  inflammatory disease marker, as it is mainly a leakage product from
  damaged cells." Metallomics. 2014 — citado y desarrollado en:
  "Limitations of Serum Ferritin in Diagnosing Iron Deficiency in
  Inflammatory Conditions." PMC5878890:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC5878890/

### Algoritmo combinado ferritina + TSAT (orientativo)

Patrón sintetizado a partir de las fuentes anteriores (WHO 2020, Medscape,
PMC5878890) — no existe una única tabla "oficial" que combine las tres
categorías en una sola fuente, así que esto es una síntesis razonada, a
marcar como tal en la ficha de descripción si se implementa:

| Patrón | Ferritina | TSAT | Interpretación orientativa |
|---|---|---|---|
| Ferropenia | Baja (< 15 µg/L) | Baja (< 20%) | Combinación más específica de ferropenia real |
| Anemia de trastorno crónico | Normal/alta | Baja/normal | Ferritina elevada por inflamación, enmascara la ferropenia |
| Ferropenia + inflamación concurrente | "Normal" pero < 70 µg/L | Baja (< 20%) | Ferropenia funcional/restringida — criterio WHO 2020 con inflamación |
| Sobrecarga de hierro / hemocromatosis | Alta | Alta (> 45–50%) | Requiere estudio (genético u otra causa: transfusiones repetidas) |

**Limitación importante a documentar igual que en `lipid_risk.py`**: esto
es apoyo informativo, no diagnóstico — la ferritina sube con cualquier
proceso inflamatorio/infeccioso/hepático (no solo con sobrecarga de
hierro), así que un valor alto aislado no implica hemocromatosis, y uno
"normal" no descarta ferropenia si hay inflamación concurrente. Analitix
no guarda de forma estructurada si el paciente tiene un proceso
inflamatorio activo, así que como mucho se puede avisar de la ambigüedad
citando PCR si está disponible en el mismo informe.

### Recomendación de implementación

- Coste bajo, valor medio: mostrar ferritina + TSAT lado a lado con la
  clasificación orientativa de la tabla de arriba (mismo patrón que el
  panel lipídico: `_mg_dl`-equivalente para validar unidades, sin inventar
  ningún valor que el informe no traiga). La fórmula de TSAT por
  transferrina+hierro solo como fallback si `saturacio_transferrina_serum`
  falta ese día.
- No implementar (todavía) un algoritmo automático que "decida" entre
  ferropenia/trastorno crónico/sobrecarga: al no guardar Analitix ningún
  marcador de inflamación activa de forma estructurada (PCR es un
  parámetro más entre otros, no un flag), un algoritmo automático podría
  sugerir con más seguridad de la debida una interpretación que en
  realidad depende de contexto clínico no disponible. Mejor mostrar los
  valores + umbrales + la tabla como referencia en la ficha de
  descripción, dejando la síntesis final al usuario/médico.

## Metabolismo glucídico

Parámetros de Analitix implicados: `glucosa_serum` (glucosa, mg/dL),
`hb_glicosilada_hba1c_sang` (HbA1c, %).

### Fórmula ADAG de glucosa media estimada (eAG)

`eAG (mg/dL) = 28.7 × HbA1c(%) − 46.7`

Verificada contra la publicación original: Nathan DM, Kuenen J, Borg R,
Zheng H, Schoenfeld D, Heine RJ, for the A1c-Derived Average Glucose
(ADAG) Study Group. "Translating the A1C Assay Into Estimated Average
Glucose Values." Diabetes Care. 2008;31(8):1473-1478.
DOI: 10.2337/dc08-0545. PMID: 18540046.
https://diabetesjournals.org/care/article/31/8/1473/28589/Translating-the-A1C-Assay-Into-Estimated-Average
Estudio: 507 sujetos (268 con diabetes tipo 1, 159 tipo 2, 80 sin
diabetes), ~2700 valores de glucosa por sujeto combinando monitorización
continua + autocontrol capilar durante ~3 meses; regresión lineal
HbA1c↔glucosa media, R² = 0.84. Fórmula adoptada oficialmente por la ADA
(calculadora eAG/A1C):
https://professional.diabetes.org/glucose_calc
La propia ADAG confirmó que la regresión no varía significativamente por
edad, sexo, tipo de diabetes, raza/etnia ni tabaquismo — no hace falta
ningún dato demográfico adicional para aplicarla, a diferencia de FIB-4 o
CKD-EPI (§2/§3 de la lista de ideas).

**Limitación importante, a citar igual que la de Friedewald con
triglicéridos**: la fórmula (y la propia HbA1c como reflejo de la
glucemia de ~3 meses) asume una vida media eritrocitaria normal e igual
entre pacientes. Es **falsamente baja** en condiciones que acortan la
vida del hematíe (anemia hemolítica, pérdida de sangre aguda/crónica,
esplenomegalia, embarazo) y **falsamente alta** en condiciones que la
alargan o reducen el recambio (ferropenia, déficit de B12/fólico,
alcoholismo crónico, asplenia). Las hemoglobinopatías (p. ej. drepanocitosis)
pueden además interferir directamente con el propio ensayo de HbA1c,
además de acortar la vida del hematíe. Fuente: "Limitations of hemoglobin
A1c in the management of type 2 diabetes mellitus." PMC7021345:
https://pmc.ncbi.nlm.nih.gov/articles/PMC7021345/ — y, para el caso
concreto de hemoglobinopatías, un caso clínico reciente de HbA1c
falsamente baja enmascarando diabetes real en un paciente con
drepanocitosis + alfa-talasemia: PMC12906350:
https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12906350/

### Índice TyG (triglicéridos-glucosa) — implementado 2026-10-01

`TyG = ln[triglicéridos (mg/dL) × glucosa en ayunas (mg/dL) / 2]`

- Simental-Mendía LE, Rodríguez-Morán M, Guerrero-Romero F. *Metab Syndr
  Relat Disord* 2008;6(4):299-304. doi:10.1089/met.2008.0034.
- ⚠ La fórmula salió mal impresa en el original; la versión corregida es
  la de arriba (*Eur J Pediatr* 2020;179:1171,
  doi:10.1007/s00431-020-03644-1).
- Validación frente al clamp euglucémico-hiperinsulinémico:
  Guerrero-Romero F et al., *J Clin Endocrinol Metab* 2010;95:3347-3351
  (referencia sin DOI verificado).

Decisiones y limitaciones:

- **Sin umbral, solo tendencia**: los puntos de corte publicados (en torno
  a 8,5-8,8) dependen de la población estudiada.
- Es un **marcador indirecto** de resistencia a la insulina, no una
  medida de ella ni un diagnóstico.
- **Requiere ayuno**, y Analitix no registra si la analítica lo era: se
  avisa en la ficha.
- Solo se calcula con glucosa y triglicéridos del mismo informe, en mg/dL.
- Implementación: `src/analitix/tyg_risk.py`, mostrado en el panel de
  glucosa junto a la eAG.

### Puntos de corte diagnósticos de HbA1c (ADA)

- Normal: < 5.7% (< 39 mmol/mol)
- Prediabetes: 5.7–6.4% (39–47 mmol/mol)
- Diabetes: ≥ 6.5% (≥ 48 mmol/mol)

American Diabetes Association, criterios diagnósticos vigentes (resumen
verificado, el umbral de 6.5% se adoptó originalmente en 2009-2010 por el
International Expert Committee de la ADA por su asociación con aparición
de retinopatía). Nota igual de importante que la anterior: estos puntos de
corte requieren un HbA1c medido en laboratorio con método estandarizado
IFCC/NGSP para uso diagnóstico — un punto de corte aislado en Analitix
sería orientativo de seguimiento, nunca sustituye el criterio diagnóstico
formal ni un test de sobrecarga oral de glucosa.

### Implementación

`src/analitix/glycemic_risk.py` calcula eAG como serie sintética
(`get_glycemic_index_series`), pestaña "🍬 Glucosa media estimada (eAG)" en
`gui.py`. El gráfico combinado Glucosa+eAG usa el botón "Ver evolución
(Glucosa + eAG)", que reutiliza `charts.comparison_figure` sin cambios,
mismo patrón que PCR+VSG en `inflammation_risk.py` —
`glycemic_risk.get_glucose_series` expone la serie real de glucosa (mg/dL)
sin calcular nada nuevo.

### Recomendación de implementación

- Coste bajo, valor alto: calcular eAG a partir de HbA1c (fórmula directa,
  sin condiciones de aplicabilidad que dependan de datos que Analitix no
  guarda, a diferencia del hierro) y mostrar glucosa + HbA1c/eAG en el
  mismo gráfico combinado de Evolución (ya se hace algo similar con dos
  paneles en Comparativa, ver `charts.comparison_figure` — aquí se
  añadiría eAG como una serie sintética igual que los índices lipídicos,
  reutilizable con `charts.evolution_figure`/`comparison_figure` sin
  cambios).
  - Mostrar la clasificación ADA (normal/prediabetes/diabetes) junto al
    valor de HbA1c es razonable y barato de implementar, pero **debe
    llevar aviso explícito** de que un valor aislado fuera del rango del
    propio informe del laboratorio no es un diagnóstico (mismo principio
    que el resto de la app) — especialmente relevante aquí porque son
    umbrales diagnósticos oficiales, no solo "orientativos" como los
    índices lipídicos.
  - Incluir en la ficha de descripción de la serie eAG la limitación de
    vida media eritrocitaria (anemia hemolítica, hemoglobinopatías,
    embarazo, etc.) de forma bien visible, ya que es la limitación más
    propensa a generar una falsa tranquilidad (HbA1c falsamente baja
    enmascarando una diabetes real).
