"""Plantillas de laboratorio del usuario: carga, validación y conflictos.

Solo texto inventado: ningún dato de un informe real."""

import json

import pytest

from analitix import config
from analitix.parser_profiles import (
    ProfileValidationError,
    check_pattern,
    detect_profile,
    load_profiles,
    matching_profiles,
    profile_issues,
    reload_profiles,
    validate_user_profile_data,
)

LAB_FICTICIO = """
id = "lab_ficticio"
name = "Laboratorio Ficticio de Pruebas"
priority = 5
bare_range_is_result = true

[signature]
requires_any = ["LABORATORIO FICTICIO XYZ"]

[[header_labels]]
key = "full_name"
pattern = 'Paciente\\s*:'
"""


def _write(name: str, text: str):
    folder = config.USER_PARSER_PROFILES_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(text, encoding="utf-8")
    reload_profiles()
    return path


def _valid_data(**extra):
    data = {
        "id": "lab_ficticio",
        "name": "Laboratorio Ficticio",
        "signature": {"requires_any": ["LABORATORIO FICTICIO XYZ"]},
    }
    data.update(extra)
    return data


def test_without_user_folder_only_app_templates_load():
    profiles = load_profiles()
    assert profiles and all(p.origin == "app" for p in profiles)
    assert profile_issues() == []


def test_user_template_is_loaded_and_detected():
    _write("lab_ficticio.toml", LAB_FICTICIO)
    profile = next(p for p in load_profiles() if p.id == "lab_ficticio")
    assert profile.origin == "usuario"
    assert profile.path.name == "lab_ficticio.toml"
    assert detect_profile(["LABORATORIO FICTICIO XYZ", "Paciente: PRUEBA, ANA"]).id == (
        "lab_ficticio"
    )


def test_invalid_user_template_is_reported_and_does_not_break_loading():
    _write("roto.toml", 'id = "roto"\nname = ')  # TOML no válido
    _write("lab_ficticio.toml", LAB_FICTICIO)
    ids = {p.id for p in load_profiles()}
    assert "lab_ficticio" in ids and "roto" not in ids
    issues = profile_issues()
    assert [(i.file, i.kind) for i in issues] == [("roto.toml", "error")]


def test_same_id_as_app_template_is_a_conflict_until_the_user_decides():
    texto = LAB_FICTICIO.replace('"lab_ficticio"', '"hugtip"')
    _write("hugtip.toml", texto)
    hugtip = next(p for p in load_profiles() if p.id == "hugtip")
    assert hugtip.origin == "app"
    assert [(i.kind, i.profile_id) for i in profile_issues()] == [("conflicto", "hugtip")]

    config.APP_CONFIG_PATH.write_text(
        json.dumps({"plantillas_sustituidas": ["hugtip"]}), encoding="utf-8"
    )
    hugtip = next(p for p in reload_profiles() if p.id == "hugtip")
    assert hugtip.origin == "usuario"
    assert profile_issues() == []


def test_matching_profiles_lists_every_signature_that_matches():
    _write("lab_ficticio.toml", LAB_FICTICIO)
    lines = ["LABORATORIO FICTICIO XYZ", "Centre: HUGTIP"]
    ids = [p.id for p in matching_profiles(lines)]
    assert ids[0] == detect_profile(lines).id
    assert set(ids) == {"lab_ficticio", "hugtip"}


@pytest.mark.parametrize(
    "pattern",
    [r"(a+)+$", r"(\s*x)*y", r"((ab)*)*", r"(x+){3}", "x" * 301, r"(", 42],
)
def test_dangerous_or_invalid_patterns_are_rejected(pattern):
    with pytest.raises(ProfileValidationError):
        check_pattern(pattern, "prueba")


@pytest.mark.parametrize(
    "pattern",
    [
        r"Nom(?:\s*/\s*[A-Za-zÀ-ÿ.º ]+)?\s*:",
        r"\d{1,3}(\.\d{3})*",
        r"^Srm-[^;]+; c\. subst\. -?[\d.]+ \S+$",
    ],
)
def test_usual_template_patterns_are_accepted(pattern):
    check_pattern(pattern, "prueba")


@pytest.mark.parametrize(
    ("data", "mensaje"),
    [
        (_valid_data(extra_key=1), "claves desconocidas"),
        (_valid_data(id="../fuera"), "«id»"),
        (_valid_data(id="Lab"), "«id»"),
        (_valid_data(signature={}), "firma"),
        (_valid_data(priority="alta"), "priority"),
        (_valid_data(known_sections="BIOQUIMICA"), "lista de textos"),
        (
            _valid_data(line_substitutions=[{"pattern": "(a)b", "replacement": r"\g<2>"}]),
            "grupo 2",
        ),
        (
            _valid_data(line_substitutions=[{"pattern": "(?P<x>a)", "replacement": r"\g<y>"}]),
            "«y»",
        ),
        (_valid_data(header_labels=[{"key": "dni", "pattern": "(a+)+"}]), "repetición"),
    ],
)
def test_user_template_validation_errors(data, mensaje):
    with pytest.raises(ProfileValidationError, match=mensaje):
        validate_user_profile_data(data)


def test_id_must_match_file_name():
    with pytest.raises(ProfileValidationError, match="nombre del fichero"):
        validate_user_profile_data(_valid_data(), "otro_nombre")


def test_app_templates_would_also_pass_the_user_validation():
    import tomllib

    from analitix.config import PARSER_PROFILES_DIR

    for path in PARSER_PROFILES_DIR.glob("*.toml"):
        validate_user_profile_data(tomllib.loads(path.read_text(encoding="utf-8")), path.stem)
