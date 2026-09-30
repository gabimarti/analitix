# Proteinograma: aviso orientativo por posible gammapatía monoclonal

> Parte de [`docs/referencias_medicas/`](README.md) — ver también
> [`docs/DOCUMENTACION_TECNICA.md`](../DOCUMENTACION_TECNICA.md).

Nota de investigación (sin código, solo documentación) — ver
una futura ampliación de proteinograma, que hoy solo
propone un gráfico de barras apiladas sin ningún cálculo/alerta clínica.
Mismo principio que el resto del proyecto: apoyo informativo, **nunca un
diagnóstico**.

## Parámetros de Analitix implicados

Confirmado mirando `src/analitix/data/descripciones/` (más completo de lo
que se había asumido al plantear esta investigación): existen fichas para
`albumina`/`frac_albumina`/`albumina_g_dl` (%, y también g/dL), `alfa_1`/
`frac_alfa_1`/`alfa_1_g_dl`, `alfa_2`/`frac_alfa_2`/`alfa_2_g_dl`, `beta`/
`frac_beta`/`beta_g_dl`, `gamma`/`frac_gamma`/`gamma_g_dl` (fracciones del
proteinograma, en % y también en g/dL), `proteines_totals`/
`proteines_totals_serum`, `quocient_albumina_globulines`. **Y, más
importante para esta idea, también existen** `immunoglobulina_g_igg_serum`,
`immunoglobulina_a_iga`/`immunoglobulina_a_iga_serum`,
`immunoglobulina_m_igm_serum` (inmunoglobulinas cuantitativas) y
`beta_2_microglobulina`/`beta_2_microglobulina_serum`.

**Lo que NO existe, confirmado con `grep`**: ningún parámetro de cadenas
ligeras libres kappa/lambda (`grep -iE "kappa|lambda|cadena|light"` sobre
el directorio no da ningún resultado relevante). Tampoco existe, ni podría
existir a partir de un PDF de resultados numéricos, la **curva real de
densitometría** de la electroforesis — solo los valores discretos por
fracción (%/g_dL) que ya lista arriba.

## Guías y hallazgos verificados

### 1. Qué distingue una gammapatía monoclonal de una elevación banal de gamma

Búsqueda cruzada de fuentes médicas de referencia (AAFP, Medscape, myeloma.org,
bpac.org.nz — verificado el contenido, no citado de memoria): en una
electroforesis de proteínas séricas, una fracción gamma elevada puede
corresponder a dos patrones con significado clínico opuesto, **distinguibles
solo por la forma de la curva**, no por el valor numérico de la fracción:

- **Patrón policlonal**: banda ancha y difusa — típico de procesos
  reactivos (infección, inflamación crónica, hepatopatía, enfermedad
  autoinmune). Es el hallazgo más frecuente y benigno de una gamma elevada.
- **Patrón monoclonal (pico M / M-spike / paraproteína)**: pico estrecho y
  bien definido ("aguja de iglesia" en la curva), producido por un único
  clon de células plasmáticas. Es el hallazgo que se asocia a gammapatía
  monoclonal de significado incierto (MGUS), mieloma múltiple, macroglobulinemia
  de Waldenström u otros procesos linfoproliferativos.

**Esto es la limitación decisiva para Analitix**: el `canonical_id`
`gamma`/`gamma_g_dl` que la app extrae es un número único (el área o
porcentaje de esa fracción), **no la curva**. Un valor de gamma alto
producido por un proceso inflamatorio banal y un valor de gamma alto
producido por un pico monoclonal pueden dar exactamente el mismo número en
Analitix — la app no tiene forma de diferenciarlos con los datos que
guarda hoy. Lo mismo aplica, por la misma razón, a un valor alto de IgG/IgA/IgM
cuantitativas: son la suma de todos los clones de esa clase de
inmunoglobulina, no solo del clon anómalo, así que tampoco distinguen por
sí solas una elevación policlonal de una monoclonal.

### 2. Criterios diagnósticos reales de mieloma/MGUS

Rajkumar SV, Dimopoulos MA, Palumbo A, et al. "International Myeloma
Working Group updated criteria for the diagnosis of multiple myeloma."
*Lancet Oncol*. 2014;15(12):e538-548. DOI: 10.1016/S1470-2045(14)70442-5.
(Citación verificada vía búsqueda cruzada).

- El diagnóstico se basa en la combinación de: células plasmáticas
  monoclonales en médula ósea (biopsia — Analitix nunca podría tener este
  dato), proteína monoclonal (mediante SPEP + inmunofijación + cadenas
  ligeras libres en suero, no solo el valor de una fracción), y los
  llamados "eventos definitorios de mieloma" (hipercalcemia, insuficiencia
  renal, anemia, lesiones óseas, más biomarcadores añadidos en 2014: ratio
  de cadenas ligeras libres ≥100, ≥60% células plasmáticas monoclonales en
  médula, o lesión focal en RMN).
- **Ninguno de estos criterios es derivable de lo que Analitix guarda.**
  La inmunofijación, la biopsia de médula y las cadenas ligeras libres no
  están ni podrían estar en un informe de analítica de sangre rutinaria de
  este tipo.

### 3. Beta-2-microglobulina: útil para estadificar, no para detectar

Greipp PR, San Miguel J, Durie BGM, et al. "International Staging System
for Multiple Myeloma." *J Clin Oncol*. 2005;23(15):3412-3420. DOI:
10.1200/JCO.2005.04.242. PMID: 15809451. (Citación verificada vía
búsqueda cruzada).

- Define el **ISS** (International Staging System), que combina
  beta-2-microglobulina sérica y albúmina en 3 estadios (I: β2M < 3.5 mg/L
  y albúmina ≥ 3.5 g/dL; II: ninguno de los otros dos; III: β2M ≥ 5.5
  mg/L) para estimar el **pronóstico de un mieloma ya diagnosticado**.
- **Importante, y motivo por el que esto no sirve para el propósito que se
  estaba investigando**: el ISS es un sistema de **estadificación
  pronóstica de una enfermedad ya diagnosticada**, no una prueba de
  cribado ni de diagnóstico. Un valor alto de beta-2-microglobulina, sin
  un mieloma ya confirmado, no es específico de esta enfermedad — también
  sube con la simple disminución de la función renal (se elimina por
  filtración glomerular) o con procesos inflamatorios/otras neoplasias,
  algo que además ya se documenta en la propia ficha de Analitix para este
  parámetro ("marcador de función renal y también en el seguimiento de
  algunas enfermedades de la sangre").

## Recomendación honesta

**No hay una forma responsable de construir un aviso de seguridad fiable
para gammapatía monoclonal/mieloma con los datos que Analitix
realmente tiene.** La pieza que de verdad distingue "posible mieloma" de
"elevación banal de gamma/inmunoglobulinas" (la forma de la curva de
electroforesis, o pruebas de confirmación como inmunofijación o cadenas
ligeras libres) no está disponible ni derivable de un informe de
laboratorio en PDF de resultados numéricos discretos — no es una
limitación de esfuerzo de implementación, es una limitación de qué datos
existen. Usar solo el valor numérico de la fracción gamma o de IgG/IgA/IgM
para generar una alerta daría, con alta probabilidad, muchos falsos
positivos en cualquier persona con una infección o proceso inflamatorio
banal en el momento de la analítica, precisamente el tipo de alerta que el
resto del proyecto ha evitado deliberadamente (ver, por comparación, cómo
`lipid_risk.py` solo usa fórmulas e índices con puntos de corte publicados
y aplicables directamente a los datos disponibles).

**Qué NO se debería implementar**: ninguna alerta basada en el valor de
gamma, IgG, IgA o IgM aislados, y ninguna alerta basada en
beta-2-microglobulina como si fuera una prueba de detección (es de
estadificación, no de diagnóstico ni cribado).

**Qué sí sigue siendo razonable** (ya estaba en la idea original, sin
cambios): el gráfico de barras apiladas en el tiempo de las fracciones del
proteinograma (§7 de la lista de ideas) tiene valor puramente descriptivo
— mostrar cómo cambian las proporciones a lo largo de los informes — sin
necesidad de ninguna interpretación clínica automática. Si el
usuario alguna vez añade manualmente un resultado de inmunofijación o
cadenas ligeras libres (vía "Entrada manual"), en ese caso sí habría datos
suficientes para una interpretación más seria — pero eso sería una
decisión distinta, no derivable de lo que un informe de proteinograma
rutinario trae hoy.
