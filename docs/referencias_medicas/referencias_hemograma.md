# Referencias científicas — Hemograma y series roja/blanca

> Parte de [`docs/referencias_medicas/`](README.md) — ver también
> [`docs/DOCUMENTACION_TECNICA.md`](../DOCUMENTACION_TECNICA.md) (sección
> `hemogram_risk.py`).

Investigación de apoyo, implementada en `src/analitix/hemogram_risk.py`
(pestaña "🩸 Hemograma"), de hemograma y series roja/blanca, **excluyendo**
cribado/orientación de leucemia o neoplasias hematológicas (ver
`referencias_leucemia_hematologia.md` para eso). Mismo principio que
`src/analitix/lipid_risk.py`: apoyo informativo y de seguimiento, **nunca
un diagnóstico** — cada fórmula/umbral está citado con una fuente real,
verificada con búsqueda (no de memoria), y con sus limitaciones explícitas.

De los 5 apartados de investigación de abajo, se implementaron los 5: NLR,
PLR, índice de Mentzer (solo con VCM microcítico), LMR (mostrado sin
umbral de alto/bajo, solo como tendencia, por la falta de un punto de
corte único y contrastado) y la orientación de anemia por VCM+RDW (como
texto en el resumen del panel, en lenguaje llano y técnico, nunca como
clasificación cerrada).

## Parámetros de Analitix implicados

`canonical_id` reales confirmados en `src/analitix/data/descripciones/`:
`hemoglobina`, `hematocrit`, `hematies`, `vcm`, `hcm`, `chcm`, `rdw_cv`,
`leucocits`, `neutrofils_total`, `limfocits_total`, `monocits_total`,
`eosinofils_total`, `basofils_total`, `plaquetes`, `vpm`. (También existen
`neutrofils`/`limfocits`/`monocits`/`eosinofils`/`basofils` sin `_total`,
probablemente el valor en % en vez de en cifra absoluta — a confirmar contra
un informe real antes de implementar cuál usar para cada índice: los tres
ratios de abajo necesitan **cifras absolutas**, no porcentajes.)

---

## 1. NLR — Índice neutrófilos/linfocitos

**Fórmula:** neutrófilos absolutos ÷ linfocitos absolutos (mismo hemograma).

**Qué mide:** marcador de inflamación sistémica y del equilibrio entre
inmunidad innata (neutrófilos) y adaptativa (linfocitos); no específico de
ninguna enfermedad — se ha estudiado como apoyo pronóstico en cardiología,
oncología, infección, cirugía, etc.

**Rango de referencia poblacional (no es un "umbral de riesgo" validado,
es un intervalo estadístico de normalidad):**
- Wang J, Zhang F, Jiang F, et al. "Distribution and reference interval
  establishment of neutral-to-lymphocyte ratio (NLR), lymphocyte-to-monocyte
  ratio (LMR), and platelet-to-lymphocyte ratio (PLR) in Chinese healthy
  adults." *J Clin Lab Anal*. 2021;35(9):e23935.
  https://doi.org/10.1002/jcla.23935 — cohorte de **404 272 adultos sanos**
  (205 592 hombres, 198 680 mujeres, 18-112 años), intervalo de referencia =
  percentil no paramétrico 95% (CLSI C28-A3). NLR: **0-2.696 (hombres)**,
  **0-2.805 (mujeres)**.
- Corroboración independiente (población y método distintos, mismo orden de
  magnitud): Wang Q, Jiang Y, Jin F, et al. "Reference range of
  neutrophil-to-lymphocyte ratio in healthy individuals and its predictive
  value for post-trauma nosocomial infections." *Front Cell Infect
  Microbiol*. 2025;15:1529532. https://doi.org/10.3389/fcimb.2025.1529532 —
  165 504 personas, percentil 2.5-97.5 global: **0.86-3.83** (se amplía con
  la edad: 0.85-3.70 en 18-40 años, hasta 0.83-4.31 en ≥61 años).

**Limitaciones importantes:**
- Los dos estudios de referencia son de población **china**; no hay
  garantía de que el mismo intervalo aplique sin más a la población de
  Analitix — se cita como orientación, no como valor validado localmente.
- El NLR fluctúa con estrés agudo, ejercicio, infección o cirugía reciente;
  un solo valor alto no es relevante — lo que importa es la tendencia (esto
  encaja de forma natural con cómo Analitix ya presenta cualquier serie:
  gráfico de evolución + tendencia, ver `charts.py`).
- Los puntos de corte de "riesgo" citados en estudios de una enfermedad
  concreta (p. ej. NLR > 3 en cardiopatía isquémica, distintos umbrales en
  oncología) **no son generalizables** a población sana — no se debe
  reutilizar un umbral de un estudio de enfermedad como si fuera un
  intervalo de normalidad.

---

## 2. PLR — Índice plaquetas/linfocitos

**Fórmula:** plaquetas ÷ linfocitos absolutos.

**Qué mide:** marcador de inflamación sistémica y estado protrombótico,
complementario al NLR (mismo tipo de literatura: cardiología, oncología,
enfermedades reumáticas, COVID-19).

**Rango de referencia poblacional:** mismo estudio que NLR — Wang J et al.
2021, *J Clin Lab Anal*. https://doi.org/10.1002/jcla.23935 — PLR:
**0-162.84 (hombres)**, **0-185.52 (mujeres)** (percentil 95% no
paramétrico, misma cohorte de 404 272 adultos sanos).

**Limitaciones:** iguales a NLR (población china, no validado localmente) +
una diferencia por sexo más marcada que en NLR/LMR (mujeres
sistemáticamente más altas en varios estudios independientes) — si algún
día se quisiera clasificar "alto/normal" en vez de solo graficar la
evolución, este es el índice donde más importaría no tener el sexo del
paciente (limitación ya conocida y documentada igual en
`lipid_risk.py`/Castelli).

---

## 3. LMR — Índice linfocitos/monocitos

**Fórmula:** linfocitos absolutos ÷ monocitos absolutos.

**Qué mide:** también marcador de inflamación sistémica/pronóstico general,
menos conocido que NLR/PLR pero complementario (linfocitos = inmunidad
específica, monocitos = inflamación/reparación tisular).

**Rango de referencia poblacional:** mismo estudio — Wang J et al. 2021.
LMR: **0-9.00 (hombres)**, **0-10.00 (mujeres)**.

**Limitaciones:** iguales a NLR/PLR. Además, a diferencia de NLR/PLR (donde
un valor alto es lo que preocupa), en LMR es un valor **bajo** el que se
asocia a peor pronóstico en la literatura oncológica — si se implementa,
cuidado con no invertir el sentido del marcador al reutilizar la misma
lógica de "alto = alerta" que el resto de índices de la app.

---

## 4. Clasificación de anemia por VCM + RDW

**Rango de VCM (volumen corpuscular medio):** normal 80-100 fL; microcítica
< 80 fL; macrocítica > 100 fL. Fuente: Regalla DKR, Killeen RB. "Anemia."
En: *StatPearls* [Internet]. StatPearls Publishing; 2026 (actualizado 5 jul.
2026). https://www.ncbi.nlm.nih.gov/books/NBK499994/ — clasifica
explícitamente "Hypoproliferative Microcytic Anemia (MCV < 80 fL)",
"...Normocytic Anemia (MCV 80 to 100 fL)", "...Macrocytic Anemia
(MCV > 100 fL)".

**Papel del RDW (ancho de distribución eritrocitaria):** según la misma
fuente, "the RDW quantifies anisocytosis (variation in red cell size); it
is characteristically elevated in iron deficiency anemia and often normal
in thalassemia trait, providing a useful (though not absolute)
discriminator" — es decir, dentro de una microcitosis, RDW alto orienta a
ferropenia y RDW normal orienta a rasgo talasémico (mismo principio que
recoge el índice de Mentzer, ver más abajo, con el que es coherente y
complementario, no un método alternativo independiente).

**Caso especial reseñable:** la misma fuente señala que un déficit
combinado de hierro + vitamina B12 puede dar un VCM "engañosamente normal"
(las dos poblaciones, microcítica y macrocítica, promedian a un VCM medio)
y que un RDW elevado con una distribución dimórfica en el frotis debe hacer
sospechar ese déficit doble — relevante como nota de cautela si se
implementa un árbol de orientación automático: VCM normal con RDW alto no
debe leerse sin más como "todo bien".

**Limitación general de implementarlo en Analitix:** este árbol de
orientación diagnóstica es **cualitativo y depende de más contexto clínico**
del que Analitix guarda (historia clínica, frotis, ferritina/B12 — algunos
de estos sí están disponibles como parámetros separados, ver
`referencias_hierro_glucosa.md`/`src/analitix/iron_risk.py`); un cruce
automático VCM+RDW puede mostrarse como **orientación en texto**, nunca
como una clasificación cerrada de tipo de anemia.

---

## 5. Índice de Mentzer

**Fórmula:** VCM (fL) ÷ nº de hematíes (millones/µL).

**Origen:** Mentzer WC Jr. "Differentiation of iron deficiency from
thalassaemia trait." *Lancet*. 1973 Apr 21;1(7808):882. PMID: 4123424.

**Punto de corte (confirmado, no asumido):** índice > 13 → más compatible
con anemia ferropénica; índice < 13 → más compatible con rasgo
talasémico-β; índice = 13 → resultado no concluyente. Racional fisiológico:
en ferropenia el recuento de hematíes también baja (además de ser
pequeños), mientras que en talasemia el recuento de hematíes suele ser
normal o alto aunque el VCM sea bajo — de ahí que el cociente separe ambos
casos.

**Rendimiento diagnóstico citado:** en un estudio pediátrico (290 niños),
sensibilidad 98.7% y especificidad 82.3% para detectar rasgo
β-talasémico (el mejor de varios índices comparados) — cita agregada vía
búsqueda, sin acceso directo al artículo original de ese dato; usar con
cautela como cifra orientativa, no como valor verificado de primera mano
como el resto de citas de este documento.

**Limitación citada en la literatura:** algunos autores (referenciados como
"Mazza et al." en fuentes secundarias) señalan que el índice no debe usarse
como único criterio, ya que casos límite/mixtos pueden dar valores
ambiguos; se recomienda siempre como cribado orientativo, nunca como
sustituto de electroforesis de hemoglobina o estudio genético para
confirmar talasemia.

**Nota de implementación (para cuando se aborde en código):** requiere que
`hematies` esté en millones/µL — a confirmar la unidad exacta que trae el
informe del laboratorio antes de calcular (mismo cuidado de unidades que
`lipid_risk._mg_dl` con mg/dL).

---

## Recomendación de prioridad

Todo lo anterior es aritmética pura sobre datos ya almacenados (sin
librerías nuevas), igual que el perfil lipídico ya implementado. Orden
sugerido:

1. **NLR y PLR**: los dos con reference interval más sólido (misma fuente,
   misma cohorte grande) y de cálculo más directo (2 parámetros cada uno).
2. **Índice de Mentzer**: cálculo trivial (2 parámetros), punto de corte
   único y bien definido (13), fuente original verificada — el más "limpio"
   de implementar de toda esta lista pese a ser el más antiguo.
3. **LMR**: mismo nivel de esfuerzo que NLR/PLR, pero cuidado documentado
   arriba con la inversión del sentido (bajo = alerta, no alto).
4. **Clasificación VCM+RDW**: la más valiosa para el usuario a nivel
   explicativo, pero la que menos se presta a un único número/semáforo —
   mejor como texto orientativo junto al gráfico de evolución de VCM/RDW
   que como índice numérico independiente.

En todos los casos, dado que ninguna fuente encontrada da un intervalo de
referencia validado específicamente para la población de Analitix (todas
las fuentes con cohortes grandes son de población china), lo más honesto es
presentar estos valores igual que los índices lipídicos: con el rango
citado explícitamente como orientativo/poblacional, nunca como un punto de
corte de enfermedad, y remarcando que lo más útil de Analitix aquí es la
**tendencia en el tiempo**, no el valor aislado.
