import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_privacy", Path(__file__).resolve().parents[1] / "scripts" / "check_privacy.py"
)
check_privacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_privacy)

# Construidos en tiempo de ejecución para que este mismo fichero no
# dispare la comprobación (son los ejemplos de DNI/NIE de manual).
DNI_VALIDO = "1234" + "5678Z"
NIE_VALIDO = "X123" + "4567L"


def test_dni_valido():
    assert check_privacy.dni_valido("", "12345678", "Z")
    assert check_privacy.dni_valido("X", "1234567", "L")
    assert not check_privacy.dni_valido("", "12345678", "A")  # letra incorrecta
    assert not check_privacy.dni_valido("", "00000000", "T")  # sintético permitido


def test_revisar(tmp_path):
    (tmp_path / "ok.py").write_text('dni = "00000000T"  # sintético\n', encoding="utf-8")
    (tmp_path / "mal.md").write_text(f"DNI: {DNI_VALIDO}\nNIE: {NIE_VALIDO}\n", encoding="utf-8")
    (tmp_path / "informe.pdf").write_bytes(b"%PDF")
    rutas = ["ok.py", "mal.md", "informe.pdf", "src/analitix/data/test_aliases.csv"]
    problemas = check_privacy.revisar(rutas, tmp_path)
    assert problemas == [
        "mal.md:1: posible DNI/NIE real",
        "mal.md:2: posible DNI/NIE real",
        "informe.pdf: tipo de fichero no permitido en el repositorio",
    ]
