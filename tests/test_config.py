from analitix.config import copy_home


def test_copy_home_copies_without_touching_the_source_or_overwriting(tmp_path):
    old, new = tmp_path / "old" / "Analitix", tmp_path / "new" / "Analitix"
    (old / "data").mkdir(parents=True)
    (old / "informes_analiticas" / "persona").mkdir(parents=True)
    (old / "data" / "analitix.db").write_bytes(b"db sintetica")
    (old / "informes_analiticas" / "persona" / "informe.pdf").write_bytes(b"pdf sintetico")
    (new / "data").mkdir(parents=True)
    (new / "data" / "test_aliases.csv").write_text("ya existia", encoding="utf-8")
    (old / "data" / "test_aliases.csv").write_text("del origen", encoding="utf-8")

    copy_home(old, new)

    assert (new / "data" / "analitix.db").read_bytes() == b"db sintetica"
    assert (new / "informes_analiticas" / "persona" / "informe.pdf").exists()
    assert (new / "data" / "test_aliases.csv").read_text(encoding="utf-8") == "ya existia"
    assert (old / "data" / "analitix.db").exists()  # el origen no se toca
