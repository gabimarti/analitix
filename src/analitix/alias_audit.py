# ---------------------------------------------------------------------------
# Script: alias_audit.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-25
# ---------------------------------------------------------------------------
"""Auditoría de alias de pruebas: propone fusiones y detecta alias dudosos.

Uso (desde la raíz del proyecto, con el entorno de la aplicación):

    python -m analitix.alias_audit                 # analiza informes_analiticas/
    python -m analitix.alias_audit <carpeta> --out export/auditoria_alias.md

Parsea todos los PDF (recursivo), agrupa las determinaciones por
`canonical_id` y busca identificadores distintos que en realidad son la misma
prueba, aunque cada laboratorio la nombre distinto o en otro idioma
(catalán/castellano). Nunca modifica nada: escribe un informe Markdown para
revisar y un CSV (`alias_normalizado,canonical_id`) con las propuestas de
confianza alta, listo para copiar a `data/test_aliases.csv` tras revisarlo.
El informe solo contiene nombres de prueba y unidades — ni nombres de
fichero (llevan el CIP) ni ningún dato de paciente.

Señales usadas, de más a menos fiable:
- Mismo código LOINC (solo lo trae Maresme).
- Misma "clave" de nombre: sin prefijo de sistema IUPAC ("Srm-", "San-"),
  sin tipo de magnitud ("; c. subst."), sin palabras de muestra/método
  ("sèrum", "suero", "total"), traducida catalán/castellano a un término
  pivote y conservando la muestra si es orina (no es la misma prueba que en
  sangre) y los calificativos ("HDL", "(rati)", "Alfa 1").
- Misma abreviatura estándar entre paréntesis o como nombre completo
  ("(AST/GOT)", "HCM", "VPM").

Nunca se proponen como alias dos id que aparecen juntos en un mismo informe:
el laboratorio los midió a la vez, así que son pruebas distintas (p. ej.
glucosa en sangre y en orina); la sección 6 lista además los id que ya
mezclan nombres de un mismo informe o códigos LOINC distintos.

Y siempre, como condición: unidades compatibles. Unidades iguales o
equivalentes (x10³/µL = x10⁹/L, mEq/L = mmol/L en iones monovalentes) →
confianza alta; convertibles con factor (g/L frente a g/dL) → se informan
pero no se proponen como alias (fusionarlas mezclaría escalas en Evolución);
incompatibles (% frente a mmol/mol) → nunca se proponen.
"""
from __future__ import annotations

import argparse
import importlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from analitix.catalog import canonical_id_for
from analitix.config import PROJECT_ROOT, REPORTS_DIR
from analitix.textutils import normalize_test_name, strip_accents, unit_key

# Prefijo "Sistema-" de la nomenclatura IUPAC (HUGTIP): "Srm-", "San-", "Pla-",
# "Uri-", "Pac(Uri)-". Orina se conserva como token: no es la misma prueba.
_SYSTEM_PREFIX_RE = re.compile(r"^(pac\s*\(\s*uri\s*\)|pac|srm|san|pla|uri|ser|sng)\s*-\s*", re.I)
_URINE_PREFIXES = {"uri", "pac(uri)", "pac"}
# Tipo de magnitud IUPAC al final: "; c. subst.", ", c. massa", "; fr. vol".
_KIND_RE = re.compile(r"[;,]\s*(?:c|fr|cabal)\b\.?.*$")
# "sèrum 1", "sèrum9 U/L": marca de nota o valor pegado tras la muestra.
_SPECIMEN_TAIL_RE = re.compile(r"\b(serum|suero)\s*\d.*$")
_PAREN_RE = re.compile(r"\(([^)]*)\)")
# Nombre con un valor/unidad/rango pegado: fallo de extracción del parser.
_NOISY_NAME_RE = re.compile(r"\d\s*(?:u/?i?/?l|ui/l|mg|g/|%|u/ml)|<\s*\d|^\*|^total$", re.I)

STOPWORDS = {
    "serum", "suero", "sero", "en", "de", "del", "la", "el", "d", "l", "plasma", "sang", "sangre", "total",
    "totales", "totals", "c", "subst", "massa", "cat", "nom", "vol", "fr", "i", "y", "per", "por", "v",
    "absoluto", "absolut", "g", "dl", "mg", "ml", "u", "ui", "io", "ion",
}
# Catalán/castellano -> pivote (el catalán, que es el de los id existentes).
TRANSLATE = {
    "hierro": "ferro", "urato": "urat", "calcio": "calci", "sodio": "sodi", "potasio": "potassi",
    "cloruro": "clor", "magnesio": "magnesi", "fosforo": "fosfat", "fosfato": "fosfat",
    "plaquetas": "plaquetes", "plaquetario": "plaquetari", "plaquetar": "plaquetari",
    "leucocitos": "leucocits", "linfocitos": "limfocits", "linfocits": "limfocits",
    "neutrofilos": "neutrofils", "monocitos": "monocits", "eosinofilos": "eosinofils", "basofilos": "basofils",
    "bilirrubina": "bilirubina", "proteinas": "proteines", "creatinini": "creatinina",
    "trigliceridos": "triglicerids", "hematocrito": "hematocrit", "libre": "lliure", "folato": "folat",
    "acido": "acid", "urico": "uric", "globulinas": "globulines", "velocidad": "velocitat",
    "sedimentacion": "sedimentacio", "tiempo": "temps", "actividad": "activitat", "segundos": "segons",
    "ratio": "rati", "calculados": "calculats", "medio": "mig", "media": "mig", "mitja": "mig",
    "volumen": "volum", "concentracion": "conc", "orina": "orina", "anticuerpos": "anticossos",
    "inmunoglobulina": "immunoglobulina", "microglobulina": "microglobulina", "transaminasa": "aminotransferasa",
    "aminotranferasa": "aminotransferasa", "aspartato": "aspartat",
}
# Abreviaturas equivalentes -> pivote. Solo cuentan como señal de identidad
# si van entre paréntesis o son el nombre entero ("HCM"): en "Colesterol HDL"
# la sigla es un calificativo, no un sinónimo del nombre.
ABBREV = {
    "got": "ast", "ast": "ast", "gpt": "alt", "alt": "alt", "ggt": "ggt", "vcm": "vcm", "mcv": "vcm",
    "hcm": "hcm", "mch": "hcm", "chcm": "chcm", "mchc": "chcm", "rdw": "rdw", "vpm": "vpm", "mpv": "vpm",
    "tsh": "tsh", "t4l": "t4l", "ft4": "t4l", "ldh": "ldh", "hba1c": "hba1c", "vsg": "vsg", "alp": "alp",
    "cea": "cea", "psa": "psa", "igm": "igm", "igg": "igg", "iga": "iga", "ige": "ige", "hco3": "hco3",
}

# Unidades: (dimensión, factor a la unidad de referencia de esa dimensión).
_UNITS: dict[str, tuple[str, float]] = {
    "g/l": ("masa", 1.0), "g/dl": ("masa", 10.0), "mg/dl": ("masa", 0.01), "mg/l": ("masa", 0.001),
    "mcg/ml": ("masa", 0.001), "mcg/dl": ("masa", 1e-5), "mcg/l": ("masa", 1e-6), "ng/ml": ("masa", 1e-6),
    "ng/dl": ("masa", 1e-8), "pg/ml": ("masa", 1e-9),
    "mmol/l": ("sustancia", 1.0), "meq/l": ("sustancia", 1.0), "mcmol/l": ("sustancia", 1e-3),
    "u/l": ("actividad", 1.0), "ui/l": ("actividad", 1.0), "iu/l": ("actividad", 1.0),
    "ui/l37c": ("actividad", 1.0), "u/l37c": ("actividad", 1.0),
    "mcui/ml": ("hormona", 1.0), "mciu/ml": ("hormona", 1.0), "mu/l": ("hormona", 1.0), "mui/l": ("hormona", 1.0),
    "iu/ml": ("ui_ml", 1.0), "ui/ml": ("ui_ml", 1.0), "ku/l": ("ui_ml", 1.0), "kua/l": ("ui_ml", 1.0),
    "mmol/mol": ("mmol/mol", 1.0),
    "%": ("%", 1.0), "fl": ("fl", 1.0), "pg": ("pg", 1.0), "mm/h": ("mm/h", 1.0),
    "s": ("s", 1.0), "seg": ("s", 1.0), "segons": ("s", 1.0),
}


def unit_dimension(unit: Optional[str]) -> Optional[tuple[str, float]]:
    """(dimensión, factor) de una unidad, o `None` si no se reconoce (o no
    tiene: índices, cocientes, resultados cualitativos)."""
    u = unit_key(unit)
    if not u:
        return None
    if u.startswith("x10^3") or u.startswith("x10^9/l"):
        return ("recuento_1e9", 1.0)
    if u.startswith("x10^6") or u.startswith("x10^12/l"):
        return ("recuento_1e12", 1.0)
    if u.startswith("ml/min"):
        return ("ml/min", 1.0)
    return _UNITS.get(u)


def unit_relation(units_a: set[str], units_b: set[str]) -> str:
    """"igual" (mismas unidades o equivalentes), "convertible" (misma
    dimensión con otro factor), "incompatible", o "desconocida" si alguna
    no se reconoce."""
    dims_a = {unit_dimension(u) for u in units_a if u}
    dims_b = {unit_dimension(u) for u in units_b if u}
    if None in dims_a or None in dims_b or not dims_a or not dims_b:
        return "igual" if {unit_key(u) for u in units_a} == {unit_key(u) for u in units_b} else "desconocida"
    if dims_a == dims_b:
        return "igual"
    if {d for d, _ in dims_a} == {d for d, _ in dims_b}:
        return "convertible"
    return "incompatible"


def name_signature(raw_name: str) -> tuple[str, frozenset[str]]:
    """(clave de nombre, abreviaturas identificativas) de un nombre crudo."""
    text = strip_accents(raw_name).lower().strip()
    pct = "%" in text
    m = _SYSTEM_PREFIX_RE.match(text)
    urine = bool(m and m.group(1).replace(" ", "") in _URINE_PREFIXES)
    text = _SYSTEM_PREFIX_RE.sub("", text)
    text = _KIND_RE.sub("", text)
    text = _SPECIMEN_TAIL_RE.sub(r"\1", text)
    abbrevs: set[str] = set()
    for inner in _PAREN_RE.findall(text):
        for part in re.split(r"[/,\s]+", inner):
            if part in ABBREV:
                abbrevs.add(ABBREV[part])
    whole = re.sub(r"[^a-z0-9]", "", text)
    if whole in ABBREV:
        abbrevs.add(ABBREV[whole])
    tokens = []
    for tok in re.findall(r"[a-z0-9]+", text):
        tok = TRANSLATE.get(tok, tok)
        if tok in STOPWORDS:
            continue
        tokens.append(ABBREV.get(tok, tok))
    if urine or "orina" in tokens:
        tokens = [t for t in tokens if t != "orina"] + ["orina"]
    if pct:
        tokens.append("%")
    return " ".join(sorted(set(tokens))), frozenset(abbrevs)


@dataclass
class TestGroup:
    canonical_id: str
    raw_names: dict[str, int] = field(default_factory=dict)
    units: set[str] = field(default_factory=set)
    labs: set[str] = field(default_factory=set)
    loinc: set[str] = field(default_factory=set)
    keys: set[str] = field(default_factory=set)
    abbrevs: set[str] = field(default_factory=set)
    n: int = 0
    # Informes (clave opaca por fichero) en los que aparece cada nombre
    # crudo: dos id que coinciden en un informe no son la misma prueba.
    name_reports: dict[str, set[str]] = field(default_factory=dict)

    @property
    def reports(self) -> set[str]:
        return set().union(*self.name_reports.values())


def collect(pdf_dir: Path) -> dict[str, TestGroup]:
    """Parsea todos los PDF de `pdf_dir` (recursivo) y agrupa por `canonical_id`."""
    from analitix.pdf_parser import parse_report

    groups: dict[str, TestGroup] = {}
    for i, path in enumerate(sorted(pdf_dir.rglob("*.pdf"))):
        parsed = parse_report(path)
        for res in parsed["results"]:
            add_result(groups, res["raw_name"], res["unit"], parsed["format_id"], res.get("loinc_code"), str(i))
    return groups


def add_result(groups: dict[str, TestGroup], raw_name: str, unit: Optional[str], lab: str,
               loinc: Optional[str] = None, report: str = "") -> None:
    cid = canonical_id_for(raw_name)
    g = groups.setdefault(cid, TestGroup(cid))
    g.raw_names[raw_name] = g.raw_names.get(raw_name, 0) + 1
    if unit:
        g.units.add(unit)
    g.labs.add(lab)
    if loinc:
        g.loinc.add(loinc)
    key, abbrevs = name_signature(raw_name)
    g.keys.add(key)
    g.abbrevs |= abbrevs
    g.n += 1
    if report:
        g.name_reports.setdefault(raw_name, set()).add(report)


def panel_ids() -> set[str]:
    """`canonical_id` que usan los paneles clínicos (constantes `*_IDS`): son
    los preferidos como destino de una fusión."""
    ids: set[str] = set()
    for mod in ("calcium_risk", "glycemic_risk", "hemogram_risk", "hepatic_risk", "inflammation_risk",
                "iron_risk", "lipid_risk", "renal_risk", "thyroid_risk", "uric_acid_risk"):
        module = importlib.import_module(f"analitix.{mod}")
        for name, value in vars(module).items():
            if name.endswith("_IDS") and isinstance(value, tuple):
                ids.update(value)
    return ids


@dataclass
class Proposal:
    ids: list[str]
    reasons: list[str]
    relation: str
    target: str
    # Variantes sin ninguna unidad (resultado cualitativo o unidad no
    # extraída): no bloquean la propuesta, pero no entran en el CSV.
    unitless: list[str] = field(default_factory=list)
    # Pares de id que aparecen juntos en un mismo informe: pruebas distintas,
    # la propuesta no entra en el CSV.
    same_report: list[tuple[str, str]] = field(default_factory=list)


def _relation_of(groups: dict[str, TestGroup], cids: list[str]) -> str:
    """Relación de unidades de un conjunto de id, ignorando los que no
    tienen unidad: la peor entre todos los pares."""
    with_units = [c for c in cids if groups[c].units]
    order = ("igual", "desconocida", "convertible", "incompatible")
    worst = "igual"
    for i, a in enumerate(with_units):
        for b in with_units[i + 1:]:
            rel = unit_relation(groups[a].units, groups[b].units)
            worst = max(worst, rel, key=order.index)
    return worst


def find_proposals(groups: dict[str, TestGroup], preferred: set[str] = frozenset()) -> list[Proposal]:
    """Grupos de `canonical_id` distintos que parecen la misma prueba. Las
    señales que solapan (p. ej. misma abreviatura y misma clave de nombre)
    se unen en un único grupo; los nombres con valor/unidad pegados (fallo
    del parser) se dejan fuera."""
    noisy = set(noisy_names(groups))
    signals: dict[tuple[str, str], set[str]] = defaultdict(set)
    for cid, g in groups.items():
        if all(raw in noisy for raw in g.raw_names):
            continue
        for loinc in g.loinc:
            signals[("LOINC", loinc)].add(cid)
        for key in g.keys:
            if key:
                signals[("nombre", key)].add(cid)
        for abbrev in g.abbrevs:
            signals[("abreviatura", abbrev)].add(cid)

    # Unión de conjuntos solapados (union-find sobre los id).
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    reasons: dict[str, list[str]] = defaultdict(list)
    for (kind, value), cids in sorted(signals.items()):
        if len(cids) < 2:
            continue
        first, *rest = sorted(cids)
        for other in rest:
            parent[find(other)] = find(first)
        reasons[first].append(f"{kind}: {value}")
    components: dict[str, list[str]] = defaultdict(list)
    for cid in list(parent):
        components[find(cid)].append(cid)
    component_reasons: dict[str, list[str]] = defaultdict(list)
    for first, rs in reasons.items():
        component_reasons[find(first)] += rs

    proposals = []
    for root, cids in components.items():
        ordered = sorted(cids)
        target = max(ordered, key=lambda c: (c in preferred, bool(groups[c].units), groups[c].n, -len(c)))
        proposals.append(Proposal(
            ordered, sorted(set(component_reasons[root])), _relation_of(groups, ordered), target,
            unitless=[c for c in ordered if not groups[c].units],
            same_report=[
                (a, b) for i, a in enumerate(ordered) for b in ordered[i + 1:]
                if groups[a].reports & groups[b].reports
            ],
        ))
    return sorted(proposals, key=lambda p: p.target)


def alias_lines(groups: dict[str, TestGroup], proposal: Proposal) -> list[tuple[str, str]]:
    """Líneas `alias_normalizado,canonical_id` para fundir la propuesta en su
    destino (clave "<nombre> pct" si el nombre crudo lleva "%", igual que
    `catalog.canonical_id_for`)."""
    noisy = set(noisy_names(groups))
    if proposal.same_report:
        return []
    lines = []
    for cid in proposal.ids:
        if cid == proposal.target or cid in proposal.unitless:
            continue
        for raw in groups[cid].raw_names:
            if raw in noisy:
                continue
            norm = normalize_test_name(raw)
            lines.append((f"{norm} pct" if "%" in raw else norm, proposal.target))
    return sorted(set(lines))


def unit_conflicts(groups: dict[str, TestGroup]) -> list[TestGroup]:
    """`canonical_id` que ya mezclan unidades de dimensión distinta: alias
    probablemente equivocado (o variantes que no deberían compartir id)."""
    out = []
    for g in groups.values():
        dims = {unit_dimension(u) for u in g.units}
        known = {d for d in dims if d is not None}
        if len({d for d, _ in known}) > 1 or len(known) > 1:
            out.append(g)
    return sorted(out, key=lambda g: g.canonical_id)


def mixed_groups(groups: dict[str, TestGroup]) -> list[tuple[TestGroup, str]]:
    """`canonical_id` que probablemente ya mezclan pruebas distintas: varios
    códigos LOINC, o dos nombres crudos distintos en un mismo informe (el
    mismo dato repetido con el mismo LOINC no cuenta)."""
    out = []
    for g in sorted(groups.values(), key=lambda g: g.canonical_id):
        if len(g.loinc) > 1:
            out.append((g, f"LOINC distintos: {', '.join(sorted(g.loinc))}"))
            continue
        names = sorted(g.name_reports)
        pairs = [
            f"{a} + {b}" for i, a in enumerate(names) for b in names[i + 1:]
            if normalize_test_name(a) != normalize_test_name(b) and g.name_reports[a] & g.name_reports[b]
        ]
        if pairs and len(g.loinc) != 1:
            out.append((g, f"juntos en un mismo informe: {'; '.join(pairs)}"))
    return out


def noisy_names(groups: dict[str, TestGroup]) -> list[str]:
    """Nombres con un valor/unidad/rango pegado (fallo del parser, no de alias)."""
    return sorted({raw for g in groups.values() for raw in g.raw_names if _NOISY_NAME_RE.search(raw)})


def _fmt_group(g: TestGroup) -> str:
    names = ", ".join(f"{name} ({n})" for name, n in sorted(g.raw_names.items(), key=lambda kv: -kv[1])[:3])
    return f"`{g.canonical_id}` — {g.n} res., {', '.join(sorted(g.labs))}, unid: {', '.join(sorted(g.units)) or '—'} — {names}"


def render_report(groups: dict[str, TestGroup], proposals: list[Proposal]) -> str:
    high = [p for p in proposals if p.relation == "igual"]
    convertible = [p for p in proposals if p.relation == "convertible"]
    doubtful = [p for p in proposals if p.relation in ("incompatible", "desconocida")]
    out = [
        "# Auditoría de alias de pruebas", "",
        f"{len(groups)} identificadores (`canonical_id`), {sum(len(g.raw_names) for g in groups.values())} "
        "nombres distintos. Nada se ha modificado: revisa y copia lo que proceda a `data/test_aliases.csv`, "
        "o fusiona desde «Normalizar pruebas».", "",
        "## 1. Propuestas de fusión (unidades iguales o equivalentes)", "",
        "Destino (★) = el que usa un panel clínico o, si no, el de más resultados. Revisa que sean de verdad "
        "la misma prueba (misma muestra y método): la herramienta solo compara textos y unidades, y trata "
        "suero y plasma como equivalentes (la orina, no). Las líneas de esta sección que no llevan ⚠ están "
        "en el CSV adjunto.", "",
    ]
    def _members(p: Proposal, star: bool) -> list[str]:
        return [
            f"  - {'★ ' if star and cid == p.target else ''}{_fmt_group(groups[cid])}"
            f"{' — ⚠ sin unidad: comprobar a mano (no va al CSV)' if cid in p.unitless else ''}"
            for cid in p.ids
        ]

    for p in high:
        warn = (" — ⚠ aparecen juntas en un mismo informe: pruebas distintas, no van al CSV "
                f"({', '.join(f'{a}/{b}' for a, b in p.same_report)})") if p.same_report else ""
        out.append(f"- **{'; '.join(p.reasons)}**{warn}")
        out += _members(p, star=True)
    out += ["", "## 2. Misma prueba probable, unidades convertibles (no se proponen como alias)", "",
            "Fusionarlas mezclaría escalas en Evolución; si un panel las necesita, se añaden a su lista de "
            "identificadores con conversión (como la PCR en mg/L o la albúmina en g/L).", ""]
    for p in convertible:
        out.append(f"- **{'; '.join(p.reasons)}**")
        out += _members(p, star=False)
    out += ["", "## 3. Coincidencias descartadas por unidades incompatibles o desconocidas", "",
            "Normalmente son pruebas distintas con nombre parecido (p. ej. HbA1c en % y en mmol/mol).", ""]
    for p in doubtful:
        out.append(f"- **{'; '.join(p.reasons)}** ({p.relation})")
        out += _members(p, star=False)
    out += ["", "## 4. Identificadores que ya mezclan unidades de dimensión distinta", "",
            "Posible alias equivocado en el CSV (o dos pruebas distintas con el mismo nombre).", ""]
    out += [f"- {_fmt_group(g)}" for g in unit_conflicts(groups)] or ["- Ninguno."]
    out += ["", "## 5. Nombres con valor o unidad pegados (revisar el parser, no los alias)", ""]
    out += [f"- {name}" for name in noisy_names(groups)] or ["- Ninguno."]
    out += ["", "## 6. Identificadores que probablemente mezclan pruebas distintas", "",
            "Mismo laboratorio con el mismo nombre para muestras distintas (sangre/orina) o alias equivocado.", ""]
    out += [f"- {_fmt_group(g)} — {why}" for g, why in mixed_groups(groups)] or ["- Ninguno."]
    return "\n".join(out) + "\n"


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("carpeta", nargs="?", type=Path, default=REPORTS_DIR)
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "export" / "auditoria_alias.md")
    args = parser.parse_args(argv)

    groups = collect(args.carpeta)
    proposals = find_proposals(groups, panel_ids())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_report(groups, proposals), encoding="utf-8")
    csv_path = args.out.with_suffix(".csv")
    lines = sorted({line for p in proposals if p.relation == "igual" for line in alias_lines(groups, p)})
    csv_path.write_text("alias_normalizado,canonical_id\n" + "".join(f"{a},{c}\n" for a, c in lines), encoding="utf-8")
    print(f"Informe: {args.out}\nPropuestas (confianza alta): {csv_path} ({len(lines)} alias)")


if __name__ == "__main__":
    main()
