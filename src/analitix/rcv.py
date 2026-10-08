"""Valor de referencia del cambio (RCV, *reference change value*): ¿el
cambio entre dos analíticas consecutivas es probablemente real o cabe dentro
de la variación esperable (biológica de la propia persona + analítica)?

Apoyo informativo, nunca un diagnóstico: superar el RCV significa "cambio
probablemente real", no "patológico"; y no superarlo no significa que no
importe (una deriva lenta puede ser real con saltos pequeños — para eso está
la tendencia de `charts.py`).

Datos: `data/biological_variation.csv` (`config.BUNDLED_BV_PATH`), valores de
CVI/CVA tomados solo de artículos publicados, cada fila con su cita; más una
capa opcional del usuario (`config.BV_PATH`, mismo formato) cuyas filas
sustituyen a las de la aplicación. Fuentes, discrepancias y valores
excluidos: `docs/referencias_medicas/referencias_rcv.md`.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from analitix.config import BUNDLED_BV_PATH, BV_PATH

# Z bilateral al 95 %: el cambio puede ser al alza o a la baja (Fraser CG,
# Harris EK, "Generation and application of data on biological variation in
# clinical chemistry", Crit Rev Clin Lab Sci 1989;27(5):409-437,
# doi:10.3109/10408368909106595).
Z_95 = 1.96

# Si no se conoce el CVA del laboratorio del usuario se usa como mínimo la
# especificación "deseable" CVA = 0,5·CVI (Ricós C et al., Scand J Clin Lab
# Invest 2004;64(3):175-184, doi:10.1080/00365510410004885). El CVA de los
# estudios es el de laboratorios de referencia, normalmente mejor que el de
# cualquier laboratorio: tomar el mayor de los dos da un umbral más prudente
# (menos cambios marcados como "probablemente reales" por error).
CVA_FRACCION_DE_CVI = 0.5


@dataclass(frozen=True)
class VariacionBiologica:
    analito: str
    cvi_pct: Optional[float]
    cvi_mujer_pct: Optional[float]
    cvi_hombre_pct: Optional[float]
    cva_pct: Optional[float]
    fuente: str
    doi: str
    tabla: str
    nota: str

    def cvi_para(self, sex: Optional[str]) -> Optional[float]:
        """CVI aplicable: el común, o el del sexo del paciente si el
        artículo los da por separado; sin sexo conocido, el mayor (umbral
        más prudente)."""
        if self.cvi_pct is not None:
            return self.cvi_pct
        por_sexo = {"Mujer": self.cvi_mujer_pct, "Hombre": self.cvi_hombre_pct}
        if por_sexo.get(sex) is not None:
            return por_sexo[sex]
        valores = [v for v in por_sexo.values() if v is not None]
        return max(valores) if valores else None


def _num(texto: Optional[str]) -> Optional[float]:
    texto = (texto or "").strip()
    return float(texto) if texto else None


def read_table(path: Path) -> dict[str, VariacionBiologica]:
    """Lee un CSV de variación biológica (líneas que empiezan por "#" son
    comentarios). Fichero inexistente → tabla vacía."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        filas = csv.DictReader(line for line in f if not line.lstrip().startswith("#"))
        return {
            fila["canonical_id"].strip(): VariacionBiologica(
                analito=(fila.get("analito") or "").strip(),
                cvi_pct=_num(fila.get("cvi_pct")),
                cvi_mujer_pct=_num(fila.get("cvi_mujer_pct")),
                cvi_hombre_pct=_num(fila.get("cvi_hombre_pct")),
                cva_pct=_num(fila.get("cva_pct")),
                fuente=(fila.get("fuente") or "").strip(),
                doi=(fila.get("doi") or "").strip(),
                tabla=(fila.get("tabla") or "").strip(),
                nota=(fila.get("nota") or "").strip(),
            )
            for fila in filas
            if (fila.get("canonical_id") or "").strip()
        }


@lru_cache(maxsize=1)
def load_table() -> dict[str, VariacionBiologica]:
    """Tabla de la aplicación + la del usuario (gana la del usuario).
    Se lee una vez por sesión: los cambios en el fichero del usuario se
    aplican al reiniciar la aplicación."""
    tabla = read_table(BUNDLED_BV_PATH)
    if BV_PATH != BUNDLED_BV_PATH:
        tabla.update(read_table(BV_PATH))
    return tabla


def rcv_limits(cvi_pct: float, cva_pct: Optional[float] = None, z: float = Z_95) -> tuple[float, float]:
    """Límites (bajada, subida) del RCV en % con el modelo log-normal
    (asimétrico), el que usa el propio estudio EuBIVAS para todos sus RCV:
    σ = √(ln(CVA²+1) + ln(CVI²+1)) con los CV en fracción;
    RCV = exp(±Z·√2·σ) − 1 (Fokkema MR et al., Clin Chem
    2006;52(8):1602-1603, doi:10.1373/clinchem.2006.069369; fórmula
    tomada de trabajos que lo citan, ver referencias_rcv.md). Con CV pequeños coincide con la
    fórmula clásica √2·Z·√(CVA²+CVI²) (Fraser & Harris 1989); con CV
    grandes (PCR, triglicéridos, bilirrubina) evita un límite de bajada
    imposible por debajo de −100 %."""
    cva = max(cva_pct or 0.0, CVA_FRACCION_DE_CVI * cvi_pct)
    sigma = math.sqrt(math.log((cva / 100) ** 2 + 1) + math.log((cvi_pct / 100) ** 2 + 1))
    k = z * math.sqrt(2) * sigma
    return (math.exp(-k) - 1) * 100, (math.exp(k) - 1) * 100


def classify_change(
    canonical_id: Optional[str],
    previous: Optional[float],
    value: Optional[float],
    sex: Optional[str] = None,
    lab_previous: Optional[str] = None,
    lab: Optional[str] = None,
    table: Optional[dict[str, VariacionBiologica]] = None,
) -> Optional[dict[str, Any]]:
    """Clasifica el cambio `previous` → `value`. Devuelve `None` si no hay
    variación biológica para el parámetro o los valores no lo permiten
    (≤ 0: el modelo es logarítmico); si no, un dict con `estado`:

    - "real": supera el RCV — cambio probablemente real (no "patológico");
    - "esperable": dentro de la variación biológica + analítica esperable;
    - "otro_lab": los dos valores son de laboratorios distintos (o uno sin
      laboratorio, p. ej. entrada manual): el RCV no incluye la diferencia
      entre laboratorios/métodos, así que no se clasifica;

    más `pct`, `rcv_bajada`, `rcv_subida`, `analito`, `fuente` y `nota`."""
    if canonical_id is None or previous is None or value is None or previous <= 0 or value <= 0:
        return None
    bv = (load_table() if table is None else table).get(canonical_id)
    cvi = bv.cvi_para(sex) if bv else None
    if cvi is None:
        return None
    bajada, subida = rcv_limits(cvi, bv.cva_pct)
    pct = (value - previous) / previous * 100
    if (lab_previous or None) != (lab or None):
        estado = "otro_lab"
    else:
        estado = "real" if pct > subida or pct < bajada else "esperable"
    return {
        "estado": estado, "pct": pct, "rcv_bajada": bajada, "rcv_subida": subida,
        "analito": bv.analito, "fuente": bv.fuente, "nota": bv.nota,
    }


# Mínimo de valores previos en estado estable para el rango personal: con 3
# o más el intervalo ya es robusto (Coşkun et al. 2021, ver
# `personal_range`).
PERSONAL_MIN_POINTS = 3


def personal_range(
    canonical_id: Optional[str],
    series: list[dict[str, Any]],
    sex: Optional[str] = None,
    table: Optional[dict[str, VariacionBiologica]] = None,
) -> Optional[dict[str, Any]]:
    """Rango de referencia personalizado (prRI) a partir del propio
    historial — Coşkun A, Sandberg S, Unsal I, et al. Clin Chem
    2021;67(2):374-384, doi:10.1093/clinchem/hvaa233 (ecuación 4: intervalo
    de predicción con media desconocida y varianza conocida):

        punto de equilibrio (SP) = media de n valores en estado estable
        prRI = SP · (1 ± Z·√((n+1)/n)·√(CVI² + CVA²) / 100)

    Valores usados ("estado estable", decisión de diseño): los anteriores
    al último que estaban **dentro del rango de referencia de su propio
    informe** (nunca uno fuera de rango, para no "normalizar" lo anormal),
    sin el último, que es el que se compara con el rango. CVA efectivo =
    máx(CVA del estudio, 0,5·CVI), igual que el RCV. El límite inferior no
    baja de 0. `None` si no hay variación biológica para el parámetro o
    hay menos de `PERSONAL_MIN_POINTS` valores válidos.

    Devuelve `bajo`, `alto`, `punto`, `n`, `labs` (cuántos laboratorios
    aportan valores: el modelo supone un mismo método), `fuente` y
    `nota`."""
    if canonical_id is None or len(series) < PERSONAL_MIN_POINTS + 1:
        return None
    bv = (load_table() if table is None else table).get(canonical_id)
    cvi = bv.cvi_para(sex) if bv else None
    if cvi is None:
        return None
    base = [
        s for s in series[:-1]
        if s.get("flag_calc") not in ("alto", "bajo")
        and (s.get("ref_low") is not None or s.get("ref_high") is not None)
        and s.get("value_num") is not None
    ]
    if len(base) < PERSONAL_MIN_POINTS:
        return None
    n = len(base)
    punto = sum(s["value_num"] for s in base) / n
    cva = max(bv.cva_pct or 0.0, CVA_FRACCION_DE_CVI * cvi)
    semiancho_pct = Z_95 * math.sqrt((n + 1) / n) * math.sqrt(cvi ** 2 + cva ** 2)
    return {
        "bajo": max(0.0, punto * (1 - semiancho_pct / 100)),
        "alto": punto * (1 + semiancho_pct / 100),
        "punto": punto, "n": n, "labs": len({s.get("lab") for s in base}),
        "fuente": bv.fuente, "nota": bv.nota,
    }


# -- Deriva lenta (CUSUM) ----------------------------------------------------
# CUSUM tabular (Page ES, "Continuous inspection schemes", Biometrika
# 1954;41(1-2):100-115, doi:10.1093/biomet/41.1-2.100) sobre la propia serie,
# en unidades de la variación esperable (σ = √(ln(CVA²+1) + ln(CVI²+1)), la
# misma que el RCV): detecta un desplazamiento pequeño y sostenido que el RCV
# entre dos analíticas no ve. k = 0,5 y h = 5 son los valores habituales
# (Montgomery DC, Introduction to Statistical Quality Control): falsa alarma
# media cada ~465 puntos sin cambio real y un desplazamiento de 1 σ detectado
# en ~10. Precedentes clínicos: CUSUM de creatinina en trasplante renal
# (Piccoli A et al., Nephron 1987;47(2):87-94, doi:10.1159/000184467) y
# gráficos de control en pacientes individuales (Tennant R et al., Int J Qual
# Health Care 2007;19(4):187-94, doi:10.1093/intqhc/mzm015).
CUSUM_K = 0.5
CUSUM_H = 5.0
# Punto de equilibrio: media de las primeras CUSUM_BASELINE analíticas dentro
# de rango del tramo (fase de referencia), para no vigilar con los mismos
# datos que lo definen; hacen falta al menos CUSUM_MIN_MONITORED después.
CUSUM_BASELINE = 4
CUSUM_MIN_MONITORED = 3


def cusum_drift(
    canonical_id: Optional[str],
    series: list[dict[str, Any]],
    sex: Optional[str] = None,
    table: Optional[dict[str, VariacionBiologica]] = None,
) -> Optional[dict[str, Any]]:
    """Deriva lenta y sostenida respecto al punto de equilibrio propio.

    Solo el tramo final de un mismo laboratorio (un cambio de método se
    confundiría con una deriva). Punto de equilibrio = media de sus primeras
    `CUSUM_BASELINE` analíticas dentro de rango; después, para cada valor,
    z = (ln x − ln punto) / σ, S⁺ = máx(0, S⁺ + z − k), S⁻ = máx(0, S⁻ − z − k).
    Devuelve `None` sin variación biológica o con datos insuficientes; si
    no, `direccion` ("sube", "baja" o `None` si ninguna suma supera h en la
    última analítica), `desde` (fecha en que empezó a acumularse esa suma),
    `punto`, `n` (analíticas vigiladas) y `fuente`."""
    if canonical_id is None or not series:
        return None
    bv = (load_table() if table is None else table).get(canonical_id)
    cvi = bv.cvi_para(sex) if bv else None
    if cvi is None:
        return None
    lab = series[-1].get("lab")
    inicio = len(series)
    while inicio > 0 and series[inicio - 1].get("lab") == lab:
        inicio -= 1
    tramo = [s for s in series[inicio:] if s.get("value_num") and s["value_num"] > 0]
    base_idx = [i for i, s in enumerate(tramo)
                if s.get("flag_calc") not in ("alto", "bajo")
                and (s.get("ref_low") is not None or s.get("ref_high") is not None)][:CUSUM_BASELINE]
    if len(base_idx) < CUSUM_BASELINE:
        return None
    vigilados = tramo[base_idx[-1] + 1:]
    if len(vigilados) < CUSUM_MIN_MONITORED:
        return None
    punto = sum(tramo[i]["value_num"] for i in base_idx) / CUSUM_BASELINE
    cva = max(bv.cva_pct or 0.0, CVA_FRACCION_DE_CVI * cvi)
    sigma = math.sqrt(math.log((cva / 100) ** 2 + 1) + math.log((cvi / 100) ** 2 + 1))
    s_alta = s_baja = 0.0
    desde_alta = desde_baja = None
    for s in vigilados:
        z = (math.log(s["value_num"]) - math.log(punto)) / sigma
        s_alta, s_baja = max(0.0, s_alta + z - CUSUM_K), max(0.0, s_baja - z - CUSUM_K)
        desde_alta = (desde_alta or s.get("fecha")) if s_alta > 0 else None
        desde_baja = (desde_baja or s.get("fecha")) if s_baja > 0 else None
    direccion, desde = None, None
    if s_alta > CUSUM_H:
        direccion, desde = "sube", desde_alta
    elif s_baja > CUSUM_H:
        direccion, desde = "baja", desde_baja
    return {"direccion": direccion, "desde": desde, "punto": punto, "n": len(vigilados), "fuente": bv.fuente}


def cusum_note(drift: Optional[dict[str, Any]]) -> Optional[str]:
    """Frase para el recuadro bajo el gráfico, solo si hay deriva."""
    if not drift or not drift.get("direccion"):
        return None
    lado = "por encima" if drift["direccion"] == "sube" else "por debajo"
    return (f"Cambio lento: desde {(drift['desde'] or '')[:7]} tus valores han ido quedando {lado} de tu "
            f"valor habitual ({drift['punto']:.3g}, la media de tus primeras analíticas normales). En cada "
            "analítica la diferencia es pequeña, pero se repite: puede ser un cambio real y lento. No es un "
            "diagnóstico; si continúa, coméntalo con tu médico.")
