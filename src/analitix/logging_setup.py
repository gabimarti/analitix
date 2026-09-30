# ---------------------------------------------------------------------------
# Script: logging_setup.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-08
# Última actualización: 2026-09-08
# ---------------------------------------------------------------------------
"""Configuración del registro (log) de la aplicación a fichero.

El fichero de log (`data/analitix.log`) no contiene datos de pacientes ni
resultados: solo nombres de fichero PDF, mensajes de estado y trazas de
error, pensado para poder diagnosticar problemas a posteriori sin exponer
información médica.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from analitix.config import DATA_DIR

LOG_PATH = DATA_DIR / "analitix.log"

_configured = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configura el logger raíz "analitix"; no hace nada si ya se llamó antes."""
    global _configured
    if _configured:
        return
    _configured = True

    logger = logging.getLogger("analitix")
    logger.setLevel(level)

    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)

    logger.info("=== Analitix iniciado ===")
