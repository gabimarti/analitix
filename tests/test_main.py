from analitix.main import _self_test


def test_self_test_passes_from_source():
    # La misma comprobación que se ejecuta sobre el .exe instalado.
    assert _self_test() == 0
