import datetime as dt

import pytest

from analitix.blood_pressure import CSV_TEMPLATE, clean_note, read_csv, validate_reading

AHORA = dt.datetime(2026, 10, 7, 12, 0)


def test_validate_reading_normalizes_and_rejects_impossible_values():
    r = validate_reading("15/01/2026 8:05", "128", "82", "", "Consulta", "  antes\tdel desayuno ", now=AHORA)
    assert r == {"measured_at": "2026-01-15 08:05", "systolic": 128, "diastolic": 82, "pulse": None,
                 "place": "consulta", "note": "antes del desayuno"}
    for args, motivo in (
        (("2026-01-15 08:00", "80", "90"), "mayor que la diastólica"),
        (("2026-01-15 08:00", "400", "90"), "fuera de los límites"),
        (("2026-01-15 08:00", "260", "90"), "fuera de los límites"),  # por defecto, sistólica 80-250
        (("2026-01-15 08:00", "12a", "80"), "solo números"),
        (("2026-01-15 08:00", "", "80"), "falta"),
        (("2027-01-01 08:00", "120", "80"), "futura"),
        (("ayer", "120", "80"), "no válidas"),
    ):
        with pytest.raises(ValueError, match=motivo):
            validate_reading(*args, now=AHORA)
    with pytest.raises(ValueError, match="lugar"):
        validate_reading("2026-01-15 08:00", "120", "80", lugar="hospital", now=AHORA)
    amplios = {"systolic": (50, 300), "diastolic": (20, 200), "pulse": (20, 250)}
    assert validate_reading("2026-01-15 08:00", "260", "90", now=AHORA, limits=amplios)["systolic"] == 260
    assert clean_note("a\x00b" + "x" * 300).startswith("a b") and len(clean_note("y" * 300)) == 200


def test_read_csv_template_omron_and_withings(tmp_path):
    plantilla = tmp_path / "plantilla.csv"
    plantilla.write_text(CSV_TEMPLATE, encoding="utf-8-sig")
    lecturas, errores = read_csv(plantilla, now=AHORA)
    assert len(lecturas) == 3 and not errores and lecturas[2]["place"] == "consulta"

    omron = tmp_path / "omron.csv"
    omron.write_text(
        "Date,Time,Systolic (mmHg),Diastolic (mmHg),Pulse (bpm),Symptoms,Consumed,TruRead,Notes\n"
        "Jan 12 2025,08:15,128,82,64,-,-,Off,ok\nJan 12 2025,21:00,abc,80,-,-,-,Off,\n", encoding="utf-8")
    lecturas, errores = read_csv(omron, now=AHORA)
    assert [(r["measured_at"], r["pulse"]) for r in lecturas] == [("2025-01-12 08:15", 64)]
    assert errores == ["Línea 3: tensión sistólica (alta) no válida: «abc» (solo números enteros)"]

    withings = tmp_path / "bp.csv"
    withings.write_text('Date,Heart rate,Systolic,Diastolic,Comments\n"2025-01-12 08:15:00",64,130,85,\n',
                        encoding="utf-8")
    assert read_csv(withings, now=AHORA)[0][0]["systolic"] == 130

    malo = tmp_path / "malo.csv"
    malo.write_text("dia;valor\n2025-01-01;120\n", encoding="utf-8")
    lecturas, errores = read_csv(malo, now=AHORA)
    assert not lecturas and errores[0].startswith("Faltan columnas")


def test_bp_readings_are_per_patient_without_duplicates_and_follow_merges(db):
    from analitix.repository import (
        add_bp_reading, delete_bp_readings, delete_patient, get_or_create_patient, list_bp_readings, merge_patients,
    )

    a, _ = get_or_create_patient(db, "PACIENTE UNO", "1970-01-01", "00000000T", "1")
    b, _ = get_or_create_patient(db, "PACIENTE DOS", "1980-01-01", "00000000A", "2")
    r1 = validate_reading("2026-01-15 08:00", "130", "85", now=AHORA)
    r2 = validate_reading("2026-01-16 08:00", "125", "80", "70", now=AHORA)
    assert add_bp_reading(db, a, r1) and not add_bp_reading(db, a, r1)  # mismo minuto: no se duplica
    assert add_bp_reading(db, b, r1, source="csv") and add_bp_reading(db, b, r2, source="csv")
    assert len(list_bp_readings(db, a)) == 1 and len(list_bp_readings(db, b)) == 2
    otra = list_bp_readings(db, b)[0]["id"]
    assert delete_bp_readings(db, a, [otra]) == 0  # solo borra las del paciente indicado
    merge_patients(db, [b], a)
    assert [r["measured_at"] for r in list_bp_readings(db, a)] == ["2026-01-15 08:00", "2026-01-16 08:00"]
    delete_patient(db, a)
    assert db.execute("SELECT COUNT(*) FROM bp_readings").fetchone()[0] == 0


def test_check_limits_keeps_user_limits_inside_absolute_bounds():
    from analitix.blood_pressure import DEFAULT_LIMITS, check_limits

    assert DEFAULT_LIMITS == {"systolic": (80, 250), "diastolic": (45, 140), "pulse": (45, 225)}
    assert check_limits({"systolic": ["90", "240"], "diastolic": [50, 130], "pulse": [40, 200]})["systolic"] == (90, 240)
    for malo in ({"systolic": [40, 250], "diastolic": [45, 140], "pulse": [45, 225]},   # por debajo del tope
                 {"systolic": [200, 150], "diastolic": [45, 140], "pulse": [45, 225]},  # mínimo > máximo
                 {"systolic": [80, 250], "diastolic": [45, 140]}):                      # falta el pulso
        with pytest.raises(ValueError):
            check_limits(malo)


def test_home_week_summary_follows_esh_protocol_and_esc_categories():
    from analitix.blood_pressure import bp_category, bp_summary_text, home_week_summary

    assert bp_category(118, 69) == "no_elevada"
    assert bp_category(125, 69) == "elevada" and bp_category(118, 75) == "elevada"
    assert bp_category(130, 85) == "hipertension"  # manda la peor cifra (diastólica)
    assert bp_category(138, 80, "consulta") == "elevada"  # en la consulta el umbral es 140/90

    def lectura(dia, hora, s, d, lugar="casa"):
        return {"measured_at": f"2026-03-{dia:02d} {hora}", "systolic": s, "diastolic": d, "pulse": 70, "place": lugar}

    # 7 días con mañana y noche; el primer día (muy alto) se descarta
    semana = [lectura(1, "08:00", 190, 110), lectura(1, "21:00", 190, 110)]
    semana += [lectura(d, h, 125, 78) for d in range(2, 8) for h in ("08:00", "21:00")]
    semana.append(lectura(20, "10:00", 150, 95, "consulta"))  # no cuenta en la media de casa
    r = home_week_summary([x for x in semana if x["place"] == "casa"])
    assert (r["n"], r["dias"], r["systolic"], r["diastolic"], r["valida"], r["categoria"]) == (
        12, 6, 125, 78, True, "elevada")
    pocas = home_week_summary(semana[:6])  # 2 días tras descartar el primero, 4 lecturas
    assert not pocas["valida"] and pocas["categoria"] is None
    texto = bp_summary_text(semana[:6])
    assert "No cumple el protocolo" in texto and "Categoría" not in texto


def test_period_stats_only_home_readings_between_dates():
    from analitix.blood_pressure import period_stats

    lecturas = [
        {"measured_at": "2020-03-01 08:00", "systolic": 120, "diastolic": 80, "pulse": 60, "place": "casa"},
        {"measured_at": "2020-03-02 08:00", "systolic": 130, "diastolic": 90, "pulse": None, "place": "casa"},
        {"measured_at": "2020-03-02 10:00", "systolic": 170, "diastolic": 100, "pulse": 80, "place": "consulta"},
        {"measured_at": "2025-03-01 08:00", "systolic": 140, "diastolic": 88, "pulse": 70, "place": "casa"},
    ]
    s = period_stats(lecturas, "2020-01-01", "2020-12-31")
    assert (s["n"], s["dias"], s["systolic"], s["diastolic"], s["pulse"]) == (2, 2, 125, 85, 60)
    assert period_stats(lecturas)["n"] == 3
    assert period_stats(lecturas, "2021-01-01", "2021-12-31") is None
