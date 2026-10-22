"""Base de datos de ejemplo con un paciente **ficticio** y analíticas
inventadas de tres laboratorios, más tensión arterial y un objetivo del
médico. La usan el botón «Base de datos de ejemplo...» de la lista de bases
de datos y `scripts/doc_screenshots.py` (capturas de la documentación), así
que las dos muestran exactamente lo mismo. Semillas fijas: siempre se
generan los mismos valores. Nunca contiene datos reales."""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

from analitix import databases, db, repository
from analitix.pdf_parser import compute_flag

# Entrada de la lista de bases de datos y contraseña de la BD de ejemplo. La
# contraseña es pública a propósito: solo contiene datos ficticios.
DEMO_NAME = "Ejemplo (datos ficticios)"
DEMO_FILE = "analitix-ejemplo"
DEMO_PASSWORD = "analitix-demo"

# Analíticas ficticias: (fecha, laboratorio). Tres laboratorios para que se
# vean la forma del punto por laboratorio y los nombres de prueba distintos.
REPORTS = [
    ("2020-02-11", "Synlab/Eurofins"),
    ("2020-09-22", "Synlab/Eurofins"),
    ("2021-03-09", "Synlab/Eurofins"),
    ("2021-10-14", "HUGTIP"),
    ("2022-05-18", "HUGTIP"),
    ("2022-12-01", "HUGTIP"),
    ("2023-06-20", "HUGTIP"),
    ("2024-01-16", "H. Mataró"),
    ("2024-06-04", "H. Mataró"),
    ("2024-11-19", "H. Mataró"),
    ("2025-03-11", "H. Mataró"),
    ("2025-10-07", "H. Mataró"),
    ("2026-02-03", "H. Mataró"),
    ("2026-04-14", "H. Mataró"),
]
LAB_INDEX = {"H. Mataró": 0, "Synlab/Eurofins": 1, "HUGTIP": 2}


# Estilo de cada serie ficticia, para que no todas se parezcan: (estilo,
# tendencia). "suave" = deriva lenta; "brusco" = deriva lenta más uno o dos
# saltos puntuales. Tendencia en amplitudes a lo largo de todo el periodo
# (+ sube, - baja; 0 = sin tendencia). Por defecto ("suave", 0).
STYLES = {
    "hemoglobina": ("suave", -0.8),
    "hematies": ("suave", -0.5),
    "rdw_cv": ("suave", 0.6),
    "neutrofils_total": ("brusco", 0.0),
    "plaquetes": ("suave", 0.3),
    "ferro_serum": ("brusco", 0.4),
    "ferritina_serum": ("suave", 1.0),
    "colesterol_serum": ("suave", -1.0),
    "colesterol_ldl": ("brusco", -0.7),
    "triglicerids_serum": ("brusco", 0.0),
    "glucosa_serum": ("suave", 0.9),
    "hb_glicosilada_hba1c_sang": ("suave", 1.0),
    "alanina_aminotransferasa_alt_serum": ("brusco", 0.0),
    "creatinina_serum": ("suave", 0.8),
    "filtrat_glomerular_estimat_serum": ("suave", -0.9),
    "urat_serum": ("brusco", 0.3),
    "proteina_c_reactiva_serum": ("brusco", 0.0),
    "vsg_velocitat_de_sedimentacio_globular": ("brusco", 0.0),
    "tirotropina_tsh_serum": ("suave", 0.7),
}


def synthetic_series(seed: str, mid: float, amp: float) -> list[float]:
    """Valores de una serie ficticia alrededor de `mid` (escala `amp`):
    paseo aleatorio con memoria (cada valor se parece al anterior, como en
    una analítica real), más la tendencia y los saltos de su estilo
    (`STYLES`). Semilla fija por parámetro: cada ejecución da las mismas
    capturas."""
    style, trend = STYLES.get(seed, ("suave", 0.0))
    rng = random.Random(seed)
    n = len(REPORTS)
    drift = rng.uniform(-0.4, 0.4)
    values = []
    for i in range(n):
        drift = 0.8 * drift + rng.gauss(0, 0.3)
        values.append(mid + amp * (trend * (2 * i / (n - 1) - 1) + drift))
    if style == "brusco":
        for i in rng.sample(range(2, n), rng.choice((1, 2))):
            values[i] = mid + amp * rng.choice((-1, 1)) * rng.uniform(1.1, 1.5)
    return [max(v, mid * 0.1) for v in values]  # nunca negativos


# canonical_id, (nombre Mataró, nombre Synlab, nombre HUGTIP), (unidad por laboratorio), rango,
# (centro, escala) de la serie sintética (ver `synthetic_series`), decimales
PARAMS = [
    (
        "hemoglobina",
        ("Hemoglobina", "Hemoglobina", "San-Hemoglobina, c. massa"),
        ("g/dL",) * 3,
        (13.0, 17.0),
        (15.0, 2.4),
        1,
    ),
    (
        "hematies",
        ("Hematies", "Hematíes", "San-Hematies, c. nom."),
        ("x10^6/ul", "x106/mm³", "x10^12/L"),
        (4.5, 5.9),
        (5.2, 0.9),
        2,
    ),
    (
        "vcm",
        ("VCM", "Volumen corpuscular medio (VCM)", "San-Volum Corpuscular Mig, vol"),
        ("fL",) * 3,
        (80.0, 100.0),
        (90.0, 12.0),
        1,
    ),
    (
        "rdw_cv",
        ("RDW-CV", "Indice de anisocitosis (RDW)", "San-Ample Distribució Eritrocits,"),
        ("%",) * 3,
        (11.5, 15.0),
        (13.3, 2.2),
        1,
    ),
    (
        "neutrofils_total",
        ("Neutròfils total", "Neutrófilos", "San-Neutròfils, c. nom"),
        ("x10^3/ul", "x10³/mm³", "x10^9/L"),
        (2.0, 7.5),
        (4.7, 3.3),
        2,
    ),
    (
        "linfocits_total",
        ("Limfòcits total", "Linfocitos", "San-Limfòcits, c. nom"),
        ("x10^3/ul", "x10³/mm³", "x10^9/L"),
        (1.0, 3.0),
        (2.0, 1.2),
        2,
    ),
    (
        "monocits_total",
        ("Monòcits total", "Monocitos", "San-Monòcits, c. nom"),
        ("x10^3/ul", "x10³/mm³", "x10^9/L"),
        (0.2, 0.8),
        (0.5, 0.35),
        2,
    ),
    (
        "plaquetes",
        ("Plaquetes", "Plaquetas", "San-Plaquetes, c. nom"),
        ("x10^3/ul", "x10³/mm³", "x10^9/L"),
        (150.0, 400.0),
        (275.0, 150.0),
        0,
    ),
    (
        "ferro_serum",
        ("Ferro sèrum", "Hierro", "Srm-Ferro, c. subst."),
        ("mcg/dL", "µg/dL", "µg/dL"),
        (59.0, 158.0),
        (105.0, 60.0),
        0,
    ),
    (
        "ferritina_serum",
        ("Ferritina sèrum", "Ferritina", "Srm-Ferritina, c. subst."),
        ("ng/mL",) * 3,
        (30.0, 400.0),
        (220.0, 200.0),
        0,
    ),
    (
        "transferrina_serum",
        ("Transferrina sèrum", "Transferrina", "Srm-Transferrina"),
        ("mg/dL",) * 3,
        (200.0, 360.0),
        (280.0, 100.0),
        0,
    ),
    (
        "colesterol_serum",
        ("Colesterol sèrum", "Colesterol total", "Srm-Colesterol; c. subst."),
        ("mg/dL",) * 3,
        (None, 200.0),
        (205.0, 45.0),
        0,
    ),
    (
        "colesterol_hdl",
        ("Colesterol HDL", "Colesterol HDL", "Srm-Colesterol HDL"),
        ("mg/dL",) * 3,
        (40.0, None),
        (48.0, 14.0),
        0,
    ),
    (
        "colesterol_ldl",
        ("Colesterol LDL", "Colesterol LDL", "Srm-Colesterol LDL"),
        ("mg/dL",) * 3,
        (None, 130.0),
        (130.0, 40.0),
        0,
    ),
    (
        "triglicerids_serum",
        ("Triglicèrids sèrum", "Triglicéridos", "Srm-Triglicèrids; c. subst."),
        ("mg/dL",) * 3,
        (None, 150.0),
        (145.0, 70.0),
        0,
    ),
    (
        "glucosa_serum",
        ("Glucosa sèrum", "Glucosa (suero/plasma)", "Srm-Glucosa; c. subst."),
        ("mg/dL",) * 3,
        (70.0, 105.0),
        (92.0, 22.0),
        0,
    ),
    (
        "hb_glicosilada_hba1c_sang",
        ("Hb glicosilada (HbA1c) sang", "Hemoglobina A1c (NGSP)", "San-HbA1c"),
        ("%",) * 3,
        (4.0, 5.7),
        (5.5, 0.6),
        1,
    ),
    (
        "aspartat_aminotranferasa_ast_serum",
        (
            "Aspartat aminotranferasa (AST) sèrum",
            "Aspartato aminotransferasa (AST/GOT)",
            "Srm-Aspartat-aminotransferasa; c. cat.",
        ),
        ("U/L",) * 3,
        (10.0, 40.0),
        (30.0, 18.0),
        0,
    ),
    (
        "alanina_aminotransferasa_alt_serum",
        (
            "Alanina aminotransferasa (ALT) sèrum",
            "Alanina aminotransferasa (ALT/GPT)",
            "Srm-Alanina-aminotransferasa; c. cat.",
        ),
        ("U/L",) * 3,
        (7.0, 41.0),
        (32.0, 20.0),
        0,
    ),
    (
        "creatinina_serum",
        ("Creatinina sèrum", "Creatinina", "Srm-Creatinini; c. subst."),
        ("mg/dL",) * 3,
        (0.6, 1.2),
        (0.95, 0.35),
        2,
    ),
    (
        "filtrat_glomerular_estimat_serum",
        (
            "Filtrat glomerular estimat sèrum",
            "Filtrado glomerular estimado",
            "Srm-Filtrat glomerular estimat",
        ),
        ("mL/min/1,73m2",) * 3,
        (60.0, None),
        (78.0, 25.0),
        0,
    ),
    (
        "urea_serum",
        ("Urea sèrum", "Urea", "Srm-Urea; c. subst."),
        ("mg/dL",) * 3,
        (17.0, 49.0),
        (34.0, 20.0),
        0,
    ),
    (
        "urat_serum",
        ("Urat sèrum", "Urato", "Srm-Urat; c. subst."),
        ("mg/dL",) * 3,
        (3.4, 7.0),
        (6.0, 1.8),
        1,
    ),
    (
        "calci",
        ("Calci", "Calcio total", "Srm-Calci(II); c. subst."),
        ("mg/dL",) * 3,
        (8.5, 10.5),
        (9.5, 1.2),
        1,
    ),
    (
        "albumina_serum",
        ("Albúmina sèrum", "Albúmina sèrum", "Albúmina sèrum"),
        ("g/dL",) * 3,
        (3.5, 5.2),
        (4.3, 1.0),
        1,
    ),
    (
        "proteina_c_reactiva_serum",
        ("Proteïna C reactiva sèrum", "Proteína C reactiva", "Proteïna C reactiva sèrum"),
        ("mg/dL",) * 3,
        (0.0, 0.5),
        (0.6, 0.55),
        2,
    ),
    (
        "vsg_velocitat_de_sedimentacio_globular",
        (
            "VSG velocitat de sedimentació globular",
            "Velocidad de sedimentación globular (VSG)",
            "San-VSG",
        ),
        ("mm/h",) * 3,
        (0.0, 20.0),
        (15.0, 12.0),
        0,
    ),
    (
        "tirotropina_tsh_serum",
        ("Tirotropina (TSH) sèrum", "Hormona estimulante del tiroides (TSH)", "Srm-TSH"),
        ("mcUI/mL", "mU/L", "mcUI/mL"),
        (0.35, 4.94),
        (2.8, 2.6),
        2,
    ),
    (
        "tiroxina_lliure_t4l",
        ("Tiroxina lliure (T4L)", "Tiroxina libre (T4L)", "Srm-Tiroxina lliure"),
        ("ng/dL",) * 3,
        (0.7, 1.48),
        (1.1, 0.5),
        2,
    ),
]


def build_demo_db(path: Path, password: str = DEMO_PASSWORD, reports_dir: str | None = None):
    """Crea en `path` la BD cifrada de ejemplo (paciente «FICTICIO,
    PACIENTE» y sus analíticas) y devuelve `(con, pid)` con la conexión
    abierta. `reports_dir`: carpeta de informes que se guarda en la BD
    (las capturas usan una ficticia; la app no la fija)."""
    con = db.connect(password, path)
    pid, _ = repository.get_or_create_patient(
        con,
        "FICTICIO, PACIENTE",
        "1970-05-15",
        "00000000T",
        "000000",
        sex="Hombre",
        cip="FICT0000000000",
    )
    repository.update_patient(
        con,
        pid,
        {
            "smoker_current": 0,
            "smoker_former": 1,
            "smoker_former_from": 1995,
            "smoker_former_to": 2008,
        },
    )
    if reports_dir:
        repository.set_setting(con, "reports_dir", reports_dir)
    series = {cid: synthetic_series(cid, mid, amp) for cid, _n, _u, _r, (mid, amp), _d in PARAMS}
    for n, (fecha, lab) in enumerate(REPORTS):
        name = f"informe_ficticio_{fecha}.pdf"
        rid = repository.upsert_report(
            con,
            pid,
            f"DEMO-{n:04d}",
            fecha,
            fecha,
            name,
            file_md5=hashlib.md5(name.encode()).hexdigest(),
            lab=lab,
        )
        li = LAB_INDEX[lab]
        for cid, names, units, (low, high), _osc, decimals in PARAMS:
            value = round(series[cid][n], decimals)
            repository.insert_result(
                con,
                rid,
                dict(
                    section=None,
                    test_group=None,
                    loinc_code=None,
                    raw_name=names[li],
                    canonical_id=cid,
                    value_raw=f"{value:g}",
                    value_num=value,
                    unit=units[li],
                    ref_low=low,
                    ref_high=high,
                    ref_text=None,
                    flag_pdf=None,
                    flag_calc=compute_flag(value, low, high),
                    sample_date=f"{fecha} 08:30:00",
                ),
            )
    # Tensión arterial de ejemplo (ficticia): dos semanas de mañana y noche
    # en casa, con deriva lenta, y dos tomas en la consulta.
    rng = random.Random("tension")
    sis, dia = 128.0, 82.0
    for d in range(14):
        for hora in ("07:45", "21:30"):
            sis = 0.7 * sis + 0.3 * 128 + rng.gauss(0, 5)
            dia = 0.7 * dia + 0.3 * 82 + rng.gauss(0, 3)
            repository.add_bp_reading(
                con,
                pid,
                {
                    "measured_at": f"2026-03-{d + 1:02d} {hora}",
                    "systolic": round(sis),
                    "diastolic": round(dia),
                    "pulse": rng.randint(60, 76),
                    "place": "casa",
                    "note": "antes del desayuno" if hora == "07:45" else None,
                },
                source="csv",
            )
    for fecha, s, di in (("2026-02-10 10:30", 138, 88), ("2026-04-14 09:15", 134, 85)):
        repository.add_bp_reading(
            con,
            pid,
            {
                "measured_at": fecha,
                "systolic": s,
                "diastolic": di,
                "pulse": 70,
                "place": "consulta",
                "note": "revisión",
            },
        )
    # Objetivo del médico de ejemplo (ficticio), para las capturas del LDL.
    repository.set_target(con, pid, "colesterol_ldl", None, 100.0, "Ejemplo ficticio")
    con.commit()
    return con, pid


def create_demo_database() -> bool:
    """Crea la BD de ejemplo en la carpeta de pacientes y la añade a la lista
    (`DEMO_NAME`, fichero `DEMO_FILE`, contraseña `DEMO_PASSWORD`). Devuelve
    `False` si ya estaba (no la toca). Si falla a medias, no deja ni la
    entrada ni el fichero."""
    if databases.find_database(DEMO_FILE):
        if databases.db_path(DEMO_FILE).exists():
            return False
        databases.remove_database(DEMO_FILE)  # borrada fuera de la app: se rehace
    databases.add_database(DEMO_NAME, DEMO_FILE)
    path = databases.db_path(DEMO_FILE)
    try:
        con, _pid = build_demo_db(path)
        con.close()
    except Exception:
        databases.remove_database(DEMO_FILE)
        path.unlink(missing_ok=True)
        raise
    return True
