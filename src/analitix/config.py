# ---------------------------------------------------------------------------
# Script: config.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-10-09
# ---------------------------------------------------------------------------
import shutil
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent

# Ejecutable empaquetado (PyInstaller, instalador de Windows): la carpeta del
# programa no es escribible, así que los datos del usuario van fuera de ella.
FROZEN = bool(getattr(sys, "frozen", False))


def _documents_dir() -> Path:
    """Carpeta Documentos real del usuario: puede estar redirigida (p. ej. a
    OneDrive), así que en Windows se le pregunta al sistema en vez de
    suponer `~/Documents`."""
    if sys.platform == "win32":
        import ctypes

        buf = ctypes.create_unicode_buffer(260)
        # CSIDL_PERSONAL = 5 (Documentos), SHGFP_TYPE_CURRENT = 0.
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
            return Path(buf.value)
    return Path.home() / "Documents"


def _installed_home_dir() -> Path:
    """Carpeta "Analitix" que el usuario eligió al instalar (el instalador la
    guarda en `HKCU\\Software\\Analitix`, valor `HomeDir`); si no consta,
    `Documentos\\Analitix`."""
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Analitix") as key:
                value, _type = winreg.QueryValueEx(key, "HomeDir")
            if value:
                return Path(value)
        except OSError:
            pass
    return _documents_dir() / "Analitix"


def set_installed_home_dir(home: Path) -> None:
    """Apunta la carpeta "Analitix" del ejecutable instalado (la misma clave
    que escribe el instalador); la app la usa a partir del siguiente
    arranque."""
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Analitix") as key:
        winreg.SetValueEx(key, "HomeDir", 0, winreg.REG_SZ, str(home))


def copy_home(old: Path, new: Path) -> None:
    """Copia `data/` e `informes_analiticas/` de la carpeta "Analitix" `old`
    a `new` para cambiar de ubicación. Nunca borra el origen ni sobrescribe
    ficheros que ya existan en el destino: el usuario borra la carpeta
    antigua cuando compruebe que todo está bien."""

    def _copy_if_missing(src: str, dst: str) -> None:
        if not Path(dst).exists():
            shutil.copy2(src, dst)

    for sub in ("data", "informes_analiticas"):
        (new / sub).mkdir(parents=True, exist_ok=True)
        if (old / sub).is_dir():
            shutil.copytree(old / sub, new / sub, dirs_exist_ok=True, copy_function=_copy_if_missing)


if FROZEN:
    # Datos y PDF juntos en la carpeta "Analitix" elegida al instalar (puede
    # ser cualquier carpeta del usuario, también una sincronizada con la
    # nube: es su decisión). La carpeta de PDF se puede cambiar además desde
    # la app ("Cambiar carpeta...").
    PROJECT_ROOT = _installed_home_dir()
    DATA_DIR = PROJECT_ROOT / "data"
    REPORTS_DIR = PROJECT_ROOT / "informes_analiticas"
else:
    PROJECT_ROOT = PACKAGE_DIR.parents[1]
    REPORTS_DIR = PROJECT_ROOT / "informes_analiticas"
    DATA_DIR = PROJECT_ROOT / "data"
# Una base de datos cifrada por paciente, cada una con su contraseña, en
# `PATIENTS_DIR`; la lista de bases de datos y la configuración de la
# aplicación son JSON sin cifrar, sin datos sensibles (ver `databases.py`).
# La antigua `DATA_DIR / "analitix.db"` (todos los pacientes en una) ya no se
# usa: los datos se reimportan desde los PDF.
PATIENTS_DIR = DATA_DIR / "pacientes"
DB_LIST_PATH = DATA_DIR / "bases_de_datos.json"
APP_CONFIG_PATH = DATA_DIR / "config.json"

# Alias de pruebas en dos capas: los que trae la aplicación
# (`BUNDLED_CATALOG_PATH`, versionados) y los que el usuario añade al fusionar
# pruebas (`CATALOG_PATH`, ver `catalog.add_aliases`). Desde el repositorio son
# el mismo fichero; en el ejecutable, el del usuario va en su carpeta de datos
# para que una versión nueva de la app traiga sus alias sin pisar los suyos.
BUNDLED_CATALOG_PATH = PACKAGE_DIR / "data" / "test_aliases.csv"
CATALOG_PATH = DATA_DIR / "test_aliases.csv" if FROZEN else BUNDLED_CATALOG_PATH
# Variación biológica para el RCV (`rcv.py`), también en dos capas: la que trae
# la aplicación (versionada, valores citados) y una opcional del usuario en su
# carpeta de datos que la completa o corrige (p. ej. el CVA de su laboratorio).
BUNDLED_BV_PATH = PACKAGE_DIR / "data" / "biological_variation.csv"
BV_PATH = DATA_DIR / "biological_variation.csv"
DESCRIPTIONS_DIR = PACKAGE_DIR / "data" / "descripciones"
PARSER_PROFILES_DIR = PACKAGE_DIR / "data" / "parser_profiles"

RES_DIR = PACKAGE_DIR / "res"
ICON_PATH = RES_DIR / "analitix_icon.png"
LOGO_PATH = RES_DIR / "analitix_logo.png"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PATIENTS_DIR.mkdir(parents=True, exist_ok=True)
if FROZEN:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
