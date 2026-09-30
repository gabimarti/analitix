# Referencias científicas — Función renal

> Parte de [`docs/referencias_medicas/`](README.md) — ver también
> [`docs/DOCUMENTACION_TECNICA.md`](../DOCUMENTACION_TECNICA.md) (sección
> `renal_risk.py`).

Investigación de apoyo, implementada en `src/analitix/renal_risk.py`
(pestaña "🩺 Función renal"), con el mismo
nivel de rigor ya aplicado en `src/analitix/lipid_risk.py`: cada
fórmula/umbral está verificado contra una fuente real (nunca de memoria) y
citado con URL. Igual que en el resto de la app: **apoyo informativo y de
seguimiento, nunca un diagnóstico** — la interpretación clínica final es
siempre del médico.

## Parámetros de Analitix implicados

`canonical_id` reales confirmados en `src/analitix/data/descripciones/`
(varios por parámetro, igual que pasó con el perfil lipídico — distintas
plantillas del laboratorio nombran la misma prueba de forma algo distinta,
ver `lipid_risk.TOTAL_IDS` como precedente):
- Filtrado glomerular estimado: `filtrat_glomerular_estimat_serum`,
  `filtrat_glomerular_estimat`, `filtrat_glomerular_estimat_90_ml_min` (¡3
  variantes! — la tercera probablemente indica un informe donde el valor
  numérico venía truncado a "≥90" en vez de un número, hay que revisar un
  PDF real antes de fusionarlas a ciegas).
- Creatinina: `creatinina_serum`.
- Urea: `urea_serum`.
- Albuminuria/ratio albúmina-creatinina: `albumina_creatinina`,
  `albumina_creatinina_orina_esporadica`, `albuminuria`, `microalbuminuria`
  (4 variantes — no está claro sin mirar PDFs reales si todas miden lo
  mismo con nombres distintos o si alguna es un valor cualitativo/otro tipo
  de determinación; **antes de implementar, revisar con Explorador BD** qué
  unidad y qué rango de valores tiene cada una).
- `potassi` (potasio), `sodi` (sodio): disponibles pero sin un cálculo
  específico propuesto en la idea original más allá de mostrarlos.

## 1. Clasificación KDIGO de enfermedad renal crónica

**Guía oficial**: Kidney Disease: Improving Global Outcomes (KDIGO) CKD Work
Group. "KDIGO 2012 Clinical Practice Guideline for the Evaluation and
Management of Chronic Kidney Disease." *Kidney Int Suppl.* 2013;3(1):1-150.
DOI: 10.1038/kisup.2012.73. PDF oficial en kdigo.org
(`kdigo.org/wp-content/uploads/2017/02/KDIGO_2012_CKD_GL.pdf`, bloqueado a
fetch automático con 403 al redactar este documento — abrir manualmente en
un navegador si se necesita el texto completo). Categorías confirmadas de
forma independiente contra una fuente alojada en NIH/NCBI (StatPearls,
[NBK535404](https://www.ncbi.nlm.nih.gov/books/NBK535404/)):

**Categorías de FG estimado (G), mL/min/1.73m²:**
| Categoría | Rango | Descripción |
|---|---|---|
| G1 | ≥90 | Normal o alto |
| G2 | 60-89 | Ligeramente disminuido |
| G3a | 45-59 | Ligera a moderadamente disminuido |
| G3b | 30-44 | Moderada a severamente disminuido |
| G4 | 15-29 | Severamente disminuido |
| G5 | <15 | Fallo renal |

Nota importante de la propia guía: sin otra evidencia de daño renal, **ni
G1 ni G2 cumplen por sí solos criterios de ERC** (un FG normal/casi normal
no es enfermedad renal si no hay albuminuria ni otro marcador).

**Categorías de albuminuria (A), ratio albúmina/creatinina (ACR):**
| Categoría | Rango (mg/g) | Rango (mg/mmol) | Descripción |
|---|---|---|---|
| A1 | <30 | <3.4 | Normal a ligeramente aumentada |
| A2 | 30-299 | 3.4-34 | Moderadamente aumentada |
| A3 | >300 | >34 | Severamente aumentada |

**Mapa de calor de riesgo (heat map)**: cruza G × A en una tabla 2D con
código de color — verde (riesgo bajo, sin otros marcadores no hay ERC),
amarillo (riesgo moderadamente aumentado), naranja (riesgo alto), rojo
(riesgo muy alto), rojo oscuro (riesgo máximo, quinto nivel que algunas
reproducciones omiten). El color exacto de cada celda no se pudo extraer
del PDF oficial de KDIGO (bloqueado a fetch automático), pero sí de una
fuente primaria alternativa verificada: la National Kidney
Foundation, "CKD Risk Assessment Tool" (2015), explícitamente "Adapted
with permission from KDIGO 2012 Clinical Practice Guideline... Kidney Int.
2013;Suppl.3:1-150" —
https://www.kidney.org/sites/default/files/01-10-7027_ABG_HeatMap_Card_3_0.pdf,
leída directamente (texto e imagen) con el lector de PDF multimodal, no
transcrita de un resumen de búsqueda. Las 18 celdas, tal como aparecen en
ese documento:

| G \ A | A1 (<30) | A2 (30-299) | A3 (≥300) |
|---|---|---|---|
| G1 (≥90) | Verde | Amarillo | Naranja |
| G2 (60-89) | Verde | Amarillo | Naranja |
| G3a (45-59) | Amarillo | Naranja | Rojo |
| G3b (30-44) | Naranja | Rojo | Rojo |
| G4 (15-29) | Rojo | Rojo | Rojo oscuro |
| G5 (<15) | Rojo oscuro | Rojo oscuro | Rojo oscuro |

Corroborado además de forma consistente por dos fuentes secundarias
independientes: [Cleveland Clinic Journal of Medicine, "Managing chronic
kidney disease according to KDIGO risk categories: A primer for primary
care"](https://www.ccjm.org/content/93/6/353) y múltiples figuras de
artículos indexados en ResearchGate que reproducen el mismo mapa atribuido
a KDIGO. (Aviso de proceso: una tabla numérica "1-4" de Wikipedia que
parecía a primera vista la misma información resultó ser la frecuencia de
monitorización anual recomendada por celda, **no** el nivel de riesgo/color
— confirmado al no coincidir con la tabla de la NKF; descartada como fuente
para esta tabla.)

**Actualización 2024**: existe una guía KDIGO más reciente (2024) que
mantiene el mismo marco G1-G5/A1-A3 pero recomienda usar también cistatina
C además de creatinina para estimar el FG con más precisión — Analitix hoy
solo tiene creatinina disponible en los PDF del laboratorio, así que esto
no cambia lo implementable a corto plazo, solo se anota como contexto.

## 2. CKD-EPI 2021 (estimación de FG sin variable de raza)

Confirmado con **dos fuentes independientes coincidentes**: la página
oficial de la [National Kidney
Foundation](https://www.kidney.org/professionals/ckd-epi-creatinine-equation-2021)
y el resumen del artículo original.

**Cita**: Inker LA, Eneanya ND, Coresh J, et al. "New creatinine- and
cystatin C–based equations to estimate GFR without race." *N Engl J Med.*
2021;385:1737-1749. https://www.nejm.org/doi/full/10.1056/NEJMoa2102953

**Fórmula** (creatinina estandarizada en mg/dL, edad en años):

```
eGFR = 142 × min(Scr/κ, 1)^α × max(Scr/κ, 1)^(-1.200) × 0.9938^edad × (1.012 si mujer)
```
donde κ = 0.7 (mujer) / 0.9 (hombre), α = -0.241 (mujer) / -0.302 (hombre).
Sin coeficiente de raza (sustituye a la versión CKD-EPI 2009, que sí lo
tenía; recomendado su reemplazo por la propia NKF-ASN Task Force: Delgado C
et al. *Am J Kidney Dis.* 2021;78(1):103-115).

**Limitación práctica real para Analitix**: la fórmula necesita **edad y
sexo** del paciente. Hoy `patients` no guarda ninguno de los dos de forma
estructurada (`birth_date` si se ha extraído del PDF permitiría calcular la
edad en el momento del informe; el sexo no se guarda en absoluto). En la
práctica esto es poco urgente: la inmensa mayoría de los informes del
laboratorio ya traen el FG calculado directamente
(`filtrat_glomerular_estimat*`), así que CKD-EPI desde cero solo aportaría
valor para informes antiguos que no lo incluyan — habría que revisar
cuántos PDF reales están en ese caso antes de justificar pedir el sexo del
paciente (dato sensible adicional) solo para eso.

## 3. Ratio urea/creatinina

Fuente: Higgins C. "Urea and creatinine concentration, the urea:creatinine
ratio." acutecaretesting.org, octubre 2016.
https://acutecaretesting.org/en/articles/urea-and-creatinine-concentration-the-urea-creatinine-ratio
— artículo de formación en química clínica, no un ensayo original, pero
citado porque explica con claridad una trampa real de unidades relevante
aquí.

**Punto crítico de unidades, verificado y no trivial**: hay dos convenciones
mundiales completamente distintas, y mezclarlas da un ratio sin sentido:
- **EE. UU. (no-SI)**: se mide **BUN** ("blood urea nitrogen", solo el
  nitrógeno de la urea, PM 28) en mg/dL. Ratio BUN/creatinina (ambos
  mg/dL), rango normal ~8-15, corte habitual >20 sugiere causa prerrenal,
  <10 sugiere causa renal intrínseca.
- **Resto del mundo (SI)**: se mide la **urea** completa (molécula entera,
  PM 60) en mmol/L. Ratio SI = urea (mmol/L) ÷ (creatinina (µmol/L) ÷
  1000), rango normal "del orden de 40-100" (cifra muy distinta a la
  americana, no son la misma escala).
- **Urea (mg/dL) ≠ BUN (mg/dL)**: aunque coincida la unidad "mg/dL", el
  valor de "urea" es ~2.14× el de "BUN" (factor derivado de la diferencia
  de peso molecular 60/28) — la conversión exacta citada es "urea mmol/L ÷
  0.357 = BUN mg/dL".

**Implicación real para Analitix**: no se sabe todavía con certeza si el
laboratorio (Consorci Sanitari del Maresme) informa `urea_serum` en mg/dL o
mmol/L, ni si el valor es "urea" real o en realidad "BUN" con otro nombre —
**no verificado en este documento, pendiente de mirarlo en Explorador BD
contra un PDF real** (mismo tipo de comprobación que ya se hizo para
confirmar mg/dL en colesterol/triglicéridos al implementar
`lipid_risk.py`). Aplicar un umbral numérico (p. ej. ">20" o "40-100") sin
confirmar antes cuál de las dos convenciones usa el laboratorio daría una
clasificación con el signo o la escala equivocados — **más importante
verificar esto que en el caso lipídico**, porque aquí sí hay dos sistemas
de unidades activos en el mundo real con el mismo nombre de columna
("urea"), mientras que en lípidos solo había mg/dL vs. mmol/L, más fácil de
detectar por el propio nombre de la unidad.

## Recomendación de implementación

Verificado contra los 39 PDF reales del proyecto:
- `urea_serum` es urea real en mg/dL (no BUN): su propio rango de
  referencia (17.1-49.3 mg/dL) es coherente con urea real, muy por encima
  del rango típico de BUN (~6-20 mg/dL).
- Solo `albumina_creatinina` (mg/g_creat) y
  `albumina_creatinina_orina_esporadica` (µg/mg, numéricamente idéntico a
  mg/g) son un ACR utilizable. `albuminuria`/`microalbuminuria` (mg/L) son
  concentración de albúmina en orina, **no** un ratio — no se usan para
  KDIGO.

Implementado en `src/analitix/renal_risk.py` + pestaña "🩺 Función renal"
(mismo patrón que `lipid_risk.py`/`hepatic_risk.py`):
1. **Clasificación y mapa de riesgo KDIGO** cruzando el FG ya guardado con
   el ACR ya guardado, sin dato nuevo del paciente. Las 18 celdas del mapa
   de riesgo (no disponibles en el PDF oficial de KDIGO, bloqueado a fetch
   automático) se obtuvieron de la adaptación oficial en PDF de la
   National Kidney Foundation ("CKD Risk Assessment Tool", 2015, "Adapted
   with permission from KDIGO 2012 CPG"), leída directamente con el lector
   de PDF multimodal.
2. **Ratio urea/creatinina**, con los cortes clásicos (BUN/Cr >20/<10)
   escalados por el factor de peso molecular urea/BUN ≈2.14, dado que este
   laboratorio informa urea real, no BUN.
3. **Aviso de subida brusca de creatinina** (criterio 1 de Sawhney et al.
   2015, ver `referencias_deterioro_renal_agudo.md`), como un índice más
   con su propia serie temporal.

**No implementado deliberadamente**: CKD-EPI 2021 desde cero — requiere el
sexo del paciente (dato nuevo, sensible) y la inmensa mayoría de los
informes reales ya traen el FG calculado por el laboratorio, así que el
esfuerzo/dato sensible adicional no se justifica hoy.

## Fuentes citadas (resumen con URLs)

- KDIGO CKD Work Group. *Kidney Int Suppl.* 2013;3(1):1-150. DOI:
  10.1038/kisup.2012.73.
  https://kdigo.org/wp-content/uploads/2017/02/KDIGO_2012_CKD_GL.pdf
- StatPearls (NIH/NCBI Bookshelf), "Chronic Kidney Disease" —
  https://www.ncbi.nlm.nih.gov/books/NBK535404/ (categorías G/A verificadas
  de forma independiente contra esta fuente).
- Cleveland Clinic Journal of Medicine, "Managing chronic kidney disease
  according to KDIGO risk categories: A primer for primary care" —
  https://www.ccjm.org/content/93/6/353 (descripción del mapa de calor).
- National Kidney Foundation, "CKD Risk Assessment Tool" (2015),
  "Adapted with permission from KDIGO 2012 Clinical Practice Guideline" —
  https://www.kidney.org/sites/default/files/01-10-7027_ABG_HeatMap_Card_3_0.pdf
  (las 18 celdas exactas del mapa de riesgo).
- Inker LA et al. *N Engl J Med.* 2021;385:1737-1749. DOI:
  10.1056/NEJMoa2102953 —
  https://www.kidney.org/professionals/ckd-epi-creatinine-equation-2021 y
  https://www.nejm.org/doi/full/10.1056/NEJMoa2102953
- Delgado C et al. *Am J Kidney Dis.* 2021;78(1):103-115 (recomendación de
  adopción de la fórmula sin raza).
- Higgins C. "Urea and creatinine concentration, the urea:creatinine
  ratio." acutecaretesting.org, 2016.
  https://acutecaretesting.org/en/articles/urea-and-creatinine-concentration-the-urea-creatinine-ratio
