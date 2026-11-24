"""Explicación línea a línea del motor (`trace`) y convención decimal de la
plantilla (`decimal_separator`). Datos inventados: nunca datos reales."""

from dataclasses import replace

import pytest

from analitix.parser_profiles import load_profiles
from analitix.pdf_parser import (
    TRACE_DISCARDED,
    TRACE_HEADER,
    TRACE_RESULT,
    TRACE_UNCLASSIFIED,
    _parse_lines,
    _to_float,
    decimal_convention,
    parse_result_line,
)

HUGTIP_LINES = [
    "Nom: GARCIA LOPEZ, MARIA Petició: 123456789",
    "Centre: HUGTIP Recepció: 14 de nov. 20246:58:57",
    "SDF",
    "San-Hemoglobina, c. massa 10.4 g/dL 12.0 - 15.0 *",
    "Pla-Glucosa; c. subst. 85 mg/dL 70 - 100",
    "4.7 mmol/L 3.9 - 5.6",
    "",
    "Texto narrativo sin nada que reconocer",
]


def _profile(profile_id: str):
    return next(p for p in load_profiles() if p.id == profile_id)


def test_trace_does_not_change_the_result():
    sin = _parse_lines(HUGTIP_LINES, _profile("hugtip"))
    trace: list = []
    con = _parse_lines(HUGTIP_LINES, _profile("hugtip"), trace)
    assert con == sin


def test_trace_explains_every_non_empty_line():
    trace: list = []
    _parse_lines(HUGTIP_LINES, _profile("hugtip"), trace)
    assert [t["idx"] for t in trace] == [0, 1, 2, 3, 4, 5, 7]
    kinds = {t["idx"]: (t["kind"], t["detail"]) for t in trace}
    assert kinds[0][0] == TRACE_HEADER and "full_name" in kinds[0][1]
    assert kinds[3] == (TRACE_RESULT, "San-Hemoglobina, c. massa")
    assert kinds[4] == (TRACE_RESULT, "Pla-Glucosa; c. subst.")
    # La línea de unidad secundaria no tiene nombre: se descarta, y se dice.
    assert kinds[5][0] == TRACE_DISCARDED
    assert kinds[7][0] == TRACE_UNCLASSIFIED
    # La línea se muestra ya sin la marca "*" que recorta la plantilla.
    assert trace[3]["line"].endswith("12.0 - 15.0")


@pytest.mark.parametrize(
    ("separator", "text", "expected"),
    [
        ("auto", "7.349", 7349.0),
        (",", "7.349", 7349.0),
        (".", "7.349", 7.349),
        (".", "1.000", 1.0),
        (",", "2.534,5", 2534.5),
        (".", "2,5", 2.5),
    ],
)
def test_decimal_convention_in_to_float(separator, text, expected):
    with decimal_convention(separator):
        assert _to_float(text) == expected


def test_fixed_convention_skips_the_range_heuristic():
    # Con "auto", un "7.349" con rango "7.32 - 7.43" se lee como 7,349; si la
    # plantilla dice que el "." es de millares, no hay nada que adivinar.
    assert parse_result_line("pH 7.349 7.32 - 7.43")["value_num"] == 7.349
    with decimal_convention(","):
        assert parse_result_line("Leucocitos 7.349 4.000 - 10.000")["value_num"] == 7349.0
    with decimal_convention("."):
        result = parse_result_line("pH 7.349 7.32 - 7.43")
    assert result["value_num"] == 7.349 and result["ref_low"] == 7.32


def test_unknown_convention_falls_back_to_auto():
    with decimal_convention("x"):
        assert _to_float("1.000") == 1000.0


def test_profile_convention_applies_while_parsing_and_is_reset():
    profile = replace(_profile("hugtip"), decimal_separator=".")
    lines = ["Centre: HUGTIP", "Pla-Plaquetes; c. núm. 1.250 x10^9/L 1.000 - 2.000"]
    resultado = _parse_lines(lines, profile)["results"][0]
    assert resultado["value_num"] == 1.25
    assert resultado["ref_high"] == 2.0
    assert _to_float("1.000") == 1000.0  # fuera del parseo, vuelve a "auto"
