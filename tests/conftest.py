from pathlib import Path

import pytest

import analitix.catalog as catalog
from analitix.db import connect


@pytest.fixture(autouse=True)
def empty_alias_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Cada test con un CSV de alias vacío y propio: los tests no deben
    depender del `data/test_aliases.csv` real (lo edita el usuario) ni
    escribir en él (`merge_canonical_ids` -> `add_aliases`)."""
    aliases = tmp_path / "test_aliases.csv"
    aliases.write_text("alias_normalizado,canonical_id\n", encoding="utf-8")
    monkeypatch.setattr(catalog, "CATALOG_PATH", aliases)
    monkeypatch.setattr(catalog, "BUNDLED_CATALOG_PATH", aliases)
    catalog.reload_overrides()
    yield
    monkeypatch.undo()
    catalog.reload_overrides()


@pytest.fixture
def db(tmp_path: Path):
    connection = connect("test-password", tmp_path / "analitix.db")
    try:
        yield connection
    finally:
        connection.close()
