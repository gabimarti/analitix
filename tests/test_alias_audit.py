from analitix import alias_audit as aa


def test_name_signature_crosses_labs_and_languages():
    key = lambda raw: aa.name_signature(raw)[0]  # noqa: E731
    # Catalán/castellano y prefijo/tipo IUPAC de HUGTIP -> misma clave.
    assert key("Ferro sèrum") == key("Hierro") == key("Srm-Ferro, c. subst.")
    assert key("Potassi") == key("Potasio") == key("Srm-Ió Potassi; c. subst.")
    assert key("Glucosa sèrum") == key("Pla-Glucosa; c. subst.") == key("Glucosa (suero/plasma)")
    # La marca "sèrum 1" no separa, pero "Alfa 1" frente a "Alfa 2" sí.
    assert key("Aspartat aminotranferasa (AST) sèrum 1") == key("Aspartat aminotranferasa (AST) sèrum")
    assert key("Alfa 1 globulina") != key("Alfa 2 globulina")
    # La orina no es la misma prueba que en sangre; el "%" tampoco.
    assert key("Uri-Creatinini; c. subst.") != key("Creatinina sèrum")
    assert key("Linfocitos %") != key("Linfocitos")
    # Calificativos que cambian la prueba se conservan.
    assert key("Colesterol HDL") != key("Colesterol no HDL sèrum") != key("Colesterol sèrum")
    assert key("Temps de protrombina (rati) plasma") != key("Temps de protrombina (segons) plasma")


def test_abbreviations_only_count_in_parentheses_or_as_whole_name():
    assert aa.name_signature("Aspartato aminotransferasa (AST/GOT)")[1] == {"ast"}
    assert aa.name_signature("HCM")[1] == {"hcm"}
    assert aa.name_signature("Colesterol HDL")[1] == frozenset()


def test_unit_relation():
    assert aa.unit_relation({"x10^3/ul"}, {"x10^9/L", "x10³/mm³"}) == "igual"
    assert aa.unit_relation({"mEq/L"}, {"mmol/L"}) == "igual"
    assert aa.unit_relation({"mg/dL"}, {"mg/L"}) == "convertible"
    assert aa.unit_relation({"%"}, {"mmol/mol"}) == "incompatible"


def test_find_proposals_and_alias_lines():
    groups: dict = {}
    for raw, unit, lab in [
        ("Ferro sèrum", "mcg/dL", "maresme"), ("Ferro sèrum", "mcg/dL", "maresme"),
        ("Hierro", "µg/dL", "synlab"), ("Srm-Ferro, c. subst.", "µg/dL", "hugtip"),
        ("Hb glicosilada (HbA1c) sang", "%", "maresme"), ("Hb glicosilada (HbA1c) IFCC sang", "mmol/mol", "maresme"),
        ("LDH sèrum 160 UI/L", None, "maresme"),  # nombre contaminado por el parser
    ]:
        aa.add_result(groups, raw, unit, lab)
    proposals = {p.target: p for p in aa.find_proposals(groups, preferred={"ferro_serum"})}
    ferro = proposals["ferro_serum"]
    assert ferro.relation == "igual"
    assert set(aa.alias_lines(groups, ferro)) == {("hierro", "ferro_serum"), ("srm ferro c subst", "ferro_serum")}
    assert all(p.relation == "incompatible" for p in proposals.values() if "hb_glicosilada_hba1c_sang" in p.ids)
    assert not any("ldh_serum_160_ui_l" in p.ids for p in proposals.values())
    assert "LDH sèrum 160 UI/L" in aa.noisy_names(groups)


def test_ids_in_the_same_report_are_never_proposed_and_mixed_ids_are_listed():
    groups: dict = {}
    # Informe "1": glucosa en sangre y (con otro nombre) en orina, a la vez.
    aa.add_result(groups, "Glucosa sèrum", "mg/dL", "maresme", "2345-7", report="1")
    aa.add_result(groups, "Glucosa suero", "mg/dL", "synlab", report="2")
    aa.add_result(groups, "Glucosa (suero/plasma)", "mg/dL", "echevarne", report="3")
    aa.add_result(groups, "Glucosa plasma", "mg/dL", "quiron", report="1")
    proposal = next(p for p in aa.find_proposals(groups) if "glucosa_serum" in p.ids)
    assert proposal.same_report and aa.alias_lines(groups, proposal) == []

    # Un mismo id con el mismo nombre para sangre y orina (LOINC distintos).
    mixed: dict = {}
    aa.add_result(mixed, "Hematies", "x10^6/ul", "maresme", "789-8", report="1")
    aa.add_result(mixed, "Hematies", None, "maresme", "32776-7", report="1")
    assert [g.canonical_id for g, _ in aa.mixed_groups(mixed)] == ["hematies"]
    assert "## 6." in aa.render_report(mixed, [])
