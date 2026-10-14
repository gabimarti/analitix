# ---------------------------------------------------------------------------
# Script: build_web.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-10-14
# ---------------------------------------------------------------------------
"""Construye la web del proyecto (GitHub Pages) en una carpeta de salida.

Copia `web/` (una carpeta por idioma), añade el logo y las capturas del
manual (`docs/images/`, siempre con datos ficticios) y sustituye en las
páginas los marcadores de la última versión publicada:

    {{VERSION}}  {{DOWNLOAD_URL}}  {{SIZE_MB}}  {{RELEASE_DATE}}  {{SHA256_URL}}

Las versiones 0.x se publican como pre-release, así que «la última versión»
de GitHub (`/releases/latest`) no existe: se toma la más reciente que no sea
borrador. Si no se puede consultar GitHub, el botón enlaza a la página de
versiones.

Uso: python scripts/build_web.py <carpeta_salida>   (desde la raíz del repositorio)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

REPO = "gabimarti/analitix"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
ROOT = Path(__file__).resolve().parents[1]
# Capturas del manual que usa la web (datos ficticios) y el logo de la app.
IMAGES = ("resumen_tabla.png", "evolucion.png", "panel_renal.png", "mapa_calor.png")
LOGO = ROOT / "src" / "analitix" / "res" / "analitix_icon.png"


def latest_release(releases: list[dict]) -> dict[str, str]:
    """Marcadores de la versión más reciente publicada (incluidas las
    pre-release), a partir de la respuesta de la API de GitHub; si no hay
    ninguna con instalador, los de la página de versiones."""
    for release in releases:
        if release.get("draft"):
            continue
        exe = next(
            (a for a in release.get("assets", []) if a["name"].lower().endswith(".exe")), None
        )
        if exe is None:
            continue
        sums = next((a for a in release["assets"] if a["name"] == "SHA256SUMS.txt"), None)
        return {
            "VERSION": release["tag_name"].lstrip("v"),
            "DOWNLOAD_URL": exe["browser_download_url"],
            "SIZE_MB": f"{exe['size'] / 1_000_000:.0f}",
            "RELEASE_DATE": (release.get("published_at") or "")[:10],
            "SHA256_URL": sums["browser_download_url"] if sums else RELEASES_PAGE,
        }
    return {
        "VERSION": "",
        "DOWNLOAD_URL": RELEASES_PAGE,
        "SIZE_MB": "",
        "RELEASE_DATE": "",
        "SHA256_URL": RELEASES_PAGE,
    }


def fetch_releases() -> list[dict]:
    """Versiones del repositorio vía la API pública de GitHub (con el token
    del workflow si lo hay, para no depender del límite anónimo)."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases?per_page=10",
        headers={"Accept": "application/vnd.github+json"},
    )
    token = os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def fill(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def build(out: Path, releases: list[dict]) -> dict[str, str]:
    values = latest_release(releases)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "web", out)
    img = out / "assets" / "img"
    img.mkdir(parents=True, exist_ok=True)
    for name in IMAGES:
        shutil.copy2(ROOT / "docs" / "images" / name, img / name)
    shutil.copy2(LOGO, img / "logo.png")
    for page in out.rglob("*.html"):
        page.write_text(fill(page.read_text(encoding="utf-8"), values), encoding="utf-8")
    return values


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    try:
        releases = fetch_releases()
    except OSError as exc:  # sin red o API caída: la web se publica igual
        print(f"Aviso: no se pudo consultar GitHub ({exc}); el botón irá a {RELEASES_PAGE}")
        releases = []
    values = build(Path(sys.argv[1]), releases)
    print(f"Web construida en {sys.argv[1]} — versión {values['VERSION'] or '(sin versión)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
