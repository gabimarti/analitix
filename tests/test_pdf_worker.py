"""Lectura de PDF en el proceso aparte vigilado (`pdf_worker`).

PDF sintéticos generados en el momento (matplotlib) con texto inventado:
nunca informes reales."""

import sys
import time
from pathlib import Path

import pytest
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure

from analitix import config, ingest, pdf_worker
from analitix.parser_profiles import reload_profiles
from analitix.pdf_worker import (
    PdfRejectedError,
    PdfTimeoutError,
    PdfWorker,
    PdfWorkerError,
    Progress,
    parse_report_isolated,
)


def _pdf(path: Path, *pages: list[str]) -> Path:
    with PdfPages(path) as pdf:
        for lines in pages:
            fig = Figure()
            for i, line in enumerate(lines):
                fig.text(0.05, 0.9 - i * 0.06, line)
            pdf.savefig(fig)
    return path


HUGTIP_PAGE = [
    "Nom: GARCIA LOPEZ, MARIA Peticio: 123456789",
    "Centre: HUGTIP",
    "Pla-Glucosa; c. subst. 85 mg/dL 70 - 100",
]


def test_parses_a_pdf_in_the_child_process(tmp_path):
    progresos: list[Progress] = []
    parsed = parse_report_isolated(_pdf(tmp_path / "a.pdf", HUGTIP_PAGE), progresos.append, True)
    assert parsed["format_id"] == "hugtip"
    assert [r["raw_name"] for r in parsed["results"]] == ["Pla-Glucosa; c. subst."]
    assert any(t["kind"] == "resultado" for t in parsed["trace"])
    assert progresos and progresos[-1].page == 1 and progresos[-1].pages == 1


def test_logs_the_time_of_each_pdf_without_its_name(tmp_path, caplog):
    pdf = _pdf(tmp_path / "PACIENTE_FICTICIO.pdf", HUGTIP_PAGE)
    with caplog.at_level("INFO", logger="analitix"):
        parse_report_isolated(pdf)
    assert "PDF leído en" in caplog.text and "1 páginas" in caplog.text
    assert "PACIENTE_FICTICIO" not in caplog.text and "GARCIA" not in caplog.text


def test_child_uses_the_same_user_templates_as_the_parent(tmp_path):
    folder = config.USER_PARSER_PROFILES_DIR
    folder.mkdir(parents=True)
    (folder / "lab_ficticio.toml").write_text(
        'id = "lab_ficticio"\nname = "Laboratorio Ficticio"\n'
        '[signature]\nrequires_any = ["LABORATORIO FICTICIO XYZ"]\n',
        encoding="utf-8",
    )
    reload_profiles()
    pdf = _pdf(tmp_path / "b.pdf", ["LABORATORIO FICTICIO XYZ"])
    assert parse_report_isolated(pdf)["format_id"] == "lab_ficticio"


def test_damaged_pdf_is_an_error_and_the_worker_keeps_working(tmp_path):
    roto = tmp_path / "roto.pdf"
    roto.write_bytes(b"%PDF-1.4\nesto no es un PDF de verdad")
    bueno = _pdf(tmp_path / "bueno.pdf", HUGTIP_PAGE)
    with PdfWorker() as worker:
        with pytest.raises(PdfWorkerError):
            worker.parse(roto)
        assert worker.parse(bueno)["format_id"] == "hugtip"


def test_too_large_pdf_is_rejected_before_opening(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_worker, "MAX_PDF_BYTES", 10)
    with pytest.raises(PdfRejectedError, match="MB"):
        parse_report_isolated(_pdf(tmp_path / "c.pdf", HUGTIP_PAGE))


def test_pdf_with_too_many_pages_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_worker, "MAX_PDF_PAGES", 1)
    pdf = _pdf(tmp_path / "d.pdf", HUGTIP_PAGE, HUGTIP_PAGE)
    with pytest.raises(PdfRejectedError, match="páginas"):
        parse_report_isolated(pdf)


def test_a_child_that_stops_answering_is_abandoned(tmp_path):
    progresos: list[Progress] = []
    worker = PdfWorker(stall_timeout=1, _target=pdf_worker._hang_for_tests)
    inicio = time.monotonic()
    with worker, pytest.raises(PdfTimeoutError):
        worker.parse(_pdf(tmp_path / "e.pdf", HUGTIP_PAGE), progresos.append)
    assert time.monotonic() - inicio < 30
    assert progresos and progresos[-1].page is None
    assert worker._proc is None  # el hijo colgado se ha parado


def test_if_the_child_never_starts_the_next_pdfs_fail_at_once(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_worker, "STARTUP_TIMEOUT_S", 2)
    pdf = _pdf(tmp_path / "i.pdf", HUGTIP_PAGE)
    with PdfWorker(_target=pdf_worker._never_ready_for_tests) as worker:
        with pytest.raises(PdfWorkerError, match="no arranca"):
            worker.parse(pdf)
        inicio = time.monotonic()
        with pytest.raises(PdfWorkerError, match="no arranca"):
            worker.parse(pdf)
        assert time.monotonic() - inicio < 1


def test_one_child_serves_several_pdfs(tmp_path):
    pdfs = [_pdf(tmp_path / f"{n}.pdf", HUGTIP_PAGE) for n in "fg"]
    with PdfWorker() as worker:
        worker.parse(pdfs[0])
        pid = worker._proc.pid
        if sys.platform == "win32":
            assert worker._job, "el hijo debe ir en un Job Object con memoria máxima"
        worker.parse(pdfs[1])
        assert worker._proc.pid == pid


def test_ingest_parse_report_goes_through_the_worker(tmp_path):
    parsed = ingest.parse_report(_pdf(tmp_path / "h.pdf", HUGTIP_PAGE))
    assert parsed["format_id"] == "hugtip"
    assert ingest._worker is None  # sin importación abierta, el hijo se cierra


def test_progress_text():
    assert Progress(2, 5, 3.2, 0).text() == "página 2 de 5 · 3 s"
    assert Progress(None, None, 14, 12).text() == "14 s · sin respuesta desde hace 12 s"
