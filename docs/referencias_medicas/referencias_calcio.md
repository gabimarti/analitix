# Referencias verificadas — calcio corregido por albúmina

> Parte de [`docs/referencias_medicas/`](README.md) — ver también
> [`docs/DOCUMENTACION_TECNICA.md`](../DOCUMENTACION_TECNICA.md) (sección
> `calcium_risk.py`).

Mismo criterio que `src/analitix/lipid_risk.py`: toda fórmula aquí está
verificada contra una fuente real (no de memoria) con su DOI. Implementado
en `src/analitix/calcium_risk.py` (pestaña "🦴 Calcio corregido").

Parámetros de Analitix implicados: `calci_serum`/`calci` (calcio total,
mg/dL), `albumina_serum`/`albumina_g_dl` (albúmina, g/dL — **no** la
fracción `albumina` (%) del proteinograma, magnitud distinta). Verificado
contra los 39 PDF reales del proyecto: 3 informes traen ambos valores el
mismo día.

## Fórmula de Payne (calcio corregido)

`Ca corregido (mg/dL) = Ca medido (mg/dL) + 0.8 × (4.0 − albúmina (g/dL))`

Payne RB, Little AJ, Williams RB, Milner JR. "Interpretation of serum
calcium in patients with abnormal serum proteins." Br Med J.
1973;4(5893):643-646. doi:10.1136/bmj.4.5893.643.

Cerca del 40% del calcio sérico total va unido a la albúmina; con
albúmina baja (cirrosis, malnutrición, síndrome nefrótico) el calcio
total sale artificialmente bajo en el análisis aunque el calcio libre
(fisiológicamente activo) sea normal — la corrección evita interpretar
como hipocalcemia real lo que es solo un efecto de la albúmina.

## Umbral de clasificación

**No se inventa ningún umbral nuevo**: `get_calcium_index_series` clasifica
el valor ya corregido con el `ref_low`/`ref_high` que el propio informe de
laboratorio ya trae para el calcio total ese día — mismo criterio de "no
inventar puntos de corte" ya aplicado en el resto de la app cuando existe
una alternativa mejor (aquí, el rango de referencia real del laboratorio).

## Limitación citada explícitamente

La fórmula asume una relación lineal que se degrada en los extremos
(albúmina < 2.0 o > 5.5 g/dL). Un estudio en pacientes de UCI quirúrgica
encontró que clasificaba mal el calcio (comparado con el calcio ionizado,
la referencia real) en el 38% de los casos:

Byrnes CK, Dobrez D, Gieber AJ, et al. "A comparison of corrected serum
calcium levels to ionized calcium levels among critically ill surgical
patients." Am J Surg. 2005;189(3):310-314.

Con datos ambulatorios como los de Analitix (no de UCI) el riesgo de
clasificación errónea es menor, pero sigue existiendo — se muestra en el
propio panel y en la ficha de descripción, mismo criterio de "apoyo
informativo, no diagnóstico" que el resto de la app.
