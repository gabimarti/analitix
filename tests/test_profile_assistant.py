"""Asistente de plantillas de laboratorio (lógica sin interfaz).

Solo texto inventado con la estructura de cada laboratorio (la misma de
`test_pdf_parser.py`): ningún dato de un informe real."""

import pytest

from analitix import config, profile_assistant as pa
from analitix.parser_profiles import (
    ProfileValidationError,
    load_profiles,
    profile_from_data,
    profile_issues,
    validate_user_profile_data,
)
from analitix.pdf_parser import _parse_lines

# DNI inventado con letra de control válida (la comprobación de privacidad
# del asistente debe bloquearlo). Se monta aquí para que el número completo
# no aparezca escrito en el fichero (`scripts/check_privacy.py` lo tomaría
# por real); 00000000 no sirve: el asistente lo trata como sintético.
FAKE_DNI = "12345678" + "TRWAGMYFPDXBNJZSQVHLCKE"[12345678 % 23]

MARESME = [
    "Pacient: GARCIA LOPEZ, MARIA",
    "Data naixement: 01/01/1980",
    "Secció / Sección BIOQUIMICA",
    "(1) Glucosa sèrum (2345-7) ↑121 mg/dL 82 - 115",
    "(2) Colesterol sèrum (2093-3) 180 mg/dL 120 - 200",
]
HUGTIP = [
    "Nom: GARCIA LOPEZ, MARIA Petició: 123456789",
    "Centre: HUGTIP Recepció: 14 de nov. 20246:58:57",
    "SDF",
    "San-Hemoglobina, c. massa 10.4 g/dL 12.0 - 15.0 *",
    "Pla-Glucosa; c. subst. 85 mg/dL 70 - 100",
    "4.7 mmol/L 3.9 - 5.6",
]
SYNLAB = [
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
QUIRON = [
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
ECHEVARNE = [
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
LABS = {
    "consorci_sanitari_maresme": MARESME,
    "hugtip": HUGTIP,
    "synlab": SYNLAB,
    "quiron": QUIRON,
    "echevarne": ECHEVARNE,
}
EXPECTED_GRAMMAR = {
    "consorci_sanitari_maresme": "marcadores",
    "hugtip": "rango_suelto",
    "synlab": "marcadores",
    "quiron": "fila_partida",
    "echevarne": "puntos_relleno",
}


def _app(profile_id):
    return next(p for p in load_profiles() if p.id == profile_id)


def _names(results):
    return sorted(r["raw_name"] for r in results)


# -- Propuesta completa: los 5 laboratorios ------------------------------------


@pytest.mark.parametrize("lab", sorted(LABS))
def test_best_grammar_per_lab(lab):
    assert pa.analyze(LABS[lab]).best.key == EXPECTED_GRAMMAR[lab]


@pytest.mark.parametrize("lab", sorted(LABS))
def test_proposed_template_reads_the_same_results_as_the_app_one(lab):
    # La plantilla propuesta, escrita a `.toml`, releída y validada como del
    # usuario, saca los mismos resultados que la plantilla de la aplicación.
    lines = LABS[lab]
    proposal = pa.propose_template(lines, f"nuevo_{lab}"[:64], "Laboratorio de prueba")
    text = pa.render_toml(proposal.data)
    data = pa.check_template_text(text, pa.private_values(lines, proposal.data))
    ours = _parse_lines(lines, profile_from_data(data))["results"]
    theirs = _parse_lines(lines, _app(lab))["results"]
    assert _names(ours) == _names(theirs)
    by_name = {r["raw_name"]: r for r in theirs}
    for r in ours:
        assert (r["value_num"], r["unit"], r["ref_low"], r["ref_high"]) == (
            by_name[r["raw_name"]]["value_num"],
            by_name[r["raw_name"]]["unit"],
            by_name[r["raw_name"]]["ref_low"],
            by_name[r["raw_name"]]["ref_high"],
        )


@pytest.mark.parametrize("lab", sorted(LABS))
def test_proposed_template_never_carries_patient_data(lab):
    text = pa.render_toml(pa.propose_template(LABS[lab], "nuevo", "Lab").data)
    for dato in ("GARCIA", "APELLIDO", "Apellido Uno", "00000000A", "1980", "1970", "X0000000"):
        assert dato not in text


def test_urine_section_gets_a_name_suffix_like_the_app_template():
    lines = [
        "Pacient: GARCIA LOPEZ, MARIA",
        "Secció / Sección BIOQUÍMICA",
        "(1) Glucosa sèrum (2345-7) 95 mg/dL 74 - 106",
        "Secció / Sección ORINA/LÍQUIDS/SECREC.",
        "(1) Glucosa (50555-2) Negatiu",
        "(1) Densitat orina (2965-2) 1.020",
    ]
    data = pa.propose_template(lines, "orina", "Orina").data
    assert data["section_name_suffixes"] == {"ORINA/LÍQUIDS/SECREC.": "orina"}
    assert data["known_text_values"] == ["Negatiu"]
    names = _names(_parse_lines(lines, profile_from_data(data))["results"])
    assert names == _names(_parse_lines(lines, _app("consorci_sanitari_maresme"))["results"])


def test_specific_marker_for_rows_without_range():
    lines = [
        *SYNLAB,
        "Tiroxina libre (T4L) ü 1,10 ng/dL",
        "Valores de referencia",
        ">19 años (0.61-1.12 ng/dL)",
    ]
    data = pa.propose_template(lines, "synlab_mio", "Synlab").data
    assert data["unranged_result_re"] == r" ü -?[\d.,]+(?: \S+)?$"
    assert data["following_range_labels"] == ["Valores de referencia"]
    names = _names(_parse_lines(lines, profile_from_data(data))["results"])
    assert "Tiroxina libre (T4L)" in names


def test_grammar_choice_ignores_rows_that_only_look_like_results():
    # Una nota que termina en un rango no hace ganar a «rango suelto».
    lines = [*MARESME, "Nivell desitjable < 100", "Classe 1 - 2"]
    assert pa.analyze(lines).best.key == "marcadores"
    hugtip = pa.analyze([*HUGTIP, "Mètode enzimàtic(AE) 6.4 mmol/L 2.8 - 7.1"] * 2)
    assert ("(AE)", 2) in pa.skip_marker_candidates(hugtip.best)


def test_proposal_warns_when_nothing_is_recognised():
    lines = ["Texto narrativo sin resultados", "Otra línea cualquiera"]
    proposal = pa.propose_template(lines, "vacio", "Vacío")
    assert any("motor nuevo" in w for w in proposal.warnings)
    assert any("nombre del paciente" in w for w in proposal.warnings)


def test_proposal_rejects_an_unsafe_id():
    with pytest.raises(ValueError):
        pa.propose_template(MARESME, "../fuera", "Lab")


# -- Cabecera ---------------------------------------------------------------------


def test_header_labels_and_suggested_fields():
    found = {c.label: c.suggested_key for c in pa.header_label_candidates(SYNLAB)}
    assert found["Nombre"] == "full_name"
    assert found["Nº Laboratorio"] == "report_number"
    assert found["Sexo"] == "sex"
    assert found["F. Nac."] == "birth_date"
    assert found["D.N.I."] == "dni"  # no «Juan D.N.I.»: el nombre del médico no es etiqueta
    assert found["Fecha Recepción"] == "sample_date"
    assert found["Fecha Validación"] == "validation_date"
    assert found["Cargo"] is None  # sin campo: frontera


def test_header_labels_glued_bilingual_and_with_hours():
    found = {c.label: c.suggested_key for c in pa.header_label_candidates(QUIRON)}
    assert found["Fecha registro"] == "request_date"  # el «08:00» no es una etiqueta
    assert found["Fecha edición"] == "validation_date"
    assert found["Fecha de nacimiento (edad)"] == "birth_date"
    assert found["Nº identificación"] == "dni"
    assert found["Fecha de toma de la muestra"] == "sample_date"
    glued = {c.label: c.suggested_key for c in pa.header_label_candidates(ECHEVARNE)}
    assert glued["I.P.F."] == "dni"
    assert glued["Data naixement"] == "birth_date"


def test_label_candidates_keep_the_kind_never_the_value():
    for c in pa.header_label_candidates(SYNLAB):
        assert "GARCIA" not in repr(c) and "00000000A" not in repr(c)
    kinds = {c.label: c.value_kind for c in pa.header_label_candidates(SYNLAB)}
    assert kinds["F. Nac."] == "fecha" and kinds["D.N.I."] == "documento"


def test_label_pattern_matches_like_the_engine():
    pattern = pa.label_pattern("Fecha de toma de la muestra")
    validate_user_profile_data(
        {
            "id": "x",
            "name": "x",
            "signature": {"requires_any": ["x"]},
            "header_labels": [{"key": "sample_date", "pattern": pattern}],
        }
    )
    import re

    assert re.search(pattern, "FECHA DE  TOMA DE LA MUESTRA: 03/01/2024", re.IGNORECASE)
    assert pa.label_pattern("Recepció") == r"Recepcio\s*:"


# -- Firma, secciones, metadatos ---------------------------------------------------


def test_signature_candidates_skip_texts_of_other_templates():
    lines = ["Laboratori Clínic Ficticio del Nord", "Synlab Diagnósticos Globales", *SYNLAB]
    found = pa.signature_candidates(lines, other_documents=[["Otro laboratorio"]])
    assert found[0].text == "Laboratori Clínic Ficticio del Nord" and not found[0].used_by
    synlab = next(c for c in found if c.text.startswith("Synlab"))
    assert synlab.used_by == ["synlab"]
    seen_elsewhere = pa.signature_candidates(lines, [["Laboratori Clínic Ficticio del Nord"]])
    ficticio = next(c for c in seen_elsewhere if c.text.startswith("Laboratori"))
    assert ficticio.in_other_documents == 1


def test_a_line_with_a_person_name_is_never_a_signature():
    # Echevarne: el nombre del paciente comparte línea con el centro remitente.
    texts = [c.text for c in pa.signature_candidates(ECHEVARNE)]
    assert not any("Apellido" in t for t in texts)
    assert pa.signature_candidates(["Dra. Ficticia Laboratorio Central"]) == []


def test_sections_and_column_headers():
    quiron = pa.section_candidates(QUIRON)
    assert [c.text for c in quiron] == [
        "Hemograma - Serie roja",
        "Indicadores hepáticos",
        "Bioquímica básica",
    ]
    assert pa.base_settings(QUIRON)["section_after_anchor"] == QUIRON[7]
    echevarne = pa.base_settings(ECHEVARNE)
    assert echevarne["detect_headings"] is True
    import re

    assert re.match(
        echevarne["ignore_line_patterns"][0], "PROVA U12345678 RESULTAT UNITATS VAL.DE.REFERENCIA"
    )
    assert [c.reason for c in pa.section_candidates(MARESME)] == ["marcador del motor"]


def test_metadata_row_pattern_from_roles():
    assert pa.metadata_row_candidates(ECHEVARNE) == [4]
    pattern = pa.metadata_row_pattern(
        ECHEVARNE[4], ["report_number", None, "sample_date", "validation_date"]
    )
    proposal = pa.propose_template(ECHEVARNE, "echevarne_mio", "Echevarne")
    proposal.data["metadata_row_re"] = pattern
    header = _parse_lines(ECHEVARNE, profile_from_data(proposal.data))["header"]
    assert header["report_number"] == "U00000000"
    assert header["validation_date"] == "2024-01-05"
    with pytest.raises(ValueError):
        pa.metadata_row_pattern(ECHEVARNE[4], ["report_number"])


# -- Números y unidades --------------------------------------------------------------


@pytest.mark.parametrize(
    ("lab", "separator"),
    [
        ("synlab", ","),
        ("echevarne", ","),
        ("hugtip", "."),
        ("quiron", "."),
        ("consorci_sanitari_maresme", "auto"),
    ],
)
def test_document_decimal_convention(lab, separator):
    assert pa.analyze(LABS[lab]).convention.separator == separator


def test_ambiguous_values_with_and_without_range():
    rows = [
        {"raw_name": "pH", "value_raw": "7.349", "ref_low": 7.32, "ref_high": 7.43},
        {"raw_name": "Leucocitos", "value_raw": "7.349", "ref_low": None, "ref_high": None},
    ]
    ph, leuco = pa.ambiguous_values(rows, "auto")
    assert ph.proposed == 7.349 and not ph.doubtful
    assert leuco.proposed == 7349.0 and leuco.doubtful
    (comma,) = pa.ambiguous_values(rows[1:], ",")
    assert comma.proposed == 7349.0 and not comma.doubtful
    (point,) = pa.ambiguous_values(rows[1:], ".")
    assert point.proposed == 7.349


def test_units_known_unknown_and_suspicious():
    rows = [
        {"raw_name": "Glucosa", "unit": "mg/dL"},
        {"raw_name": "Colesterol HDL", "unit": "mg/dL 40"},
        {"raw_name": "Índice", "unit": "ratio raro"},
        {"raw_name": "Hematíes", "unit": "* x106/mm³"},
    ]
    units = {u.unit: u for u in pa.classify_units(rows)}
    assert units["mg/dL"].status == "conocida" and units["mg/dL"].dimension == "masa"
    assert units["mg/dL 40"].status == "sospechosa"
    assert units["ratio raro"].status == "desconocida"
    assert units["* x106/mm³"].status == "sospechosa"


# -- Parámetros y duplicados -----------------------------------------------------------


def test_new_parameter_with_a_possible_match_in_the_database():
    known = [{"raw_name": "Factor ficticio", "unit": "mg/dL", "source_file": "a.pdf"}]
    rows = [{"raw_name": "Factor ficticio sèrum", "unit": "mg/dL"}]
    (match,) = pa.parameter_matches(rows, known)
    assert match.status == "nuevo"
    assert [c.canonical_id for c in match.candidates] == ["factor_ficticio"]
    assert match.candidates[0].relation == "igual"
    assert pa.aliases_for({"Glucosa sèrum": "glucosa"}) == {"glucosa serum": "glucosa"}


def test_never_proposes_a_test_that_appears_in_the_same_report():
    known = [{"raw_name": "Factor ficticio", "unit": "mg/dL", "source_file": "a.pdf"}]
    rows = [
        {"raw_name": "Factor ficticio", "unit": "mg/dL"},
        {"raw_name": "Factor ficticio sèrum", "unit": "mg/dL"},
    ]
    existing, new = pa.parameter_matches(rows, known)
    assert existing.status == "base de datos"
    assert new.status == "nuevo" and new.candidates == []


def test_incompatible_units_are_not_proposed():
    known = [{"raw_name": "Factor ficticio", "unit": "mg/dL", "source_file": "a.pdf"}]
    (match,) = pa.parameter_matches([{"raw_name": "Factor ficticio sèrum", "unit": "%"}], known)
    assert match.candidates == []


def test_catalog_parameters():
    (match,) = pa.parameter_matches([{"raw_name": "Hemoglobina", "unit": "g/dL"}])
    assert match.status in ("catálogo", "nuevo")
    import analitix.catalog as catalog

    catalog.add_aliases({"hemoglobina": "hemoglobina"})
    (match,) = pa.parameter_matches([{"raw_name": "Hemoglobina", "unit": "g/dL"}])
    assert match.status == "catálogo"


# -- Evaluación y comparaciones -----------------------------------------------------------


def test_evaluate_reports_fields_read_and_review_reasons():
    data = pa.propose_template(SYNLAB, "synlab_mio", "Synlab").data
    data["required_fields"] = ["full_name", "cip"]
    evaluation = pa.evaluate(SYNLAB, data)
    assert evaluation.header_read["full_name"] and evaluation.header_read["birth_date"]
    assert evaluation.header_read["sample_date"]
    assert evaluation.missing_required == ["cip"]
    assert "faltan campos obligatorios: cip" in evaluation.review_reasons
    assert all(isinstance(v, bool) for v in evaluation.header_read.values())
    assert len(evaluation.results) == 3


def test_evaluate_without_signature_and_with_near_misses():
    data = {"id": "x", "name": "x", "signature": {"requires_any": ["NO APARECE"]}}
    evaluation = pa.evaluate(["Glucosa 85 mg/dL sin rango"], data)
    assert not evaluation.signature_matches
    assert "la firma de la plantilla no aparece en el documento" in evaluation.review_reasons
    assert evaluation.near_misses == [0] and evaluation.coverage == 0.0


def test_compare_results_and_header_fields():
    reference = [
        {"raw_name": "Glucosa", "value_raw": "85", "unit": "mg/dL", "ref_text": "70 - 100"},
        {"raw_name": "Urea", "value_raw": "30", "unit": "mg/dL", "ref_text": "17 - 43"},
    ]
    candidate = [
        {"raw_name": "Glucosa", "value_raw": "85", "unit": "mmol/L", "ref_text": "70 - 100"},
        {"raw_name": "Sodio", "value_raw": "140", "unit": "mmol/L", "ref_text": "135 - 145"},
    ]
    diff = pa.compare_results(reference, candidate)
    assert [r["raw_name"] for r in diff.missing] == ["Urea"]
    assert [r["raw_name"] for r in diff.extra] == ["Sodio"]
    assert [(a["raw_name"], fields) for a, _, fields in diff.changed] == [("Glucosa", ["unit"])]
    assert pa.compare_results(reference, reference).same
    fields = pa.compare_header_fields(SYNLAB, [_app("synlab"), _app("quiron")])
    assert fields["synlab"]["full_name"] and not fields["quiron"]["birth_date"]


# -- TOML: escritura, validación, privacidad, guardado ----------------------------------------


def _minimal(**extra):
    return {"id": "lab_x", "name": "Lab X", "signature": {"requires_any": ["LAB X"]}, **extra}


def test_render_roundtrip_with_quotes_backslashes_and_control_chars():
    data = _minimal(
        boundary_terms=["Data d'activació", "Ref\x0cerència\x00"],
        ignore_line_patterns=[r"^PROVA\s+\d+$"],
        header_labels=[{"key": "full_name", "pattern": r"Nom\s*:"}],
        section_name_suffixes={"ORINA/LÍQUIDS": "orina"},
    )
    back = pa.check_template_text(pa.render_toml(data))
    assert back["boundary_terms"] == ["Data d'activació", "Referència"]
    assert back["ignore_line_patterns"] == [r"^PROVA\s+\d+$"]
    assert back["section_name_suffixes"] == {"ORINA/LÍQUIDS": "orina"}


def test_render_rejects_unknown_keys_and_check_rejects_dangerous_patterns():
    with pytest.raises(ProfileValidationError):
        pa.render_toml(_minimal(ejecutar="algo"))
    text = pa.render_toml(_minimal(ignore_line_patterns=["(a+)+$"]))
    with pytest.raises(ProfileValidationError):
        pa.check_template_text(text)


@pytest.mark.parametrize(
    "fuga",
    [
        {"boundary_terms": ["GARCIA LOPEZ, MARIA"]},  # valor de la cabecera
        {"boundary_terms": ["Garcia Lopez"]},  # los apellidos de «Apellidos, Nombre»
        {"known_text_values": [FAKE_DNI]},  # DNI con letra válida
        {"known_text_values": ["01/02/2024"]},  # una fecha concreta
    ],
)
def test_privacy_check_blocks_patient_data(fuga):
    text = pa.render_toml(_minimal(**fuga))
    with pytest.raises(pa.TemplatePrivacyError) as exc:
        pa.check_template_text(text, {"GARCIA LOPEZ, MARIA"})
    assert "GARCIA" not in str(exc.value) and FAKE_DNI not in str(exc.value)


def test_private_values_of_a_document():
    values = pa.private_values(SYNLAB, pa.propose_template(SYNLAB, "s", "S").data)
    assert "GARCIA LOPEZ, MARIA" in values and "00000000A" in values
    assert not any("EMPRESA" in v for v in values)  # «Cargo» no es un dato del paciente


def test_save_user_template_with_backup_and_conflict(tmp_path):
    text = pa.render_toml(_minimal())
    saved = pa.save_user_template(text)
    assert saved.path == config.USER_PARSER_PROFILES_DIR / "lab_x.toml"
    assert saved.backup is None and not saved.same_id_as_app
    assert any(p.id == "lab_x" and p.origin == "usuario" for p in load_profiles())
    with pytest.raises(FileExistsError):
        pa.save_user_template(text)
    again = pa.save_user_template(text, overwrite=True)
    assert again.backup.parent == config.USER_PARSER_PROFILES_DIR / "copias"
    assert sum(p.id == "lab_x" for p in load_profiles()) == 1  # la copia no se carga

    conflict = pa.save_user_template(pa.render_toml(_minimal(id="hugtip")))
    assert conflict.same_id_as_app
    assert any(i.kind == "conflicto" and i.profile_id == "hugtip" for i in profile_issues())


def test_save_refuses_a_template_with_patient_data():
    text = pa.render_toml(_minimal(boundary_terms=["GARCIA LOPEZ, MARIA"]))
    with pytest.raises(pa.TemplatePrivacyError):
        pa.save_user_template(text, {"GARCIA LOPEZ, MARIA"})
    assert not (config.USER_PARSER_PROFILES_DIR / "lab_x.toml").exists()


def test_required_fields_validation():
    validate_user_profile_data(_minimal(required_fields=["full_name", "sample_date"]))
    with pytest.raises(ProfileValidationError):
        validate_user_profile_data(_minimal(required_fields=["telefono"]))
