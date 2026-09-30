from pathlib import Path

import pytest

import analitix.catalog as catalog
from analitix.textutils import normalize_name, normalize_test_name, strip_accents


def test_text_normalization():
    assert strip_accents("Árbol Ñandú") == "Arbol Nandu"
    assert normalize_name("  García, María-José ") == "MARIA JOSE GARCIA"
    assert normalize_test_name("Colesterol HDL (sèrum)!") == "colesterol hdl serum"


def test_catalog_aliases_and_description(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    aliases = tmp_path / "aliases.csv"
    descriptions = tmp_path / "descriptions"
    descriptions.mkdir()
    monkeypatch.setattr(catalog, "CATALOG_PATH", aliases)
    monkeypatch.setattr(catalog, "DESCRIPTIONS_DIR", descriptions)
    catalog.reload_overrides()

    assert catalog.canonical_id_for("Colesterol HDL") == "colesterol_hdl"
    catalog.add_aliases({"colesterol hdl": "hdl_canonical"})
    assert catalog.canonical_id_for("Colesterol HDL") == "hdl_canonical"
    (descriptions / "hdl_canonical.txt").write_text("  HDL description \n", encoding="utf-8")
    assert catalog.get_description("hdl_canonical") == "HDL description"
    assert catalog.get_description("missing") is None


def test_percent_and_absolute_get_separate_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    aliases = tmp_path / "aliases.csv"
    aliases.write_text(
        "alias_normalizado,canonical_id\nlinfocitos,linfocits_total\nlinfocitos pct,limfocits\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(catalog, "CATALOG_PATH", aliases)
    catalog.reload_overrides()
    assert catalog.canonical_id_for("Linfocitos") == "linfocits_total"
    assert catalog.canonical_id_for("Linfocitos %") == "limfocits"
    assert catalog.canonical_id_for("% linfocitos") == "limfocits"
    catalog.reload_overrides()


def test_unit_equivalences():
    from analitix.textutils import is_count_1e9_l, is_count_1e12_l, unit_key
    for unit in ("x10^3/ul", "x10^3_u/mcL", "x10³/mm³", "x10^9/L", "·10³/µl"):
        assert is_count_1e9_l(unit), unit
    for unit in ("x10^6/ul", "x106/mm³", "x10^12/L"):
        assert is_count_1e12_l(unit), unit
    assert not is_count_1e9_l("x10^6/ul") and not is_count_1e12_l("x10^3/ul")
    assert unit_key("µg/dL") == "mcg/dl"


def test_user_aliases_layer_over_bundled_ones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Ejecutable instalado: alias de la app (solo lectura) + los del usuario.
    bundled, user = tmp_path / "bundled.csv", tmp_path / "user.csv"
    bundled.write_text("alias_normalizado,canonical_id\nhierro,ferro_serum\nurea,urea_app\n", encoding="utf-8")
    user.write_text("alias_normalizado,canonical_id\nurea,urea_usuario\n", encoding="utf-8")
    monkeypatch.setattr(catalog, "BUNDLED_CATALOG_PATH", bundled)
    monkeypatch.setattr(catalog, "CATALOG_PATH", user)
    catalog.reload_overrides()
    assert catalog.canonical_id_for("Hierro") == "ferro_serum"
    assert catalog.canonical_id_for("Urea") == "urea_usuario"  # gana el del usuario

    catalog.add_aliases({"glucosa plasma": "glucosa_serum"})
    assert "hierro" not in user.read_text(encoding="utf-8")  # no copia los de la app
    assert "glucosa plasma,glucosa_serum" in user.read_text(encoding="utf-8")
    assert "glucosa" not in bundled.read_text(encoding="utf-8")
