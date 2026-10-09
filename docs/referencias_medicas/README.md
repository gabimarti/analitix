# Referencias médicas

Documentos de investigación que respaldan (o descartan, cuando la evidencia
no era suficiente) los cálculos e ideas de análisis clínico de Analitix.
Cada fórmula, umbral o guía citada en estos documentos está verificada
contra una fuente real (artículo científico, guía clínica o revisión),
nunca de memoria — el mismo criterio que ya siguen los tres módulos de
cálculo clínico ya implementados,
[`src/analitix/lipid_risk.py`](../../src/analitix/lipid_risk.py) (perfil
lipídico y riesgo cardiovascular),
[`hepatic_risk.py`](../../src/analitix/hepatic_risk.py) (función e índices
hepáticos),
[`renal_risk.py`](../../src/analitix/renal_risk.py) (función renal),
[`hemogram_risk.py`](../../src/analitix/hemogram_risk.py) (hemograma y
series roja/blanca),
[`iron_risk.py`](../../src/analitix/iron_risk.py) (metabolismo del
hierro) e
[`inflammation_risk.py`](../../src/analitix/inflammation_risk.py) (PCR +
VSG, sin índice combinado),
[`uric_acid_risk.py`](../../src/analitix/uric_acid_risk.py) (ácido
úrico/hiperuricemia),
[`calcium_risk.py`](../../src/analitix/calcium_risk.py) (calcio corregido
por albúmina),
[`tyg_risk.py`](../../src/analitix/tyg_risk.py) (índice TyG, solo tendencia),
[`glycemic_risk.py`](../../src/analitix/glycemic_risk.py) (glucosa media
estimada desde HbA1c) y
[`thyroid_risk.py`](../../src/analitix/thyroid_risk.py) (TSH+T4L, solo
gráfico combinado); sus citas viven directamente en el código en vez de
en un documento aparte.

**Principio de toda esta carpeta, igual que el resto de la app**: apoyo
informativo y de seguimiento, nunca un diagnóstico. Cuando la evidencia no
respalda un cálculo o alerta fiable, el propio documento lo dice de forma
explícita en vez de forzar una propuesta más ambiciosa de lo que la
literatura permite.

- [`referencias_visualizacion.md`](referencias_visualizacion.md) — cómo se
  presentan los resultados a pacientes: resumen en texto y aviso de pocos
  datos (**implementados**), ideas pendientes con su evidencia y por qué
  la evidencia general es escasa.
- [`referencias_rcv.md`](referencias_rcv.md) — **implementado**: valor de
  referencia del cambio (RCV, "¿cambio real o variación esperable?") con
  variación biológica de artículos publicados (EuBIVAS, Coşkun 2018);
  discrepancias entre fuentes y parámetros excluidos a propósito.
- [`referencias_tendencia_tiempo_en_rango.md`](referencias_tendencia_tiempo_en_rango.md)
  — **implementado**: tendencia robusta (Theil-Sen, Sen 1968) con
  intervalo de confianza, umbral KDIGO de descenso rápido del filtrado
  glomerular y tiempo en rango (Rosendaal 1993); umbrales de velocidad
  descartados (PSA, HbA1c).
- [`referencias_tension_arterial.md`](referencias_tension_arterial.md) —
  **implementado**: media de automedida en casa (protocolo ESH 2021) y
  categorías de la guía ESC 2024 para medidas en casa.
- [`referencias_hepatico.md`](referencias_hepatico.md) — **implementado**:
  función e índices hepáticos, ratio AST/ALT (De Ritis), FIB-4, APRI.
- [`referencias_renal.md`](referencias_renal.md) — **implementado**:
  función renal, clasificación y mapa de riesgo KDIGO (G1-G5 × A1-A3),
  ratio urea/creatinina; CKD-EPI 2021 deliberadamente no implementado
  (necesitaría el sexo del paciente).
- [`referencias_deterioro_renal_agudo.md`](referencias_deterioro_renal_agudo.md)
  — **implementado**: aviso orientativo de subida brusca de creatinina
  (AKI), distinto de la clasificación KDIGO crónica de arriba.
- [`referencias_hemograma.md`](referencias_hemograma.md) — **implementado**:
  NLR, PLR, LMR, clasificación de anemia por VCM+RDW, índice de Mentzer.
- [`referencias_leucemia_hematologia.md`](referencias_leucemia_hematologia.md)
  — avisos de seguridad orientativos sobre neoplasias hematológicas
  (leucemia y similares) a partir del hemograma; **parcialmente
  implementado**: aviso de linfocitosis sostenida > 5×10⁹/L en ≥2
  informes (umbral ESMO 2021/iwCLL 2018), sin ningún score combinado de
  riesgo (no existe ninguno validado).
- [`referencias_hierro_glucosa.md`](referencias_hierro_glucosa.md) —
  metabolismo del hierro: **implementado** (ferritina + saturación de
  transferrina, sin automatizar el diagnóstico diferencial); metabolismo
  glucídico: **implementado** (glucosa media estimada, eAG, desde HbA1c,
  fórmula ADAG).
- [`referencias_calcio.md`](referencias_calcio.md) — **implementado**:
  calcio corregido por albúmina (fórmula de Payne 1973), clasificado con
  el rango de referencia del propio informe.
- [`referencias_proteinograma_gammapatia.md`](referencias_proteinograma_gammapatia.md)
  — por qué un aviso de gammapatía monoclonal/mieloma desde el
  proteinograma no es viable con los datos que Analitix guarda.
- [`referencias_tiroides_inflamacion_coagulacion.md`](referencias_tiroides_inflamacion_coagulacion.md)
  — tiroides: **parcialmente implementado** (solo el gráfico combinado
  TSH+T4L, sin la clasificación por cuadrante — deliberadamente no
  implementada, es el criterio diagnóstico estándar y depende del
  embarazo); coagulación (rango terapéutico de INR, no implementado);
  inflamación (PCR/VSG) — **implementado**, sin índice combinado por
  diseño.
- [`referencias_ictus.md`](referencias_ictus.md) — por qué ningún score de
  riesgo de ictus validado es calculable solo con analítica (todos exigen
  tensión arterial y/o tabaquismo), y qué marcadores individuales
  (hs-PCR, fibrinógeno, HbA1c, INR en fibrilación auricular) tienen
  asociación real pero sin umbral aplicable como alerta automática. El
  ácido úrico (`urat_serum`) se descarta aquí como marcador de ictus,
  pero sí está **implementado** con una indicación distinta (hiperuricemia,
  no ictus) — ver `uric_acid_risk.py` arriba.
