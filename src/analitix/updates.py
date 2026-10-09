# ---------------------------------------------------------------------------
# Script: updates.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-30
# Última actualización: 2026-10-09
# ---------------------------------------------------------------------------
"""Comprobación de versiones nuevas en GitHub Releases.

Es la ÚNICA conexión a internet de la aplicación: una petición GET anónima a
la API pública de GitHub que solo lee el número de la última versión
publicada. No envía ningún dato del usuario ni de la base de datos.
"""
from __future__ import annotations

import json
import urllib.request

from analitix import __version__

REPO_URL = "https://github.com/gabimarti/analitix"
# Página personal del autor ("Acerca de" y portada de los informes PDF).
AUTHOR_URL = "https://gabimarti.github.io/"
RELEASES_URL = f"{REPO_URL}/releases"
# `/releases/latest` no sirve: excluye las *pre-release*, y todas las 0.x lo
# son (ver release.yml). La lista viene ordenada de más nueva a más antigua.
API_URL = "https://api.github.com/repos/gabimarti/analitix/releases?per_page=1"
TIMEOUT_S = 5


def _parse(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.lstrip("vV").split("."))


def is_newer(latest: str, current: str = __version__) -> bool:
    """True si `latest` ("v0.10.0" o "0.10.0") es posterior a `current`."""
    return _parse(latest) > _parse(current)


def fetch_latest_release() -> tuple[str, str] | None:
    """(versión, URL de su página) de la última Release, o None si no hay.

    Lanza `OSError`/`ValueError` si no se puede consultar (sin conexión,
    repositorio privado → 404, respuesta inesperada).
    """
    req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        releases = json.load(resp)
    if not releases:
        return None
    return releases[0]["tag_name"].lstrip("vV"), releases[0]["html_url"]
