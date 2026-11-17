from analitix.gui import _smoking_summary


def test_smoking_summary():
    assert _smoking_summary({}) == ""
    assert _smoking_summary({"smoker_current": 0, "smoker_former": 0}) == "No fumador"
    assert _smoking_summary({"smoker_current": 1}) == "Fumador"
    assert _smoking_summary(
        {"smoker_former": 1, "smoker_former_from": 1998, "smoker_former_to": 2010}
    ) == ("Exfumador (1998-2010)")
    assert (
        _smoking_summary({"smoker_former": 1, "smoker_former_period": "de joven"})
        == "Exfumador (de joven)"
    )


def test_pdf_pages_split_and_same_orientation():
    from matplotlib.figure import Figure

    from analitix.gui import PDF_ROWS_PER_PAGE, _pages_of, _same_size

    assert _pages_of(list(range(5))) == [(list(range(5)), "")]
    trozos = _pages_of(list(range(PDF_ROWS_PER_PAGE + 3)))
    assert [(len(t), s) for t, s in trozos] == [(PDF_ROWS_PER_PAGE, " (1/2)"), (3, " (2/2)")]
    figuras = _same_size([Figure(figsize=(9, 15)), Figure(figsize=(9, 3))])
    assert tuple(figuras[1].get_size_inches()) == (9, 15)  # misma orientación que la primera


def test_heatmap_pages_are_balanced():
    from analitix.gui import HEATMAP_PAGE_ROWS, _heatmap_pages

    assert _heatmap_pages([]) == []
    assert _heatmap_pages(list(range(HEATMAP_PAGE_ROWS))) == [(list(range(HEATMAP_PAGE_ROWS)), "")]
    paginas = _heatmap_pages(list(range(50)))  # 50 filas: 3 páginas parecidas
    assert [(len(t), s) for t, s in paginas] == [(17, " (1/3)"), (17, " (2/3)"), (16, " (3/3)")]
    assert sum((t for t, _ in paginas), []) == list(range(50))  # sin perder ni repetir filas


def test_balanced_pages_of_splits_evenly():
    from analitix.gui import _balanced_pages_of

    assert _balanced_pages_of([]) == []
    # 41 filas con max 25: 2 páginas equilibradas (21 y 20), nunca 25 y 16 descompensadas
    paginas = _balanced_pages_of(list(range(41)), 25)
    assert [(len(t), s) for t, s in paginas] == [(21, " (1/2)"), (20, " (2/2)")]
    assert sum((t for t, _ in paginas), []) == list(range(41))
    # Si cabe en 1 página, va todo en una sin sufijo
    assert _balanced_pages_of(list(range(25)), 25) == [(list(range(25)), "")]


def test_history_window_counts_back_from_last_report():
    from types import SimpleNamespace

    from analitix.gui import AnalitixApp

    serie = [
        {"fecha": f}
        for f in (
            "2012-03-01",
            "2019-06-01",
            "2019-06-02 08:30:00",
            "2021-06-01",
            "2024-06-01",
        )
    ]

    def app(years=5, full=False):
        return SimpleNamespace(
            chart_years=years,
            var_full_history=SimpleNamespace(get=lambda: full),
        )

    # 5 años antes de la última analítica (2024 -> >= 2019)
    assert [s["fecha"][:10] for s in AnalitixApp._windowed(app(5), serie)] == [
        "2019-06-01",
        "2019-06-02",
        "2021-06-01",
        "2024-06-01",
    ]
    # 3 años antes de la última analítica (2024 -> >= 2021)
    assert [s["fecha"][:10] for s in AnalitixApp._windowed(app(3), serie)] == [
        "2021-06-01",
        "2024-06-01",
    ]
    # Todo el histórico (years = 0)
    assert AnalitixApp._windowed(app(0), serie) == serie
    # Todo el histórico con flag full_history
    assert AnalitixApp._windowed(app(5, full=True), serie) == serie


def test_format_points_count_dual_range():
    from types import SimpleNamespace

    from analitix.gui import AnalitixApp

    def app(years=3):
        fake = SimpleNamespace(chart_years=years)
        fake._windowed = lambda s: AnalitixApp._windowed(fake, s)
        return fake

    serie = [
        {"fecha": "2018-01-01", "value_num": 1.0},
        {"fecha": "2020-01-01", "value_num": 2.0},
        {"fecha": "2024-01-01", "value_num": 3.0},
    ]

    # Con chart_years=3, solo entra la de 2024 (1 de 3)
    assert AnalitixApp._format_points_count(app(3), serie) == "n=1 / 3 hist."
    # Con chart_years=0 (todo el histórico), muestra solo n=3
    assert AnalitixApp._format_points_count(app(0), serie) == "n=3"
    # Sin recorte (todos dentro de los últimos 10 años)
    assert AnalitixApp._format_points_count(app(10), serie) == "n=3"
