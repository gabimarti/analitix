# Valor de referencia del cambio (RCV) — fuentes, decisiones y limitaciones

**Implementado** en [`src/analitix/rcv.py`](../../src/analitix/rcv.py) con
los datos de
[`src/analitix/data/biological_variation.csv`](../../src/analitix/data/biological_variation.csv);
se muestra en **Resumen → "Qué ha cambiado"** (barras atenuadas) y en los gráficos de
**Evolución y de los paneles clínicos** (banda gris de variación esperable en el último
punto, centrada en el valor anterior).

Apoyo informativo, nunca un diagnóstico. Superar el RCV quiere decir "es
probable que el cambio sea real" y **no** que sea patológico. Quedar por
debajo tampoco quiere decir que el cambio no importe: una deriva lenta puede
ser real aunque cada salto sea pequeño, y para eso está la tendencia.

## 1. Qué es

Dos analíticas de la misma persona nunca dan exactamente el mismo valor,
aunque no haya cambiado nada. Hay dos fuentes de variación:

- la **variación biológica intraindividual (CVI)**: cuánto oscila el valor
  de cada persona en torno a su propio punto de equilibrio;
- la **imprecisión analítica (CVA)**: cuánto varía la medida del
  laboratorio.

El RCV es el cambio mínimo, en %, que hace falta para que la diferencia
entre dos resultados sea probablemente real (95 %) y no solo esa variación
esperable. Es un concepto estándar en medicina de laboratorio desde hace
décadas.

## 2. Fórmulas

- **Clásica (simétrica)**: RCV = √2 · Z · √(CVA² + CVI²), con Z = 1,96
  (bilateral, 95 %).
  - Fraser CG, Harris EK. "Generation and application of data on
    biological variation in clinical chemistry". *Crit Rev Clin Lab Sci*
    1989;27(5):409-437. doi:10.3109/10408368909106595, PMID 2679660.
- **Log-normal (asimétrica), la que usa Analitix**:
  - σ = √(ln(CVA²+1) + ln(CVI²+1)), con los CV expresados en fracción;
  - RCV de subida = exp(+Z·√2·σ) − 1;
  - RCV de bajada = exp(−Z·√2·σ) − 1.
  
  Con CV pequeños coincide con la clásica. Con CV grandes (PCR,
  triglicéridos, bilirrubina) evita un límite de bajada imposible por
  debajo de −100 % y respeta que estos parámetros suban más de lo que
  bajan. Es el enfoque con el que el estudio EuBIVAS calcula todos sus RCV.
  - Fokkema MR, Herrmann Z, Muskiet FAJ, Moecks J. *Clin Chem*
    2006;52(8):1602-1603. doi:10.1373/clinchem.2006.069369.
  - ⚠ La fórmula se ha tomado de trabajos que citan este artículo y del
    propio resumen EuBIVAS (§3); no se ha cotejado con el texto original
    de Fokkema.
- **CVA cuando no se conoce el del laboratorio**: Analitix usa el mayor
  entre el CVA del estudio y la especificación "deseable"
  CVA = 0,5 · CVI.
  - Ricós C, Cava F, García-Lario JV, et al. "The reference change value:
    a proposal to interpret laboratory reports in serial testing based on
    biological variation". *Scand J Clin Lab Invest* 2004;64(3):175-184.
    doi:10.1080/00365510410004885, PMID 15222627.
  - **Por qué el mayor.** El CVA de los estudios es el de laboratorios de
    referencia, que suele ser mejor que el de un laboratorio cualquiera.
    Con el mayor, el umbral es más prudente: se marcan menos cambios como
    "reales" por error.
  - El usuario puede poner el CVA real de su laboratorio en su fichero
    local (§6).

## 3. Origen de los valores (solo datos abiertos)

Analitix es gratuito y de código abierto, y **solo usa datos publicados en
abierto**. La EFLM Biological Variation Database
(<https://biologicalvariation.eu/>) es la referencia del sector, pero sus
términos de uso solo permiten extractos para uso personal no comercial.
Prohíben distribuir su contenido o guardarlo en otro sistema electrónico de
consulta sin permiso escrito. Por eso **ningún valor procede de esa web** (ni
de la tabla online de Westgard): todos salen de artículos publicados, citados
fila a fila en el CSV. Se ha pedido permiso a la EFLM; si se concede, se
indicará aquí.

Fuentes:

- **Fuente principal, resumen EuBIVAS.** Carobene A, Aarsand AK,
  Bartlett WA, et al. "The European Biological Variation Study (EuBIVAS):
  a summary report". *Clin Chem Lab Med* 2022;60(4):505-517.
  doi:10.1515/cclm-2021-0370, PMID 34049424. Valores leídos en su Tabla 2
  (acceso libre). Son adultos sanos de 6 laboratorios europeos y cumplen
  los criterios de calidad BIVAC (Aarsand AK et al., *Clin Chem*
  2018;64:501-514). La Tabla 2 recoge los artículos EuBIVAS originales, que
  son los que se citan en cada fila:
  - Aarsand AK et al. Electrolitos, lípidos, urea, ácido úrico, proteínas
    totales, bilirrubina y glucosa. *Clin Chem* 2018;64(9):1380-1393.
    doi:10.1373/clinchem.2018.288415.
  - Carobene A et al. 9 enzimas (ALT, AST, GGT, FA, LDH, amilasa…).
    *Clin Chem* 2017;63:1141-1150. doi:10.1373/clinchem.2016.269811.
  - Carobene A et al. Creatinina enzimática y de Jaffé. *Clin Chem*
    2017;63:1527-1536. doi:10.1373/clinchem.2017.275115.
  - Carobene A et al. 15 proteínas (albúmina, PCR, transferrina…).
    *Clin Chem* 2019;65(8):1031-1041. doi:10.1373/clinchem.2019.304618.
  - Bottani M et al. Tiroides. *Clin Chem Lab Med* 2022;60(4):523-532.
    doi:10.1515/cclm-2020-1885.
  - Aarsand AK et al. Coagulación. *Clin Chem* 2021;67(9):1259-1270.
    doi:10.1093/clinchem/hvab100.
- **Hemograma.** Coşkun A, Carobene A, Kilercik M, et al. "Within-subject
  and between-subject biological variation estimates of 21 hematological
  parameters in 30 healthy subjects". *Clin Chem Lab Med*
  2018;56(8):1309-1318. doi:10.1515/cclm-2017-1155, PMID 29605821. Tablas 1
  y 2 (acceso libre). Es un único centro y un único analizador (Sysmex
  XN-3000), con el protocolo EuBIVAS. Sus valores coinciden con el
  metaanálisis de Coskun A et al., *Clin Chem Lab Med* 2019;58(1):25-32
  (doi:10.1515/cclm-2019-0658), usado solo para contrastar.

## 4. Discrepancias y posibles errores conocidos

- **TSH**: la Tabla 2 del resumen EuBIVAS da un CVI de 18,9 %, pero el
  resumen del artículo original (Bottani 2022) da 17,7 %. Se usa 18,9 %,
  que es el valor visto en tabla, y la diferencia se anota en el CSV.
  Pendiente de cotejar con la Tabla 1 del artículo original.
- **Inmunoglobulinas (IgG/IgA/IgM)**: excluidas por ahora. En la tabla del
  resumen, las medias de IgA e IgG no son plausibles (posible errata) y
  hay otra discrepancia de la misma tabla con su artículo original (sTfR).
  Se incluirán cuando se coteje el artículo de 2019.
- **Diferencias por sexo sin cifras disponibles**: en urea, ácido úrico,
  triglicéridos, ALT, GGT y TTPa los artículos originales indican que el
  CVI varía según el sexo, pero esas cifras están en artículos de pago. Se
  usa el valor común y se anota en el CSV.
- **Leucocitos, neutrófilos, monocitos y eosinófilos**: Coşkun 2018 da
  valores distintos para mujeres y hombres. Analitix usa el del sexo de la
  ficha del paciente y, si no consta, el mayor de los dos (umbral más
  prudente).
- **Creatinina**: el método (Jaffé o enzimático) cambia sobre todo el CVA
  (4,4 % frente a 1,1 %). Como Analitix no conoce el método de cada
  laboratorio, usa el de Jaffé, que da el umbral más amplio.
- **LDL**: el valor del estudio es para el LDL medido. Si el informe da el
  LDL calculado (Friedewald), su variación real puede ser mayor.
- **PCR**: alrededor de una cuarta parte de los participantes de EuBIVAS
  tuvo algún episodio inflamatorio, y esos resultados se excluyeron. En la
  vida real, un episodio agudo domina cualquier cambio.
- **Basófilos**: el CVA es comparable al CVI (valores cerca del límite de
  cuantificación), así que el umbral es muy amplio.
- **TTPa**: en la tabla, el CVA (3,7 %) es mayor que el CVI (2,9 %). Es lo
  que dice la fuente, no un error de transcripción.

## 5. Excluidos a propósito

| Parámetro | Motivo |
|---|---|
| 25-OH vitamina D | No tiene estado estacionario: varía con la estación del año (EuBIVAS observó una subida de ~2,8 %/semana en primavera; Cavalier E et al., *Nutrients* 2021;13(2):431, doi:10.3390/nu13020431). El RCV no tiene sentido. |
| RDW | El dato verificado es del RDW-SD, y los informes de Analitix traen el RDW-CV. Son medidas distintas. |
| HbA1c, ferritina, vitamina B12, folato | Solo hay estudios pequeños o de calidad moderada, sin datos EuBIVAS (Carlsen S et al., *Clin Chem Lab Med* 2011;49(9):1501-1507; Ozkanay H et al., *Scand J Clin Lab Invest* 2023;83(7):509-518). |
| Hierro | EuBIVAS solo da valores por sexo y edad (Carobene A et al., *Clin Chem Lab Med* 2023;61(3):e57-e60); no se han podido verificar en el texto completo. |
| VSG | No hay un CVI en % de calidad; el único estudio (Penev MN et al., *Scand J Clin Lab Invest* 1996;56(3):285-288) da diferencias absolutas en mm/h. |
| Linfocitos (%), INR | Sin dato primario de calidad en adultos sanos. |
| Fibrinógeno derivado | Es otro método (derivado del tiempo de protrombina), distinto del fibrinógeno de Clauss que estudia EuBIVAS. |

## 6. Limitaciones y cómo corregir valores

- **Población de los estudios.** Los CVI proceden de adultos sanos en
  estado estable. En una enfermedad crónica, la variación propia puede ser
  distinta.
- **Cambio de laboratorio.** El RCV no incluye la diferencia entre
  laboratorios ni entre métodos. Si los dos valores son de laboratorios
  distintos (o uno es una entrada manual y el otro no), Analitix **no
  valora el cambio** y lo indica.
- **Detección limitada.** Un cambio justo igual al RCV solo se detecta con
  un 50 % de probabilidad: el umbral no separa de forma tajante lo real de
  lo esperable.
- **Corregir o completar valores.** Se puede crear un fichero
  `biological_variation.csv` en la carpeta de datos (junto a
  `analitix.db`), con el mismo formato que el de la aplicación. Sus filas
  sustituyen a las de la aplicación con el mismo `canonical_id`; por
  ejemplo, para poner el CVA real del propio laboratorio. Los cambios se
  aplican al reiniciar Analitix.
