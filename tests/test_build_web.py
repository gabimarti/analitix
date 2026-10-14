import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "build_web", Path(__file__).resolve().parents[1] / "scripts" / "build_web.py"
)
build_web = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_web)


def _release(tag, draft=False, exe=True):
    assets = [{"name": "SHA256SUMS.txt", "size": 100, "browser_download_url": f"https://x/{tag}/sums"}]
    if exe:
        assets.append(
            {
                "name": f"Analitix-Setup-{tag[1:]}.exe",
                "size": 41_500_000,
                "browser_download_url": f"https://x/{tag}/setup.exe",
            }
        )
    return {"tag_name": tag, "draft": draft, "published_at": "2026-10-09T10:00:00Z", "assets": assets}


def test_latest_release_skips_drafts_and_releases_without_installer():
    releases = [_release("v0.14.0", draft=True), _release("v0.13.1", exe=False), _release("v0.13.0")]
    valores = build_web.latest_release(releases)
    assert valores == {
        "VERSION": "0.13.0",
        "DOWNLOAD_URL": "https://x/v0.13.0/setup.exe",
        "SIZE_MB": "42",
        "RELEASE_DATE": "2026-10-09",
        "SHA256_URL": "https://x/v0.13.0/sums",
    }


def test_without_releases_the_button_goes_to_the_releases_page():
    valores = build_web.latest_release([])
    assert valores["DOWNLOAD_URL"] == build_web.RELEASES_PAGE


def test_build_fills_every_language_page_and_copies_images(tmp_path):
    out = tmp_path / "site"
    build_web.build(out, [_release("v0.13.0")])
    paginas = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.html"))
    assert paginas == ["ca/index.html", "es/index.html", "index.html"]
    for pagina in ("es/index.html", "ca/index.html"):
        html = (out / pagina).read_text(encoding="utf-8")
        assert "{{" not in html  # ningún marcador sin sustituir
        assert "https://x/v0.13.0/setup.exe" in html and "0.13.0" in html
    for nombre in (*build_web.IMAGES, "logo.png"):
        assert (out / "assets" / "img" / nombre).is_file()
