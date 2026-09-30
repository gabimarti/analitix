import re

import pytest

from analitix.parser_profiles import detect_profile, load_profiles
from analitix.pdf_parser import (
    _drop_overlapping_spaces,
    _extract_labeled_fields,
    _extract_range,
    _parse_date,
    _parse_lines,
    _to_float,
    apply_age_bands,
    compute_flag,
    parse_result_line,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1,25", 1.25), ("-3.0", -3.0), (" 10 ", 10.0), ("1.2.3", None), ("", None)],
)
def test_to_float(value, expected):
    assert _to_float(value) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("03/11/23 (08:46)", "2023-11-03 08:46:00"),
        ("1/2/2024", "2024-02-01"),
        ("2024-09-05 07:03:02", "2024-09-05 07:03:02"),
        # Formato HUGTIP: mes en catalán, hora pegada al año sin separador.
        ("13 de nov. 202411:23:16", "2024-11-13 11:23:16"),
        ("14 de nov. 20246:58:57", "2024-11-14 06:58:57"),
        # "de" eufonizado en "d'" delante de mes que empieza por vocal, con
        # apóstrofo tipográfico (’) o recto (') según la plantilla.
        ("17 d’abr. 2025 9:09:39", "2025-04-17 09:09:39"),
        ("17 d'abr. 2025 9:09:39", "2025-04-17 09:09:39"),
        ("not a date", None),
    ],
)
def test_parse_date_variants(text, expected):
    assert _parse_date(text) == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("Glucosa 74 - 106", ("Glucosa", "74 - 106", 74.0, 106.0)),
        ("TSH < 4,5", ("TSH", "< 4,5", None, 4.5)),
        ("HDL ( > 40 )", ("HDL", "> 40", 40.0, None)),
        # Límite inferior negativo (gasometría, p. ej. exceso de base).
        ("Excés de base -0.8 -2.0 - 2.0", ("Excés de base -0.8", "-2.0 - 2.0", -2.0, 2.0)),
    ],
)
def test_extract_ranges(content, expected):
    assert _extract_range(content) == expected


def test_labeled_fields_stop_at_next_header():
    # "Sexe:" no es un campo que se guarde, pero sí una etiqueta "frontera"
    # conocida (ver `boundary_re` en `parser_profiles.py`): sin ella, su
    # valor se comería el texto siguiente hasta la próxima etiqueta que sí
    # interesa.
    boundary_re = re.compile(r"Sexe\s*:", re.IGNORECASE)
    fields = _extract_labeled_fields(
        "Pacient: Ada Lovelace  Sexe: F  NHC: 123",
        [("full_name", r"Pacient\s*:"), ("nhc", r"NHC\s*:")],
        boundary_re,
    )
    assert fields == {"full_name": "Ada Lovelace", "nhc": "123"}


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "Glucosa sèrum (2345-6) ↑ 108 mg/dL 74 - 106",
            {
                "raw_name": "Glucosa sèrum",
                "loinc_code": "2345-6",
                "value_num": 108.0,
                "unit": "mg/dL",
                "ref_low": 74.0,
                "ref_high": 106.0,
                "flag_pdf": "alto",
            },
        ),
        (
            "Colesterol HDL 47 mg/dL 40",
            {
                "raw_name": "Colesterol HDL",
                "loinc_code": None,
                "value_num": 47.0,
                "unit": "mg/dL",
                "ref_low": 40.0,
                "ref_high": None,
                "flag_pdf": None,
            },
        ),
    ],
)
def test_parse_result_line(line, expected):
    result = parse_result_line(line)
    for key, value in expected.items():
        assert result[key] == value


@pytest.mark.parametrize(
    ("value", "low", "high", "expected"),
    [(None, 0, 1, None), (2, 0, 1, "alto"), (-1, 0, 1, "bajo"), (1, 0, 1, "normal"), (1, None, None, None)],
)
def test_compute_flag_boundaries(value, low, high, expected):
    assert compute_flag(value, low, high) == expected


def _maresme_profile():
    return next(p for p in load_profiles() if p.id == "consorci_sanitari_maresme")


def test_parse_lines_with_maresme_profile():
    # Nombre y valores inventados: nunca datos reales de un informe.
    lines = [
        "Pacient: GARCIA LOPEZ, MARIA",
        "Data naixement: 01/01/1980",
        "Secció / Sección BIOQUIMICA",
        "(1) Glucosa sèrum (2345-7) ↑121 mg/dL 82 - 115",
    ]
    parsed = _parse_lines(lines, _maresme_profile())
    assert parsed["header"]["full_name"] == "GARCIA LOPEZ, MARIA"
    assert parsed["header"]["birth_date"] == "1980-01-01"
    assert len(parsed["results"]) == 1
    result = parsed["results"][0]
    assert result["raw_name"] == "Glucosa sèrum"
    assert result["section"] == "BIOQUIMICA"
    assert result["value_num"] == 121.0
    assert result["flag_pdf"] == "alto"


@pytest.mark.parametrize("title", ["Informe", "Reedició Informe"])
def test_parse_lines_recognizes_bare_name_after_informe_title(title):
    # Plantilla 2023-2024: sin etiqueta "Pacient:", el nombre va suelto en la
    # línea siguiente a un título "Informe" — o "Reedició Informe" en una
    # reedición del mismo informe (nombre inventado).
    lines = [title, "GARCIA LOPEZ, MARIA", "Glucosa sèrum 101 mg/dl ( 82 - 115 )"]
    parsed = _parse_lines(lines, _maresme_profile())
    assert parsed["header"]["full_name"] == "GARCIA LOPEZ, MARIA"
    assert len(parsed["results"]) == 1


def _hugtip_profile():
    return next(p for p in load_profiles() if p.id == "hugtip")


def test_parse_lines_with_hugtip_profile():
    # Nombre inventado: nunca datos reales de un informe. Reproduce la
    # estructura real (sin marcador "(n)", rango suelto sin paréntesis,
    # fuera de rango con "*", línea de unidad secundaria sin nombre delante).
    lines = [
        "Nom: GARCIA LOPEZ, MARIA Petició: 123456789",
        "Centre: HUGTIP Recepció: 14 de nov. 20246:58:57",
        "SDF",
        "San-Hemoglobina, c. massa 10.4 g/dL 12.0 - 15.0 *",
        "Pla-Glucosa; c. subst. 85 mg/dL 70 - 100",
        "4.7 mmol/L 3.9 - 5.6",
    ]
    parsed = _parse_lines(lines, _hugtip_profile())
    assert parsed["header"]["full_name"] == "GARCIA LOPEZ, MARIA"
    assert len(parsed["results"]) == 2
    hemoglobina = parsed["results"][0]
    assert hemoglobina["raw_name"] == "San-Hemoglobina, c. massa"
    assert hemoglobina["value_num"] == 10.4
    assert hemoglobina["ref_low"] == 12.0
    assert hemoglobina["sample_date"] == "2024-11-14 06:58:57"
    assert hemoglobina["test_group"] is None  # "SDF" no debe colarse como grupo
    glucosa = parsed["results"][1]
    assert glucosa["raw_name"] == "Pla-Glucosa; c. subst."
    assert glucosa["value_num"] == 85.0  # la línea de unidad secundaria (SI) se descarta


def test_parse_lines_with_hugtip_bilingual_variant():
    # Variante "Laboratori Clínic Metropolitana Nord" (2026-09-23): etiquetas
    # bilingües catalán/castellano, con fecha de nacimiento y DNI en la
    # cabecera (a diferencia de la variante compacta de arriba). Datos
    # inventados: nunca datos reales de un informe.
    lines = [
        "Número de petició del laboratori / Número de petición del laboratorio:",
        "Número de petició / Número de petición SAP o ECAP: 999999999",
        "Data d'activació petició / Fecha y hora d'activación de petición: 01/06/25 9:00",
        "Nom i cognoms / Nombre y apellidos: GARCIA LOPEZ, MARIA",
        "Data naixement / Fecha de nacimiento: 01/01/1980 Sexe / Sexo: F",
        "NHC / Nº Historia Clínica: 111111 CIP autonòmic: XXYY00000000",
        "NIF / DNI: 00000000A CIP SNS: 0000000000000000",
        "Data signatura d'informe/ Fecha y hora de firma de informe: 02/06/25 10:00",
        "Data i hora recepció / Fecha y hora recepción: 01/06/25 9:30",
        "Srm-Urea; c. subst. 38.7 mg/dL 17.0 - 43.0",
        "Mètode enzimàtic(AE) 6.4 mmol/L 2.8 - 7.1",
        "Valors de normalitat en pacients amb insuficiència renal: 0.37 - 3.1",
        "Srm-Alfa 1 Globulines; fr. massa. 2.7 2.5 - 6",
    ]
    parsed = _parse_lines(lines, _hugtip_profile())
    header = parsed["header"]
    assert header["full_name"] == "GARCIA LOPEZ, MARIA"
    assert header["birth_date"] == "1980-01-01"
    assert header["nhc"] == "111111"
    assert header["dni"] == "00000000A"
    # La etiqueta señuelo ("del laboratori", sin valor en su misma línea) no
    # debe ganarle a la real vía `header.setdefault`.
    assert header["report_number"] == "999999999"
    assert header["request_date"] == "2025-06-01 09:00:00"
    assert header["validation_date"] == "2025-06-02 10:00:00"

    results_by_name = {r["raw_name"]: r for r in parsed["results"]}
    assert results_by_name["Srm-Urea; c. subst."]["value_num"] == 38.7
    assert results_by_name["Srm-Urea; c. subst."]["sample_date"] == "2025-06-01 09:30:00"
    # Línea de unidad secundaria "(AE)" del mismo resultado: no debe colarse
    # como una determinación fantasma aparte.
    assert "Mètode enzimàtic(AE)" not in results_by_name
    assert len(parsed["results"]) == 2
    # Nota a pie que por casualidad termina en un rango numérico, sin ningún
    # valor delante: descartada, no un resultado con value_num=None.
    assert "Valors de normalitat en pacients amb insuficiència renal:" not in results_by_name
    # Nombre con un dígito suelto en medio ("Alfa 1"): el valor real es el
    # último número de la línea (2.7), no el "1" de en medio.
    alfa = results_by_name["Srm-Alfa 1 Globulines; fr. massa."]
    assert alfa["value_num"] == 2.7
    assert alfa["ref_low"] == 2.5 and alfa["ref_high"] == 6.0


def _synlab_profile():
    return next(p for p in load_profiles() if p.id == "synlab")


def test_parse_lines_with_synlab_profile():
    # Datos inventados: nunca datos reales de un informe. Reproduce la
    # estructura real: rango entre corchetes, glifo "ü" delante del valor
    # en las determinaciones acreditadas ENAC, "*" de fuera de rango entre
    # el valor y la unidad (no al final de línea), un valor "DNR" (no
    # realizado) y un valor con "<" pegado al número.
    lines = [
        "Nombre: GARCIA LOPEZ, MARIA Nº Laboratorio: X0000000 - 01/01/2024",
        "Cargo: LCB-0000-EMPRESA EJEMPLO Sexo: MUJER F. Nac.: 01/01/1980",
        "Doctor: Pérez, Juan D.N.I.: 00000000A Nº Lab.: X0000000",
        "Fecha Recepción: 01/01/2024 NºHistoria: 222222",
        "Fecha Validación: 02/01/2024 NºReferencia: -",
        "Hematíes 3,89 * x106/mm³ [ 3,9 - 5,2 ]",
        "Tiempo de protrombina ü 9,8 * seg [ 10 - 13 ]",
        "Colesterol HDL ü DNR mg/dL [ > 50]",
        "Antiestreptolisinas O (ASLO) <100 UI/mL [ < 200 ]",
    ]
    parsed = _parse_lines(lines, _synlab_profile())
    header = parsed["header"]
    assert header["full_name"] == "GARCIA LOPEZ, MARIA"
    assert header["report_number"] == "X0000000"  # sin la fecha pegada de "Nº Laboratorio:"
    assert header["nhc"] is None  # "NºHistoria" es un código del laboratorio, no un NHC
    assert header["dni"] == "00000000A"  # es el del paciente pese a ir tras "Doctor:"
    assert header["sex"] == "Mujer"
    assert header["birth_date"] == "1980-01-01"
    assert header["validation_date"] == "2024-01-02"

    results_by_name = {r["raw_name"]: r for r in parsed["results"]}
    assert len(parsed["results"]) == 3
    hematies = results_by_name["Hematíes"]
    assert hematies["value_num"] == 3.89
    assert hematies["unit"] == "x106/mm³"  # el "*" mid-línea no se cuela en la unidad
    assert hematies["ref_low"] == 3.9 and hematies["ref_high"] == 5.2
    protrombina = results_by_name["Tiempo de protrombina"]
    assert protrombina["value_num"] == 9.8  # el "ü" delante del valor no rompe el parseo
    assert protrombina["unit"] == "seg"
    # DNR (no realizado): sin valor reconocible, se descarta.
    assert "Colesterol HDL" not in results_by_name
    aslo = results_by_name["Antiestreptolisinas O (ASLO)"]
    assert (aslo["value_raw"], aslo["value_num"], aslo["unit"]) == ("<100", None, "UI/mL")


def test_snb_eurofins_report_uses_synlab_profile_and_reception_date():
    # Misma plantilla que Synlab firmada como "SNB Diagnósticos Globales"
    # (Eurofins). "Fecha Informe" (fecha de descarga) no debe usarse como
    # fecha de la analítica, y una dirección colada en "NºHistoria" no es un
    # NHC. Datos inventados.
    lines = [
        "Nombre: GARCIA LOPEZ, JUAN Nº Laboratorio: X0000001 - 03/11/2025",
        "Sexo: HOMBRE F. Nac.: 01/01/1970",
        "Doctor: No consta D.N.I.: 00000000A Nº Lab.: X0000001",
        "Fecha Recepción: 03/11/2025 NºHistoria: Calle Falsa, 1. 2o 3a",
        "Fecha Validación: 04/11/2025 NºReferencia: 00000 - Ciudad",
        "Fecha Informe: 25/09/2026 Cama: Fecha petición: 03/11/2025",
        "Hemoglobina 14,1 g/dL [ 12,5 - 17,2 ]",
        "SNB Diagnósticos Globales",
    ]
    assert detect_profile(lines).id == "synlab"
    parsed = _parse_lines(lines, _synlab_profile())
    header = parsed["header"]
    assert header["sex"] == "Hombre"
    assert header["nhc"] is None
    assert header["report_number"] == "X0000001"
    assert "2026-09-25" not in (header["request_date"], header["validation_date"])
    assert parsed["results"][0]["sample_date"] == "2025-11-03"


@pytest.mark.parametrize(
    ("lines", "sample_date", "assistance", "sex"),
    [
        # 2024-2025: extracción y recepción en la misma línea; gana recepción.
        (["Sexe: Home Servei: MEDICINA",
          "Núm. història clínica: 1 Tipus petició: Rutina Núm. Assistència: 99E000001",
          "Data extracció: 01/02/2024 (08:00) Data recepció mostra: 02/02/2024 (09:00) "
          "Data validació: 05/02/2024 (10:00)"],
         "2024-02-02 09:00:00", "99E000001", "Hombre"),
        # 2014-2023: "Recepció:" y el tipo de asistencia entre paréntesis.
        (["Num. Història : 1 CIP : XXXX0000000000 Programada: 01/02/2014 Recepció: 01/02/14 (09:50)",
          "Num. Assistència : 99H000001 (Hospitalització) Servei : MEDICINA"],
         "2014-02-01 09:50:00", "99H000001", None),
        # 2025-2026 bilingüe.
        (["Data naixement / Fecha de nacimiento: 01/01/1970 (55 anys) Sexe / Sexo:Dona",
          "Servei Sol·licitant / Servicio Solicitante: MEDICINA Nº Assistència / Nº Assistencia: 99E000002",
          "Data de la mostra / Fecha y hora de toma de la muestra: 03/03/2026 09:31:07"],
         "2026-03-03 09:31:07", "99E000002", "Mujer"),
    ],
)
def test_maresme_reception_date_assistance_and_sex(lines, sample_date, assistance, sex):
    parsed = _parse_lines([*lines, "Glucosa sèrum 101 mg/dl ( 82 - 115 )"], _maresme_profile())
    assert parsed["results"][0]["sample_date"] == sample_date
    assert parsed["header"]["assistance_number"] == assistance
    assert parsed["header"]["sex"] == sex


def test_maresme_nhc_numero_historia_label():
    lines = ["Número història clinica: 123456 Tipus petició: Rutina Núm. Assistència: 99E000001"]
    assert _parse_lines(lines, _maresme_profile())["header"]["nhc"] == "123456"


@pytest.mark.parametrize(
    "line",
    [
        "Num. Història : 1 CIP : XXXX0000000000 Data/Hora : 22/03/2023 (17:49)",
        "Núm. targeta sanitària: XXXX0000000000 Sol·licitant: APELLIDO, NOMBRE",
        "DNI / NIE: 00000000A CIP-AUT:XXXX0000000000 CIP-SNS:BBBBBBBB00000000",
    ],
)
def test_maresme_cip_autonomico(line):
    # Datos inventados. Nunca el CIP-SNS estatal.
    assert _parse_lines([line], _maresme_profile())["header"]["cip"] == "XXXX0000000000"


def test_hugtip_cip_autonomico():
    lines = ["NHC / Nº Historia Clínica: 111111 CIP autonòmic: XXXX0000000000", "NIF / DNI: CIP SNS: 0000"]
    assert _parse_lines(lines, _hugtip_profile())["header"]["cip"] == "XXXX0000000000"


def test_hugtip_compact_cip_with_trailing_noise():
    # La variante compacta pega ruido de extracción tras el CIP; se guarda
    # solo el primer token en vez de descartarlo entero.
    lines = ["Centre: HUGTIP CIP: XXXX0000000000 aa"]
    assert _parse_lines(lines, _hugtip_profile())["header"]["cip"] == "XXXX0000000000"


def test_maresme_calella_2023_data_hora_is_request_date():
    # Única fecha de esa variante; sin ella el informe quedaba sin fecha.
    lines = ["Num. Història : 1 CIP : XXXX0000000000 Data/Hora : 22/03/2023 (17:49)"]
    assert _parse_lines(lines, _maresme_profile())["header"]["request_date"] == "2023-03-22 17:49:00"


def _quiron_profile():
    return next(p for p in load_profiles() if p.id == "quiron")


def test_parse_lines_with_quiron_profile():
    # Datos inventados: nunca datos reales de un informe. Reproduce la
    # estructura real: cabecera con varios campos por línea, secciones
    # marcadas por la línea fija de cabecera de columna (no por mayúsculas),
    # resultado "en casa" con "*" de fuera de rango al final de línea y
    # rango "(Inf. N)" de un único límite, y resultado "interfaced" (valor
    # en una línea que empieza por "‡", nombre en la siguiente), incluida
    # una fila con una coletilla en prosa después del rango.
    lines = [
        "Nº Laboratorio: X0000000 Fecha registro: 01/01/2024 08:00 Fecha edición: 02/01/2024 09:00",
        "Datos del paciente",
        "Razón Social: EMPRESA EJEMPLO S.L. Nombre: APELLIDO1 APELLIDO2, NOMBRE",
        "Información Adicional Nº identificación: 00000000A",
        "Sexo: VARON",
        "Fecha de nacimiento (edad): 01/01/1970 (55 años)",
        "Hemograma - Serie roja",
        "Prueba Resultado Unidades Valores de Normalidad",
        "Hemoglobina 9.9 g/dl (13 - 17) *",
        "Indicadores hepáticos",
        "Prueba Resultado Unidades Valores de Normalidad",
        "Índice de hígado graso 20 (Inf. 30)",
        "Bioquímica básica",
        "Prueba Resultado Unidades Valores de Normalidad",
        "‡ 99.9 mg/dl (74 - 109)",
        "Glucosa plasma",
        "‡ 60 mg/dl (Inf. 200) <150 para pacientes con riesgo CV",
        "Colesterol LDL calculado",
        "Fecha de toma de la muestra: 03/01/2024 10:00",
    ]
    parsed = _parse_lines(lines, _quiron_profile())
    header = parsed["header"]
    assert header["report_number"] == "X0000000"
    assert header["request_date"] == "2024-01-01 08:00:00"
    assert header["validation_date"] == "2024-01-02 09:00:00"
    assert header["full_name"] == "APELLIDO1 APELLIDO2, NOMBRE"
    assert header["dni"] == "00000000A"
    assert header["birth_date"] == "1970-01-01"
    assert header["nhc"] is None  # el documento no trae número de historia propio
    assert header["sex"] == "Hombre"

    results_by_name = {r["raw_name"]: r for r in parsed["results"]}
    assert len(parsed["results"]) == 4

    hemoglobina = results_by_name["Hemoglobina"]
    assert hemoglobina["section"] == "Hemograma - Serie roja"
    assert hemoglobina["value_num"] == 9.9 and hemoglobina["unit"] == "g/dl"
    assert hemoglobina["ref_low"] == 13.0 and hemoglobina["ref_high"] == 17.0

    higado = results_by_name["Índice de hígado graso"]
    assert higado["section"] == "Indicadores hepáticos"
    assert higado["value_num"] == 20.0 and higado["unit"] is None
    assert higado["ref_low"] is None and higado["ref_high"] == 30.0

    glucosa = results_by_name["Glucosa plasma"]
    assert glucosa["section"] == "Bioquímica básica"
    assert glucosa["value_num"] == 99.9 and glucosa["unit"] == "mg/dl"
    assert glucosa["ref_low"] == 74.0 and glucosa["ref_high"] == 109.0
    assert glucosa["sample_date"] == "2024-01-03 10:00:00"  # preescaneada pese a ir al final del documento

    ldl = results_by_name["Colesterol LDL calculado"]
    assert ldl["value_num"] == 60.0 and ldl["unit"] == "mg/dl"
    # la coletilla en prosa tras el rango no forma parte de él ni de la unidad
    assert ldl["ref_low"] is None and ldl["ref_high"] == 200.0


def _echevarne_profile():
    return next(p for p in load_profiles() if p.id == "echevarne")


def test_parse_lines_with_echevarne_profile():
    # Datos inventados: nunca datos reales de un informe. Reproduce la
    # estructura real: nombre tras un tratamiento sin etiqueta "Nombre:",
    # fila de metadatos (nº análisis + 3 fechas) sin etiquetas en la misma
    # línea, cabecera de columna con el nº de análisis inyectado en medio
    # (debe ignorarse, no leerse como sección), resultado con puntos de
    # relleno, placeholder "RESULTAT" sustituido por el título de sección,
    # resultado repartido en 3 líneas por quedar fuera de rango, y
    # resultado categórico sin unidad ni rango.
    lines = [
        "Sra. Apellido Uno Apellido Dos, Nombre CENTRO REMITENTE S.L.",
        "I.P.F.:00000000A//Data naixement:01/01/1970 (URGENT) U00000000",
        "Sexe:Dona //Referència:00000 Sra. Apellido Uno Apellido Dos, Nombre",
        "PROVA U00000000 RESULTAT UNITATS VAL.DE.REFERENCIA",
        "U00000000 01/01/2024 02/01/2024 05/01/2024(1)",
        "(LC) PROTEÏNES TOTALS / SÈRUM",
        "Espectrofotometria Ultraviolada-Visible",
        "RESULTAT......................... 64,5 g/L (57,0-82,0)",
        "(LC) PROTEÏNOGRAMA / SÈRUM",
        "Electroforesi Capil·lar",
        "SEROALBÚMINA..................... 39,0 g/L (36,0-54,0)",
        "BETA-GLOBULINA................... 12,1",
        "(cid:145)",
        "g/L (5,5-10,7)",
        "(LC) ANTICOSSOS ANTI-NUCLEARS SCREENING",
        "Inmunoanálisis de flujo multiplex",
        "RESULTAT......................... Negatiu",
    ]
    parsed = _parse_lines(lines, _echevarne_profile())
    header = parsed["header"]
    assert header["full_name"] == "Apellido Uno Apellido Dos, Nombre"
    assert header["dni"] == "00000000A"
    assert header["birth_date"] == "1970-01-01"
    assert header["report_number"] == "U00000000"
    assert header["request_date"] is None  # la toma de muestra (1ª fecha) no se guarda
    assert header["validation_date"] == "2024-01-05"
    assert header["nhc"] is None  # el documento no trae número de historia propio
    assert header["sex"] == "Mujer"

    results_by_name = {r["raw_name"]: r for r in parsed["results"]}
    assert len(parsed["results"]) == 4
    # el placeholder "RESULTAT" (sección con una única determinación) se
    # sustituye por el título de sección, nunca se guarda literal
    assert "RESULTAT" not in results_by_name

    proteines = results_by_name["(LC) PROTEÏNES TOTALS / SÈRUM"]
    assert proteines["value_num"] == 64.5 and proteines["unit"] == "g/L"
    assert proteines["ref_low"] == 57.0 and proteines["ref_high"] == 82.0
    assert proteines["sample_date"] == "2024-01-02"  # fecha de recepción

    seroalbumina = results_by_name["SEROALBÚMINA"]
    assert seroalbumina["section"] == "(LC) PROTEÏNOGRAMA / SÈRUM"
    assert seroalbumina["value_num"] == 39.0 and seroalbumina["unit"] == "g/L"

    # fila partida en 3 líneas (valor, marcador de flecha, unidad+rango):
    # recompuesta en un único resultado, sin descartar la unidad/rango
    beta = results_by_name["BETA-GLOBULINA"]
    assert beta["value_num"] == 12.1 and beta["unit"] == "g/L"
    assert beta["ref_low"] == 5.5 and beta["ref_high"] == 10.7

    nuclears = results_by_name["(LC) ANTICOSSOS ANTI-NUCLEARS SCREENING"]
    assert nuclears["value_raw"] == "Negatiu"
    assert nuclears["value_num"] is None and nuclears["unit"] is None
    assert nuclears["ref_low"] is None and nuclears["ref_high"] is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Convención catalana/española: "." agrupa millares, "," es el
        # separador decimal (visto en Echevarne).
        ("1.000", 1000.0),
        ("2.534", 2534.0),
        ("1.234,5", 1234.5),
        # Sigue funcionando igual que antes para valores sin agrupación de
        # millares (HUGTIP usa "." como separador decimal normal).
        ("-3.0", -3.0),
        ("1,25", 1.25),
    ],
)
def test_to_float_thousands_grouping(value, expected):
    assert _to_float(value) == expected


# Valores inventados; la forma de cada línea reproduce la de informes reales.
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        # Valor por debajo/encima del límite de detección: es el valor (como
        # texto, sin value_num), no parte del nombre.
        ("Factor Reumatoide sèrum <8 U/ml ( 0.01 - 14 )",
         {"raw_name": "Factor Reumatoide sèrum", "value_raw": "<8", "value_num": None, "unit": "U/ml"}),
        ("IgE clara d'ou sèrum <0.35 kU/L ( 0 - 0.10 )",
         {"raw_name": "IgE clara d'ou sèrum", "value_raw": "<0.35", "unit": "kU/L"}),
        # Marca "* " de determinación calculada: fuera del nombre.
        ("* Colesterol LDL 112 mg/dl ( 50 - 129 )", {"raw_name": "Colesterol LDL", "value_num": 112.0}),
        # Límite suelto sin "<"/">": su dirección sale de la flecha del PDF o,
        # sin flecha (valor normal), de si el valor lo supera.
        ("(1) Folat sèrum ↓<1 ng/mL 2.9",
         {"raw_name": "(1) Folat sèrum", "value_raw": "<1", "unit": "ng/mL", "ref_low": 2.9, "ref_high": None}),
        ("Filtrat glomerular estimat 95 mL/min 90", {"ref_low": 90.0, "ref_high": None}),
        ("Filtrat glomerular estimat >90 mL/min 90", {"value_raw": ">90", "ref_low": 90.0, "ref_high": None}),
        ("Colesterol sèrum 180 mg/dL 200", {"ref_low": None, "ref_high": 200.0}),
        # Rango entre paréntesis cortado tras el guion: solo mínimo.
        ("Folat 7.5 ng/ml ( 2.9 -", {"raw_name": "Folat", "value_num": 7.5, "ref_low": 2.9, "ref_high": None}),
    ],
)
def test_parse_result_line_censored_and_loose_bounds(line, expected):
    result = parse_result_line(line)
    for key, value in expected.items():
        assert result[key] == value, key


def test_maresme_old_template_ldh_temperature_and_glued_ggt():
    lines = [
        "LDH sèrum 199 UI/L 37 ºC ( 135 - 225 )",
        "Gamma Glutamil Transferasa (GGT) sèrum23 U/L ( 0 - 40 )",
        "Filtrat glomerular estimat 66 ml/mi/1.73m2 ( 90 -",
    ]
    by_name = {r["raw_name"]: r for r in _parse_lines(lines, _maresme_profile())["results"]}
    assert by_name["LDH sèrum"]["value_num"] == 199.0  # no el 37 de la temperatura
    assert by_name["Gamma Glutamil Transferasa (GGT) sèrum"]["value_num"] == 23.0
    assert by_name["Filtrat glomerular estimat"]["ref_low"] == 90.0


def test_hugtip_unranged_row_takes_recommended_range_below():
    lines = [
        "Srm-Colesterol; c. subst. 205 mg/dL",
        "Mètode Enzimàtic-Colorimètric (AE) 5.3 mmol/L",
        ".",
        "Valors recomanats:",
        "<200 ( 5.2 mmol/L )",
        "Srm-Glucosa; c. subst. 91 mg/dL",
    ]
    results = _parse_lines(lines, _hugtip_profile())["results"]
    assert [r["raw_name"] for r in results] == ["Srm-Colesterol; c. subst.", "Srm-Glucosa; c. subst."]
    assert results[0]["value_num"] == 205.0 and results[0]["ref_high"] == 200.0
    assert results[1]["value_num"] == 91.0 and results[1]["ref_text"] is None


_T4L_LINES = [
    "Tiroxina libre (T4L) ü 0,95 ng/dL",
    "Valores de referencia",
    "<1 año (0.75-1.49 ng/dL)",
    "14-19 años (0.61-1.03 ng/dL)",
    ">19 años (0.61-1.12 ng/dL)",
    "INR (Ratio Internacional Normalizado T.protrombina) ü 1,1",
]


def test_synlab_unranged_row_with_age_bands():
    lines = ["Sexo: MUJER F. Nac.: 01/01/1980", "Fecha Recepción: 01/01/2024", *_T4L_LINES]
    results = _parse_lines(lines, _synlab_profile())["results"]
    t4l, inr = results
    assert t4l["raw_name"] == "Tiroxina libre (T4L)" and t4l["value_num"] == 0.95
    assert (t4l["ref_low"], t4l["ref_high"]) == (0.61, 1.12)  # franja ">19 años"
    assert "age_bands" not in t4l
    assert inr["value_num"] == 1.1 and inr["ref_text"] is None


def test_synlab_age_bands_without_birth_date_wait_for_ingest():
    lines = ["Sexo: MUJER F. Nac.:", "Fecha Recepción: 01/01/2024", *_T4L_LINES]
    t4l = _parse_lines(lines, _synlab_profile())["results"][0]
    assert t4l["ref_text"] is None and t4l["age_bands"]
    apply_age_bands([t4l], "2010-06-01", None)  # 13 años: ninguna franja de la lista
    assert t4l["ref_text"] is None
    apply_age_bands([t4l], "2008-01-01", None)  # 16 años
    assert (t4l["ref_low"], t4l["ref_high"]) == (0.61, 1.03)


class _FakePage:
    def __init__(self, chars):
        self.chars = chars

    def filter(self, keep):
        return _FakePage([c for c in self.chars if keep(c)])


def test_drop_overlapping_spaces_keeps_normal_spaces():
    def char(text, x0, x1):
        return {"object_type": "char", "text": text, "x0": x0, "x1": x1, "top": 100.0}

    page = _FakePage([
        char("m", 0, 8), char(" ", 8, 11),  # espacio normal entre glifos
        char("1", 20, 25), char(" ", 22, 26), char("6", 25, 30),  # relleno encima del valor
    ])
    assert [c["text"] for c in _drop_overlapping_spaces(page).chars] == ["m", " ", "1", "6"]


def test_maresme_urine_section_gets_its_own_test_names():
    lines = [
        "Secció / Sección BIOQUÍMICA",
        "(1) Glucosa sèrum (2345-7) 95 mg/dL 74 - 106",
        "Secció / Sección ORINA/LÍQUIDS/SECREC.",
        "(1) Glucosa (50555-2) Negatiu",
        "(1) Densitat orina (2965-2) 1.020",
    ]
    names = [r["raw_name"] for r in _parse_lines(lines, _maresme_profile())["results"]]
    assert names == ["Glucosa sèrum", "Glucosa orina", "Densitat orina"]
