# Referencias científicas — Función e índices hepáticos

> Parte de [`docs/referencias_medicas/`](README.md) — ver también
> [`docs/DOCUMENTACION_TECNICA.md`](../DOCUMENTACION_TECNICA.md) (sección
> `hepatic_risk.py`).

Investigación de apoyo, implementada en `src/analitix/hepatic_risk.py`, con
el mismo criterio que `src/analitix/lipid_risk.py`: cada fórmula/umbral está
verificado contra una fuente real (búsqueda web, nunca de memoria) antes de
citarlo aquí. Como el resto de Analitix, esto es **apoyo informativo y de
seguimiento, nunca un diagnóstico** — ningún índice de esta lista sustituye
una prueba de imagen, una biopsia o la valoración de un hepatólogo.

## Parámetros de Analitix implicados

`alanina_aminotransferasa_alt_serum` (ALT), `aspartat_aminotranferasa_ast_serum`
(AST), `gamma_glutamil_transferasa_ggt_serum`, `fosfatasa_alcalina_serum`,
`bilirubina_total_serum`, `albumina_serum`, `proteines_totals_serum`,
`plaquetes`, `temps_de_protrombina_rati_plasma` (INR/rati) — confirmados en
`src/analitix/data/descripciones/`. GGT, fosfatasa alcalina, bilirrubina,
albúmina y proteínas totales no entran en ninguna fórmula de las tres de
abajo, pero son los parámetros de "función hepática" clásicos que sí se
podrían mostrar con su propia clasificación de referencia (mismo patrón que
`ATP3_HIGH`/`ATP3_LOW` en `lipid_risk.py`) si se retoma esta idea, aunque no
se ha investigado un consenso numérico único para ellos en esta sesión — no
son objeto de las tres fórmulas siguientes.

## 1. Ratio AST/ALT (índice De Ritis)

**Fórmula:** AST ÷ ALT, sin más.

**Origen:** De Ritis F, Coltorti M, Giusti G. Descrito en 1957 (*Minerva
Medica*) como prueba enzimática para la hepatitis viral aguda. Cita
verificada a través de una revisión reciente que reconstruye la historia del
índice: "Navigating Disease Management: A Comprehensive Review of the De
Ritis Ratio in Clinical Medicine" (PMC, 2024).
https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11319523/

**Interpretación orientativa** (confirmada en la misma revisión):
- Ratio normal en sujetos sanos: ≈ 0.8.
- Ratio < 1 (ALT predomina): patrón típico de hígado graso
  (MASLD/NAFLD) y hepatitis viral aguda, donde predomina la liberación de
  ALT citosólica.
- Ratio > 2: sugiere enfermedad hepática alcohólica (la AST mitocondrial se
  libera más, y el déficit de vitamina B6 asociado al alcohol suprime la
  ALT).
- Ratio > 1 de forma sostenida en hepatitis viral crónica o hígado graso no
  alcohólico: se asocia a progresión hacia fibrosis/cirrosis (marcador
  pronóstico, no solo diagnóstico del patrón agudo).

**Advertencia técnica** encontrada en la misma fuente: el resultado puede
verse afectado por si el laboratorio usa un reactivo suplementado con
piridoxal fosfato en la determinación de las transaminasas (relevante en
pacientes alcohólicos, ancianos u oncológicos con posible déficit de
piridoxina) — Analitix no tiene forma de saber qué reactivo usó el
laboratorio, así que esto quedaría como limitación no resoluble desde la
app.

**Implementable ya**: sí, cálculo puro con `aspartat_aminotranferasa_ast_serum`
y `alanina_aminotransferasa_alt_serum`, sin datos adicionales.

## 2. FIB-4 (índice de fibrosis 4)

**Fórmula:** `Edad [años] × AST [U/L] ÷ (Plaquetas [10⁹/L] × √ALT [U/L])`.

**Cita original:** Sterling RK, Lissen E, Clumeck N, et al. (APRICOT Clinical
Investigators). "Development of a simple noninvasive index to predict
significant fibrosis in patients with HIV/HCV coinfection." *Hepatology*.
2006;43(6):1317-1325. doi: 10.1002/hep.21178. PMID: 16729309.
https://pubmed.ncbi.nlm.nih.gov/16729309/

**Población de validación original**: pacientes coinfectados VIH/VHC (no
población general) — 832 pacientes, fibrosis evaluada por biopsia (escala de
Ishak). AUROC 0.765 para distinguir Ishak 0-3 de 4-6.

**Puntos de corte "clásicos" (Sterling 2006, HIV/HCV)**: < 1.45 → alto valor
predictivo negativo (90%) para excluir fibrosis avanzada; > 3.25 → alto valor
predictivo positivo (65%), especificidad 97%. Con estos dos cortes, el 87%
de los pacientes fuera del rango 1.45-3.25 quedaban correctamente
clasificados.

**Puntos de corte "modernos" para MASLD/NAFLD (más relevantes para cribado en
población general, no solo VIH/VHC)**: Rinella ME, Neuschwander-Tetri BA,
Siddiqui MS, et al. "AASLD Practice Guidance on the clinical assessment and
management of nonalcoholic fatty liver disease." *Hepatology*.
2023;77(5):1797-1835. DOI: 10.1097/HEP.0000000000000323.
https://pmc.ncbi.nlm.nih.gov/articles/PMC10735173/ — define **< 1.3** como
riesgo bajo (manejable en atención primaria), **1.3-2.67** riesgo intermedio
(requiere una segunda prueba no invasiva, p. ej. elastografía) y **> 2.67**
riesgo alto (derivación directa a digestivo/hepatología). Cita textual: "or
when FIB4 > 2.67 due to the increased risk of clinically significant
fibrosis."

**Nota importante para Analitix**: los dos conjuntos de puntos de corte
(1.45/3.25 de Sterling vs. 1.3/2.67 de AASLD) **no son intercambiables** —
miden poblaciones y objetivos algo distintos (validación específica en
VIH/VHC vs. guía de cribado general orientada a hígado graso). Si se
implementa, habría que citar ambos y ser explícito sobre cuál se está usando
y por qué (probablemente el de AASLD 2023, por ser más reciente y pensado
para cribado general, más cercano al caso de uso de un paciente sin
diagnóstico previo de VIH/VHC).

**Limitación práctica real para Analitix**: la fórmula necesita la **edad
exacta** del paciente en la fecha del informe, y no todas las plantillas/
informes traen la fecha de nacimiento del paciente.

`src/analitix/hepatic_risk.py` (función `_age_at`) calcula la edad a partir
de `patients.birth_date` y la fecha de cada informe concreto; si el
paciente no tiene fecha de nacimiento conocida, FIB-4 simplemente no
aparece para ese informe, sin bloquear el resto de índices hepáticos.
Puntos de corte usados: los de AASLD 2023 (1.3/2.67), no los de
Sterling 2006.

## 3. APRI (AST to Platelet Ratio Index)

**Fórmula:** `(AST [U/L] ÷ Límite superior normal de AST [U/L]) × 100 ÷
Plaquetas [10⁹/L]`. El límite superior normal de AST más usado en la
literatura es 40 U/L (valor de referencia típico de laboratorio, no un dato
por paciente).

**Cita original:** Wai CT, Greenson JK, Fontana RJ, et al. "A simple
noninvasive index can predict both significant fibrosis and cirrhosis in
patients with chronic hepatitis C." *Hepatology*. 2003;38(2):518-526. doi:
10.1053/jhep.2003.50346. PMID: 12883497.
https://pubmed.ncbi.nlm.nih.gov/12883497/

**Población de validación original**: pacientes con hepatitis C crónica.
AUC 0.80 (fibrosis significativa) y 0.89 (cirrosis) en el set de
entrenamiento; 0.88 y 0.94 en el de validación.

**Puntos de corte "clásicos"** (los mismos del estudio original, ampliamente
citados en revisiones posteriores): **< 0.5** → alto valor predictivo
negativo para fibrosis significativa; **> 1.5** → sugiere fibrosis
significativa/cirrosis. Un cribado adicional de la literatura posterior
(meta-análisis) muestra que estos cortes varían bastante según la etiología
(VHC/VHB/MASLD) y el objetivo (fibrosis vs. cirrosis) — p. ej. algunos
estudios usan 0.7 o 1.0 como corte para fibrosis significativa, y 2.0 para
cirrosis con mayor especificidad — así que, a diferencia de FIB-4 (con un
único conjunto de cortes bien establecido por AASLD 2023), APRI no tiene un
único punto de corte "vigente" tan claro; habría que presentar 0.5/1.5 como
los históricos/más citados y advertir explícitamente de esta variabilidad si
se implementa.

**A favor de APRI frente a FIB-4**: no necesita la edad del paciente, así
que sí sería implementable con los datos que Analitix ya guarda hoy.

**Implementable ya**: sí, cálculo puro con `aspartat_aminotranferasa_ast_serum`
y `plaquetes` (asumiendo el límite superior normal estándar de 40 U/L para
AST, no un dato por paciente).

## Recomendación final

| Índice | Implementado | Motivo |
|---|---|---|
| AST/ALT (De Ritis) | Sí | Cálculo puro, sin datos adicionales |
| APRI | Sí | Cálculo puro, sin datos adicionales (usa 40 U/L como AST-ULN estándar) |
| FIB-4 | Sí | Edad calculada por informe desde `patients.birth_date` (`hepatic_risk._age_at`); no aparece si no se conoce la fecha de nacimiento del paciente |

Implementado en `src/analitix/hepatic_risk.py` + pestaña "🧪 Salud hepática"
(mismo patrón que `lipid_risk.py` / "❤ Riesgo cardiovascular": valor +
clasificación orientativa + aviso de límites de aplicabilidad). eGFR
CKD-EPI 2021 (`referencias_renal.md`) sigue pendiente porque, a diferencia
de FIB-4, también necesita el **sexo** del paciente, que Analitix no
guarda.
