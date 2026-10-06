from analitix.gui import _smoking_summary


def test_smoking_summary():
    assert _smoking_summary({}) == ""
    assert _smoking_summary({"smoker_current": 0, "smoker_former": 0}) == "No fumador"
    assert _smoking_summary({"smoker_current": 1}) == "Fumador"
    assert _smoking_summary({"smoker_former": 1, "smoker_former_from": 1998, "smoker_former_to": 2010}) == (
        "Exfumador (1998-2010)"
    )
    assert _smoking_summary({"smoker_former": 1, "smoker_former_period": "de joven"}) == "Exfumador (de joven)"


def test_pdf_pages_split_and_same_orientation():
    from matplotlib.figure import Figure

    from analitix.gui import PDF_ROWS_PER_PAGE, _pages_of, _same_size

    assert _pages_of(list(range(5))) == [(list(range(5)), "")]
    trozos = _pages_of(list(range(PDF_ROWS_PER_PAGE + 3)))
    assert [(len(t), s) for t, s in trozos] == [(PDF_ROWS_PER_PAGE, " (1/2)"), (3, " (2/2)")]
    figuras = _same_size([Figure(figsize=(9, 15)), Figure(figsize=(9, 3))])
    assert tuple(figuras[1].get_size_inches()) == (9, 15)  # misma orientación que la primera


def test_history_window_counts_back_from_last_report():
    from types import SimpleNamespace

    from analitix.gui import AnalitixApp

    serie = [{"fecha": f} for f in ("2012-03-01", "2019-06-01", "2019-06-02 08:30:00", "2024-06-01")]

    def app(full):
        return SimpleNamespace(var_full_history=SimpleNamespace(get=lambda: full))

    assert [s["fecha"][:10] for s in AnalitixApp._windowed(app(False), serie)] == [
        "2019-06-01", "2019-06-02", "2024-06-01"]  # 5 años antes de la última, no de hoy
    assert AnalitixApp._windowed(app(True), serie) == serie
