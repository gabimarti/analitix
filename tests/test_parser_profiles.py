from analitix.parser_profiles import UNKNOWN_PROFILE, detect_profile, load_profiles


def test_load_profiles_from_package_data():
    profiles = load_profiles()
    ids = {p.id for p in profiles}
    assert "consorci_sanitari_maresme" in ids
    assert "hugtip" in ids
    maresme = next(p for p in profiles if p.id == "consorci_sanitari_maresme")
    assert not maresme.manual_review_only
    assert maresme.header_labels
    assert maresme.boundary_re is not None
    hugtip = next(p for p in profiles if p.id == "hugtip")
    assert not hugtip.manual_review_only
    assert hugtip.header_labels
    assert hugtip.bare_range_is_result
    assert not hugtip.detect_headings


def test_detect_profile_maresme_by_header_label():
    # Nombre inventado: sin datos reales de ningún informe.
    lines = ["Pacient: PEREZ RUIZ, JUAN", "Data naixement: 05/05/1975"]
    profile = detect_profile(lines)
    assert profile.id == "consorci_sanitari_maresme"


def test_detect_profile_hugtip_by_center_name():
    lines = ["Nom: PEREZ RUIZ, JUAN", "Centre: HUGTIP", "Edat: 50 anys"]
    profile = detect_profile(lines)
    assert profile.id == "hugtip"
    assert not profile.manual_review_only


def test_detect_profile_falls_back_to_unknown():
    profile = detect_profile(["texto totalmente ajeno sin ninguna señal reconocible"])
    assert profile is UNKNOWN_PROFILE
    assert profile.manual_review_only
