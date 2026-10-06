import math

import pytest

from analitix import rcv
from analitix.config import BUNDLED_BV_PATH
from analitix.rcv import VariacionBiologica, classify_change, rcv_limits, read_table


def _bv(cvi=None, mujer=None, hombre=None, cva=None):
    return VariacionBiologica("Prueba", cvi, mujer, hombre, cva, "Fuente", "", "", "")


def test_rcv_limits_matches_hand_calculation():
    # CVI 10 %, CVA 2 % (< 0,5·CVI → se usa 5 %):
    # σ = √(ln(1.0025) + ln(1.01)); límites = exp(±1.96·√2·σ) − 1.
    sigma = math.sqrt(math.log(1.0025) + math.log(1.01))
    k = 1.96 * math.sqrt(2) * sigma
    bajada, subida = rcv_limits(10, 2)
    assert bajada == pytest.approx((math.exp(-k) - 1) * 100)
    assert subida == pytest.approx((math.exp(k) - 1) * 100)
    assert subida == pytest.approx(36.2, abs=0.1)
    assert bajada == pytest.approx(-26.6, abs=0.1)


def test_rcv_uses_study_cva_when_larger_than_half_cvi():
    assert rcv_limits(4, 3) != rcv_limits(4, 0)
    assert rcv_limits(4, 1) == rcv_limits(4, 0)  # 1 < 0,5·4 → manda 0,5·CVI


def test_small_cv_close_to_classic_formula():
    # Con CV pequeños el log-normal ≈ clásico √2·Z·√(CVA²+CVI²).
    clasico = math.sqrt(2) * 1.96 * math.sqrt(0.53**2 + 0.40**2)
    assert rcv_limits(0.53, 0.40)[1] == pytest.approx(clasico, rel=0.01)


def test_classify_change_states():
    table = {"x": _bv(cvi=10, cva=2)}
    assert classify_change("x", 100, 110, table=table)["estado"] == "esperable"
    assert classify_change("x", 100, 140, table=table)["estado"] == "real"
    assert classify_change("x", 100, 70, table=table)["estado"] == "real"
    assert classify_change("x", 100, 140, lab_previous="A", lab="B", table=table)["estado"] == "otro_lab"
    assert classify_change("x", 100, 140, lab_previous=None, lab="B", table=table)["estado"] == "otro_lab"
    assert classify_change("y", 100, 140, table=table) is None  # sin variación biológica
    assert classify_change("x", 0, 140, table=table) is None  # modelo logarítmico


def test_sex_specific_cvi():
    bv = _bv(mujer=20, hombre=10)
    assert bv.cvi_para("Mujer") == 20
    assert bv.cvi_para("Hombre") == 10
    assert bv.cvi_para(None) == 20  # sin sexo: el mayor (más prudente)


def test_bundled_table_is_valid_and_cited():
    table = read_table(BUNDLED_BV_PATH)
    assert len(table) > 40
    for canonical_id, bv in table.items():
        assert bv.cvi_pct or (bv.cvi_mujer_pct and bv.cvi_hombre_pct), canonical_id
        assert bv.fuente and bv.doi.startswith("10."), canonical_id
    # Excluidos a propósito (ver docs/referencias_medicas/referencias_rcv.md).
    for excluido in ("vitamina_d_25_oh_serum", "rdw_cv", "hb_glicosilada_hba1c_sang", "ferritina"):
        assert excluido not in table


def test_user_layer_overrides_bundled(tmp_path, monkeypatch):
    user = tmp_path / "biological_variation.csv"
    user.write_text("# comentario\ncanonical_id,analito,cvi_pct,cva_pct,fuente\nglucosa,Glucosa,9.9,,Mi lab\n",
                    encoding="utf-8")
    monkeypatch.setattr(rcv, "BV_PATH", user)
    rcv.load_table.cache_clear()
    try:
        assert rcv.load_table()["glucosa"].cvi_pct == 9.9
        assert "sodi" in rcv.load_table()  # el resto sigue viniendo de la aplicación
    finally:
        rcv.load_table.cache_clear()


def _punto(fecha, valor, flag="normal", lab="A"):
    return dict(fecha=fecha, value_num=valor, flag_calc=flag, ref_low=50.0, ref_high=150.0, lab=lab)


def test_personal_range_coskun_formula():
    from analitix.rcv import personal_range

    table = {"x": _bv(cvi=10, cva=2)}  # CVA efectivo = máx(2, 0,5·10) = 5
    serie = [_punto("2024-01-01", 100.0), _punto("2024-02-01", 104.0), _punto("2024-03-01", 96.0),
             _punto("2024-04-01", 130.0)]  # el último no entra en el cálculo
    pr = personal_range("x", serie, table=table)
    semiancho = 1.96 * math.sqrt(4 / 3) * math.sqrt(10**2 + 5**2)  # n = 3
    assert pr["punto"] == pytest.approx(100.0)
    assert pr["bajo"] == pytest.approx(100 * (1 - semiancho / 100))
    assert pr["alto"] == pytest.approx(100 * (1 + semiancho / 100))
    assert pr["n"] == 3 and pr["labs"] == 1


def test_personal_range_uses_only_in_range_values():
    from analitix.rcv import personal_range

    table = {"x": _bv(cvi=10, cva=2)}
    serie = [_punto("2024-01-01", 100.0), _punto("2024-02-01", 300.0, flag="alto"),
             _punto("2024-03-01", 104.0), _punto("2024-04-01", 96.0), _punto("2024-05-01", 99.0, lab="B")]
    pr = personal_range("x", serie, table=table)
    assert pr["n"] == 3 and pr["punto"] == pytest.approx(100.0)  # el valor alto no "normaliza" el rango
    # Con menos de 3 valores dentro de rango (sin contar el último) no hay rango personal.
    assert personal_range("x", serie[:3], table=table) is None
    assert personal_range("y", serie, table=table) is None  # sin variación biológica
