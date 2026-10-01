# ---------------------------------------------------------------------------
# Script: repository.py
# Autor: Gabriel Marti
# Contacto: https://github.com/gabimarti
# Fecha de creación: 2026-09-07
# Última actualización: 2026-09-29
# ---------------------------------------------------------------------------
"""Operaciones CRUD sobre la base de datos."""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Optional

from sqlcipher3 import dbapi2 as sqlcipher

from analitix.catalog import add_aliases, canonical_id_for
from analitix.db import now_iso
from analitix.pdf_parser import compute_flag
from analitix.textutils import normalize_name, normalize_test_name, strip_accents

# Fecha efectiva de un resultado: la de recepción/toma de la muestra si el
# PDF la trae; si no, la de petición (en todas las plantillas conocidas es
# el mismo día de la extracción); la de validación solo como último
# recurso, porque puede ser días posterior. Nunca la fecha de emisión/
# descarga del informe, que no se guarda.
_FECHA_SQL = "COALESCE(r.sample_date, rep.request_date, rep.validation_date)"

# Filtro de laboratorios de gráficos y paneles: los informes cuyo `lab` está
# en la tabla temporal `excluded_labs` (ver `db.connect`) no cuentan en
# `get_series` (y por tanto `get_merged_series`, todos los paneles, el mapa
# de calor y el PDF), `get_latest_report_summary` ni `list_canonical_tests`.
# Los informes sin laboratorio conocido (importados antes de guardarlo) se
# filtran con la clave "". Las exportaciones Excel/CSV y el Explorador BD no
# se filtran: son los datos en bruto.
_LAB_FILTER_SQL = "COALESCE(rep.lab, '') NOT IN (SELECT lab FROM temp.excluded_labs)"


def list_labs(con) -> list[dict[str, Any]]:
    """Laboratorios con informes (`lab`, "" si no consta) y cuántos informes
    tiene cada uno, para el diálogo de laboratorios incluidos."""
    cur = con.execute("SELECT COALESCE(lab, '') AS lab, COUNT(*) AS n FROM reports GROUP BY 1 ORDER BY 1")
    return [{"lab": lab, "n": n} for lab, n in cur.fetchall()]


def get_excluded_labs(con) -> set[str]:
    return {row[0] for row in con.execute("SELECT lab FROM temp.excluded_labs")}


def set_excluded_labs(con, labs) -> None:
    """Sustituye los laboratorios excluidos de gráficos y paneles. Se
    confirma (`commit`) en el acto: un `rollback` posterior de otra
    operación (p. ej. un PDF con error al importar) no debe deshacer el
    filtro en silencio."""
    con.execute("DELETE FROM temp.excluded_labs")
    con.executemany("INSERT OR IGNORE INTO temp.excluded_labs (lab) VALUES (?)", [(lab or "",) for lab in labs])
    con.commit()


def _add_alt_value(alt_str: Optional[str], value: Optional[str]) -> Optional[str]:
    """Añade `value` a una lista de valores alternativos guardada como texto
    separado por comas (p. ej. `nhc_alt`), sin duplicarlo si ya está. Usado
    para no perder un NHC antiguo cuando aparece uno nuevo distinto — el
    NHC cambia de numeración entre plantillas del laboratorio a lo largo de
    los años (ver `get_or_create_patient`), así que el antiguo sigue siendo
    un dato real y puede hacer falta consultarlo."""
    if not value:
        return alt_str
    values = [v.strip() for v in alt_str.split(",") if v.strip()] if alt_str else []
    if value not in values:
        values.append(value)
    return ", ".join(values)


def _remove_alt_value(alt_str: Optional[str], value: Optional[str]) -> Optional[str]:
    """Quita `value` de una lista separada por comas como `nhc_alt`."""
    if not alt_str or not value:
        return alt_str
    values = [v.strip() for v in alt_str.split(",") if v.strip() and v.strip() != value]
    return ", ".join(values) or None


def get_or_create_patient(
    con,
    full_name: Optional[str],
    birth_date: Optional[str],
    dni: Optional[str],
    nhc: Optional[str],
    fallback_name: Optional[str] = None,
    sex: Optional[str] = None,
    cip: Optional[str] = None,
    previous_patient_id: Optional[int] = None,
) -> tuple[int, str]:
    """Empareja pacientes por nombre normalizado + fecha de nacimiento; si el
    PDF no trae un nombre reconocible (plantilla no soportada) pero sí un
    DNI o NHC que coincide con un paciente ya existente, se usa ese en vez de
    crear uno nuevo — así un informe sin nombre reconocido no genera un
    paciente "fantasma" con el nombre del fichero cuando en realidad sabemos
    de quién es por otro identificador. Solo si nada coincide se crea un
    paciente nuevo, usando `fallback_name` (el nombre del fichero) como
    nombre provisional.

    El NHC/Núm. d'història clínica cambia de numeración entre las distintas
    plantillas del laboratorio a lo largo de los años, así que no sirve como
    clave única estable para informes con nombre reconocido; solo se usa como
    identificador de emparejamiento cuando el nombre no se pudo extraer.

    Devuelve `(patient_id, matched_by)`, con `matched_by` en
    `"name" | "dni" | "cip" | "nhc" | "previous" | "new"`, para que quien llama pueda distinguir
    un emparejamiento por identificador (que sigue mereciendo revisión, ya
    que la plantilla no se reconoció) de uno normal por nombre.
    """
    cur = con.cursor()
    key = normalize_name(full_name) if full_name else None
    row = None
    matched_by: Optional[str] = None
    if key:
        row = cur.execute(
            "SELECT id FROM patients WHERE name_key = ? AND IFNULL(birth_date,'') = IFNULL(?, '')",
            (key, birth_date),
        ).fetchone()
        if row:
            matched_by = "name"
    if not row and dni:
        row = cur.execute("SELECT id FROM patients WHERE dni = ?", (dni,)).fetchone()
        if row:
            matched_by = "dni"
    # El CIP (tarjeta sanitaria autonómica) es personal y estable entre
    # plantillas, a diferencia del NHC — se prueba antes que este.
    if not row and cip:
        row = cur.execute("SELECT id FROM patients WHERE cip = ?", (cip,)).fetchone()
        if row:
            matched_by = "cip"
    if not row and nhc:
        row = cur.execute("SELECT id FROM patients WHERE nhc = ?", (nhc,)).fetchone()
        if row:
            matched_by = "nhc"
    if not row and previous_patient_id is not None:
        # Reimportación de un PDF que ya estaba asignado a este paciente
        # (p. ej. tras fusionarlo a mano, `merge_patients`): si nada del PDF
        # identifica a otra persona, se respeta esa asignación en vez de
        # recrear el paciente duplicado — antes, cada reimportación de un
        # fichero en "revisar" deshacía la fusión.
        row = cur.execute("SELECT id FROM patients WHERE id = ?", (previous_patient_id,)).fetchone()
        if row:
            matched_by = "previous"
    if row:
        patient_id = row[0]
        # full_name/dni/nhc se actualizan con el valor más reciente: el NHC
        # cambia de numeración entre plantillas y el más nuevo es el vigente.
        # Si el NHC nuevo es distinto del que tenía, el antiguo no se pierde:
        # pasa a `nhc_alt` en vez de sobrescribirse sin más. El nombre solo
        # se refresca si el emparejamiento ha sido por nombre: por DNI/CIP/
        # NHC o asignación previa se conserva el que ya tenía (p. ej. el que
        # el usuario eligió al fusionar), en vez del de cada PDF reimportado.
        if matched_by != "name":
            full_name = None
        current_nhc = cur.execute("SELECT nhc, nhc_alt FROM patients WHERE id = ?", (patient_id,)).fetchone()
        current_nhc_value, current_nhc_alt = current_nhc
        if nhc and current_nhc_value and nhc != current_nhc_value:
            new_nhc_alt = _add_alt_value(current_nhc_alt, current_nhc_value)
        else:
            new_nhc_alt = current_nhc_alt
        # El NHC que pasa a ser el principal no debe seguir listado también
        # como secundario (pasaba al volver a un NHC ya visto antes).
        new_nhc_alt = _remove_alt_value(new_nhc_alt, nhc)
        cur.execute(
            "UPDATE patients SET full_name = COALESCE(?, full_name), birth_date = COALESCE(birth_date, ?), "
            "dni = COALESCE(?, dni), nhc = COALESCE(?, nhc), nhc_alt = ?, sex = COALESCE(?, sex), "
            "cip = COALESCE(?, cip) WHERE id = ?",
            (full_name, birth_date, dni, nhc, new_nhc_alt, sex, cip, patient_id),
        )
        return patient_id, matched_by
    name_for_new = full_name or fallback_name or "Desconocido"
    cur.execute(
        "INSERT INTO patients (full_name, name_key, birth_date, dni, nhc, sex, cip) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name_for_new, normalize_name(name_for_new), birth_date, dni, nhc, sex, cip),
    )
    return cur.lastrowid, "new"


def upsert_report(
    con,
    patient_id: int,
    report_number: Optional[str],
    request_date: Optional[str],
    validation_date: Optional[str],
    source_file: str,
    notes: Optional[str] = None,
    file_md5: Optional[str] = None,
    assistance_number: Optional[str] = None,
    lab: Optional[str] = None,
) -> int:
    """`source_file` es solo el nombre del PDF (nunca la ruta); `file_md5`
    identifica su contenido aunque se renombre. `report_number` es el
    identificador del informe en el laboratorio (Nº Petició, Nº Laboratorio,
    Nº Anàlisi... según la plantilla) y `assistance_number` el Nº
    Assistència del Consorci Sanitari del Maresme."""
    cur = con.cursor()
    row = cur.execute(
        "SELECT id FROM reports WHERE patient_id = ? AND IFNULL(report_number,'') = IFNULL(?, '')",
        (patient_id, report_number),
    ).fetchone()
    if row:
        report_id = row[0]
        # El PDF de origen puede haberse renombrado/movido desde la última
        # importación (mismo informe, mismo `report_number` extraído del
        # propio PDF); se refresca para que apunte al nombre de fichero
        # vigente en vez de quedarse con uno que ya no existe.
        cur.execute(
            "UPDATE reports SET source_file = ?, file_md5 = COALESCE(?, file_md5), "
            "assistance_number = COALESCE(?, assistance_number), lab = COALESCE(?, lab) WHERE id = ?",
            (source_file, file_md5, assistance_number, lab, report_id),
        )
        # `notes` solo se toca si se pasa explícitamente: la importación de
        # PDF nunca lo pasa, así que reimportar un informe no borra una nota
        # ya puesta a mano.
        if notes is not None:
            cur.execute("UPDATE reports SET notes = ? WHERE id = ?", (notes, report_id))
        return report_id
    cur.execute(
        "INSERT INTO reports (patient_id, report_number, request_date, validation_date, source_file, notes, "
        "file_md5, assistance_number, lab) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (patient_id, report_number, request_date, validation_date, source_file, notes, file_md5, assistance_number,
         lab),
    )
    return cur.lastrowid


def clear_report_results(con, report_id: int) -> None:
    """Borra los resultados ya guardados de un informe antes de volver a
    insertarlos. `clear_previous_import` limpia por nombre de fichero, pero
    no detecta el caso de un PDF renombrado que `upsert_report` empareja con
    un informe ya existente por `report_number` — sin este borrado previo,
    reimportarlo duplicaría cada resultado. Inofensivo si el informe es
    nuevo (no borra nada)."""
    con.execute("DELETE FROM results WHERE report_id = ?", (report_id,))


def prune_missing_processed_files(con, existing_filenames: set[str]) -> int:
    """Borra de `processed_files` las marcas de importación de ficheros que
    ya no están en la carpeta de informes (renombrados o eliminados). No
    toca los informes/resultados ya guardados (siguen accesibles bajo el
    nombre de fichero vigente vía `upsert_report`), solo el registro de qué
    PDF se procesó con qué hash y cuándo, que deja de ser relevante para un
    fichero que ya no existe con ese nombre. Devuelve cuántas se han
    borrado."""
    cur = con.execute("SELECT filename FROM processed_files")
    stale = [row[0] for row in cur.fetchall() if row[0] not in existing_filenames]
    if stale:
        placeholders = ",".join("?" * len(stale))
        con.execute(f"DELETE FROM processed_files WHERE filename IN ({placeholders})", stale)  # noqa: S608
        con.commit()
    return len(stale)


def insert_result(con, report_id: int, result: dict[str, Any]) -> None:
    con.execute(
        "INSERT INTO results (report_id, section, test_group, loinc_code, raw_name, canonical_id, "
        "value_raw, value_num, unit, ref_low, ref_high, ref_text, flag_pdf, flag_calc, sample_date) "
        "VALUES (:report_id, :section, :test_group, :loinc_code, :raw_name, :canonical_id, "
        ":value_raw, :value_num, :unit, :ref_low, :ref_high, :ref_text, :flag_pdf, :flag_calc, :sample_date)",
        {"report_id": report_id, **result},
    )


def create_manual_report(
    con, patient_id: int, fecha: str, entries: list[dict[str, Any]], notes: Optional[str] = None
) -> int:
    """Crea un informe "de entrada manual" (sin PDF de origen), para cuando
    un PDF no se puede parsear y hay que registrar la analítica de todos
    modos. `entries` es una lista de dicts con `raw_name`/`value_num`/`unit`/
    `ref_low`/`ref_high` (estos tres últimos ya pueden ser `None`). `notes`
    es un texto libre opcional (a qué corresponde la analítica, por qué se
    ha puesto a mano) guardado en `reports.notes`.

    `report_number` se genera con la marca de tiempo actual (no con la fecha
    de la analítica) para poder registrar varias entradas manuales del mismo
    paciente sin chocar con `UNIQUE(patient_id, report_number)` aunque
    compartan fecha.
    """
    report_id = upsert_report(
        con,
        patient_id=patient_id,
        report_number=f"MANUAL-{now_iso()}",
        request_date=fecha,
        validation_date=fecha,
        source_file="(entrada manual)",
        notes=notes,
        lab="Entrada manual",
    )
    for entry in entries:
        canonical_id = canonical_id_for(entry["raw_name"])
        flag_calc = compute_flag(entry["value_num"], entry.get("ref_low"), entry.get("ref_high"))
        insert_result(
            con,
            report_id,
            {
                "section": None,
                "test_group": None,
                "loinc_code": None,
                "raw_name": entry["raw_name"],
                "canonical_id": canonical_id,
                "value_raw": str(entry["value_num"]),
                "value_num": entry["value_num"],
                "unit": entry.get("unit"),
                "ref_low": entry.get("ref_low"),
                "ref_high": entry.get("ref_high"),
                "ref_text": None,
                "flag_pdf": None,
                "flag_calc": flag_calc,
                "sample_date": None,
            },
        )
    con.commit()
    return report_id


def list_known_test_names(con) -> list[str]:
    """Nombres de prueba ya vistos (para el autocompletado del formulario de
    entrada manual)."""
    cur = con.execute("SELECT DISTINCT raw_name FROM results ORDER BY raw_name")
    return [row[0] for row in cur.fetchall()]


def already_processed(con, filename: str, file_hash: str) -> bool:
    """Un fichero solo se salta si no ha cambiado Y la vez anterior salió
    bien (`status="ok"`); uno marcado "review"/"error" se reintenta siempre,
    para que una mejora del parser lo recoja sin que el usuario tenga que
    hacer nada especial."""
    row = con.execute(
        "SELECT file_hash, status FROM processed_files WHERE filename = ?", (filename,)
    ).fetchone()
    return row is not None and row[0] == file_hash and row[1] == "ok"


def clear_previous_import(con, filename: str) -> Optional[int]:
    """Borra el informe y los resultados de una importación anterior de este
    fichero (si los hay), para poder reimportarlo desde cero sin duplicar
    filas ni dejar datos huérfanos de un intento previo fallido.

    Devuelve el paciente al que estaba asignado ese informe si sigue
    existiendo (tiene otros informes), para que la reimportación pueda
    respetar esa asignación (`get_or_create_patient(previous_patient_id=...)`)."""
    row = con.execute(
        "SELECT report_id FROM processed_files WHERE filename = ?", (filename,)
    ).fetchone()
    if row and row[0] is not None:
        report_id = row[0]
        patient_row = con.execute("SELECT patient_id FROM reports WHERE id = ?", (report_id,)).fetchone()
        con.execute("DELETE FROM results WHERE report_id = ?", (report_id,))
        con.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        if patient_row:
            # Si el paciente asociado a ese informe (p.ej. uno "de repuesto"
            # creado a partir del nombre del fichero porque no se reconoció
            # el nombre real) se queda sin ningún informe, se elimina: era
            # un paciente fantasma del intento anterior, no una persona real.
            remaining = con.execute(
                "SELECT COUNT(*) FROM reports WHERE patient_id = ?", (patient_row[0],)
            ).fetchone()[0]
            if remaining == 0:
                con.execute("DELETE FROM patients WHERE id = ?", (patient_row[0],))
                return None
            return patient_row[0]
    return None


def record_processed_file(
    con,
    filename: str,
    file_hash: str,
    status: str,
    report_id: Optional[int] = None,
    error_message: Optional[str] = None,
) -> None:
    con.execute(
        "INSERT INTO processed_files (filename, file_hash, processed_at, status, report_id, error_message) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(filename) DO UPDATE SET file_hash=excluded.file_hash, processed_at=excluded.processed_at, "
        "status=excluded.status, report_id=excluded.report_id, error_message=excluded.error_message",
        (filename, file_hash, now_iso(), status, report_id, error_message),
    )


def list_patient_reports(con, patient_id: int) -> list[dict[str, Any]]:
    """Informes de un paciente para su ficha (gui.py): fichero, firma MD5,
    fecha de la analítica (la misma regla que `_FECHA_SQL`: recepción de la
    muestra, si no petición, si no validación) y nº de parámetros. Del más
    reciente al más antiguo."""
    cur = con.execute(
        "SELECT rep.id, rep.source_file, rep.file_md5, rep.report_number, rep.lab, "
        "COALESCE(MIN(r.sample_date), rep.request_date, rep.validation_date) AS fecha, "
        "COUNT(r.id) AS num_results "
        "FROM reports rep LEFT JOIN results r ON r.report_id = rep.id "
        "WHERE rep.patient_id = ? GROUP BY rep.id ORDER BY fecha DESC",
        (patient_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def list_patients(con) -> list[dict[str, Any]]:
    # `num_reports` ayuda a detectar en la propia pestaña Pacientes un
    # paciente "fantasma"/duplicado: alguien con muy pocos informes junto a
    # otro con muchos, misma fecha de nacimiento, suele ser la misma persona
    # separada en dos filas (ver `merge_patients`).
    cur = con.execute(
        "SELECT p.*, COUNT(r.id) AS num_reports "
        "FROM patients p LEFT JOIN reports r ON r.patient_id = p.id "
        "GROUP BY p.id ORDER BY p.full_name"
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# Campos editables a mano desde la ficha del paciente (gui.py). Lista
# blanca: son los únicos nombres de columna que `update_patient` interpola.
EDITABLE_PATIENT_FIELDS = (
    "full_name", "birth_date", "sex", "dni", "cip", "nhc", "nhc_alt",
    "smoker_current", "smoker_former", "smoker_former_from", "smoker_former_to",
    "smoker_former_period",
)
SEX_OPTIONS = ("Hombre", "Mujer")


def update_patient(con, patient_id: int, fields: dict[str, Any]) -> None:
    """Edición manual de la ficha del paciente, para completar lo que la
    importación no pudo detectar. Valida antes de escribir y lanza
    `ValueError` con un mensaje para el usuario si algo no es válido.

    Una reimportación posterior solo sustituye nombre/DNI/NHC/sexo/CIP si el
    PDF trae un valor (ver `get_or_create_patient`); la fecha de nacimiento
    y el tabaquismo nunca los toca."""
    unknown = set(fields) - set(EDITABLE_PATIENT_FIELDS)
    if unknown:
        raise ValueError(f"Campos no editables: {sorted(unknown)}")
    clean = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in fields.items()}
    if "full_name" in clean and not clean["full_name"]:
        raise ValueError("El nombre no puede quedar vacío.")
    if clean.get("birth_date"):
        try:
            dt.date.fromisoformat(clean["birth_date"])
        except ValueError:
            raise ValueError("Fecha de nacimiento no válida (formato AAAA-MM-DD).") from None
    if clean.get("sex") and clean["sex"] not in SEX_OPTIONS:
        raise ValueError("Sexo no válido.")
    for key in ("smoker_current", "smoker_former"):
        if clean.get(key) not in (None, 0, 1):
            raise ValueError("Fumador: valor no válido.")
    this_year = dt.date.today().year
    for key in ("smoker_former_from", "smoker_former_to"):
        value = clean.get(key)
        if value is None:
            continue
        if not re.fullmatch(r"\d{4}", str(value)) or not 1900 <= int(value) <= this_year:
            raise ValueError(f"Año no válido: {value} (1900-{this_year}).")
        clean[key] = int(value)
    if clean.get("smoker_former_from") and clean.get("smoker_former_to") and (
        clean["smoker_former_from"] > clean["smoker_former_to"]
    ):
        raise ValueError("El año «desde» no puede ser posterior al año «hasta».")
    if clean.get("smoker_former") != 1 and "smoker_former" in clean:
        # Sin "fumador anterior: sí", el periodo no tiene sentido.
        clean.update(smoker_former_from=None, smoker_former_to=None, smoker_former_period=None)
    if "full_name" in clean:
        clean["name_key"] = normalize_name(clean["full_name"])
    if not clean:
        return
    assignments = ", ".join(f"{k} = ?" for k in clean)  # claves de la lista blanca
    try:
        con.execute(
            f"UPDATE patients SET {assignments} WHERE id = ?",  # noqa: S608
            (*clean.values(), patient_id),
        )
    except sqlcipher.IntegrityError:
        # UNIQUE(name_key, birth_date): ya hay otro paciente igual. El UPDATE
        # fallido no deja nada a medias; sin rollback, para no descartar
        # cambios pendientes de quien llama.
        raise ValueError(
            "Ya existe otro paciente con ese nombre y fecha de nacimiento; "
            "si es la misma persona, usa «Fusionar seleccionados»."
        ) from None
    con.commit()


def get_patient_birth_date(con, patient_id: int) -> Optional[str]:
    """Fecha de nacimiento de un paciente (`AAAA-MM-DD`), o `None` si no se
    conoce — usada por `hepatic_risk.py` para calcular la edad del paciente
    en la fecha de cada informe (FIB-4)."""
    row = con.execute("SELECT birth_date FROM patients WHERE id = ?", (patient_id,)).fetchone()
    return row[0] if row else None


def get_patient_sex(con, patient_id: int) -> Optional[str]:
    """Sexo del paciente (uno de `SEX_OPTIONS`), o `None` si no se conoce —
    usado por `rcv.py` para los parámetros con variación biológica distinta
    por sexo."""
    row = con.execute("SELECT sex FROM patients WHERE id = ?", (patient_id,)).fetchone()
    return row[0] if row else None


def merge_patients(con, source_ids: list[int], target_id: int) -> int:
    """Funde uno o más pacientes (`source_ids`) en `target_id` — para
    cuando un mismo paciente ha quedado partido en dos filas porque un PDF
    trae el nombre abreviado (sin algún nombre intermedio) y, además, ni el
    DNI ni el NHC coincidían con los del paciente ya existente (el NHC
    cambia de numeración entre plantillas del laboratorio, ver
    `get_or_create_patient`). Reasigna los informes del/de los origen(es) al
    destino, rellena en el destino el DNI/NHC/fecha de nacimiento que
    pudiera faltarle con los del origen (`full_name` no se toca: el
    "correcto" ya lo elige quien llama, pasándolo como destino), y borra
    los pacientes origen.

    Si origen y destino tienen un informe con el mismo `report_number` (un
    duplicado real, no solo el mismo paciente con historiales distintos),
    se descarta el del origen en vez de arrastrar un choque con la
    restricción `UNIQUE(patient_id, report_number)`.

    Si origen y destino tienen un NHC distinto (típico: uno viene de una
    plantilla del laboratorio con otra numeración), el del origen **no se
    pierde**: se guarda en `nhc_alt` del destino en vez de descartarse.

    Devuelve el nº de informes reasignados (no cuenta los descartados por
    duplicado).
    """
    source_ids = [sid for sid in source_ids if sid != target_id]
    if not source_ids:
        return 0
    cur = con.cursor()
    moved = 0
    for source_id in source_ids:
        target_row = cur.execute(
            "SELECT dni, nhc, nhc_alt FROM patients WHERE id = ?", (target_id,)
        ).fetchone()
        source_row = cur.execute("SELECT dni, nhc FROM patients WHERE id = ?", (source_id,)).fetchone()
        target_dni, target_nhc, target_nhc_alt = target_row
        source_dni, source_nhc = source_row

        new_nhc_alt = target_nhc_alt
        if source_nhc and source_nhc != target_nhc:
            # Si el destino ni siquiera tenía NHC, el del origen pasa a ser
            # el principal (no tiene sentido relegar a "alternativo" el
            # único NHC real que hay); si el destino ya tenía uno distinto,
            # el del origen se guarda como alternativo para no perderlo.
            if target_nhc is None:
                new_nhc_alt = target_nhc_alt
            else:
                new_nhc_alt = _add_alt_value(target_nhc_alt, source_nhc)

        cur.execute(
            "UPDATE patients SET dni = ?, nhc = ?, nhc_alt = ?, "
            "birth_date = COALESCE(birth_date, (SELECT birth_date FROM patients WHERE id = ?)), "
            "sex = COALESCE(sex, (SELECT sex FROM patients WHERE id = ?)), "
            "cip = COALESCE(cip, (SELECT cip FROM patients WHERE id = ?)), "
            "smoker_current = COALESCE(smoker_current, (SELECT smoker_current FROM patients WHERE id = ?)), "
            "smoker_former = COALESCE(smoker_former, (SELECT smoker_former FROM patients WHERE id = ?)), "
            "smoker_former_from = COALESCE(smoker_former_from, (SELECT smoker_former_from FROM patients WHERE id = ?)), "
            "smoker_former_to = COALESCE(smoker_former_to, (SELECT smoker_former_to FROM patients WHERE id = ?)), "
            "smoker_former_period = COALESCE(smoker_former_period, "
            "(SELECT smoker_former_period FROM patients WHERE id = ?)) "
            "WHERE id = ?",
            (
                target_dni or source_dni,
                target_nhc if target_nhc is not None else source_nhc,
                new_nhc_alt,
                *([source_id] * 8),
                target_id,
            ),
        )
        reports = cur.execute(
            "SELECT id, report_number FROM reports WHERE patient_id = ?", (source_id,)
        ).fetchall()
        for report_id, report_number in reports:
            clash = cur.execute(
                "SELECT id FROM reports WHERE patient_id = ? AND IFNULL(report_number,'') = IFNULL(?, '')",
                (target_id, report_number),
            ).fetchone()
            if clash:
                cur.execute("DELETE FROM results WHERE report_id = ?", (report_id,))
                cur.execute("DELETE FROM processed_files WHERE report_id = ?", (report_id,))
                cur.execute("DELETE FROM reports WHERE id = ?", (report_id,))
            else:
                cur.execute("UPDATE reports SET patient_id = ? WHERE id = ?", (target_id, report_id))
                moved += 1
        cur.execute("DELETE FROM patients WHERE id = ?", (source_id,))
    con.commit()
    return moved


def list_canonical_tests(con, patient_id: Optional[int] = None) -> list[dict[str, Any]]:
    q = (
        "SELECT r.canonical_id, MAX(r.raw_name) AS raw_name, MAX(r.unit) AS unit, "
        "MAX(CASE WHEN r.flag_calc IN ('alto', 'bajo') THEN 1 ELSE 0 END) AS out_of_range, "
        "COUNT(*) AS num_points "
        f"FROM results r JOIN reports rep ON rep.id = r.report_id WHERE r.value_num IS NOT NULL AND {_LAB_FILTER_SQL}"
    )
    params: tuple = ()
    if patient_id is not None:
        q += " AND rep.patient_id = ?"
        params = (patient_id,)
    q += " GROUP BY r.canonical_id"
    cur = con.execute(q, params)
    cols = [d[0] for d in cur.description]
    tests = [dict(zip(cols, row)) for row in cur.fetchall()]
    # Nombre a mostrar = el más frecuente de cada prueba (como en "Normalizar
    # pruebas"), no el alfabéticamente mayor: con varios laboratorios,
    # MAX(raw_name) elegía p. ej. "San-Hemoglobina, c. massa" frente a
    # "Hemoglobina" solo por orden alfabético.
    q_names = (
        "SELECT r.canonical_id, r.raw_name, COUNT(*) FROM results r JOIN reports rep ON rep.id = r.report_id "
        f"WHERE r.value_num IS NOT NULL AND {_LAB_FILTER_SQL}"
        + (" AND rep.patient_id = ?" if patient_id is not None else "")
        + " GROUP BY r.canonical_id, r.raw_name"
    )
    best: dict[str, tuple[int, str]] = {}
    for cid, raw_name, n in con.execute(q_names, params):
        if cid not in best or (n, raw_name) > best[cid]:
            best[cid] = (n, raw_name)
    for t in tests:
        if t["canonical_id"] in best:
            t["raw_name"] = best[t["canonical_id"]][1]
    return sorted(tests, key=lambda t: strip_accents(t["raw_name"] or "").casefold())


def list_canonical_groups(con) -> list[dict[str, Any]]:
    """Para la pestaña "Normalizar pruebas": un grupo por `canonical_id` con
    todas las variantes de `raw_name` vistas y cuántos resultados tiene cada
    una (de todos los pacientes — el catálogo de nombres es del laboratorio,
    no de una persona), para detectar variantes que en realidad son la misma
    prueba (p. ej. el laboratorio abrevia o renombra ligeramente un nombre
    entre informes)."""
    # `labs`: de qué laboratorio(s) viene cada id — dos nombres distintos del
    # mismo laboratorio no siempre son la misma prueba (ver `merge_check`).
    # `variants`: cada nombre con el laboratorio que lo usa, `(raw_name, lab,
    # n)`, para ver qué nombre viene de qué laboratorio (`lab` es None en
    # informes importados antes de guardar el laboratorio).
    cur = con.execute(
        "SELECT r.canonical_id, r.raw_name, rep.lab, COUNT(*) AS n FROM results r "
        "JOIN reports rep ON rep.id = r.report_id "
        "WHERE r.canonical_id IS NOT NULL GROUP BY r.canonical_id, r.raw_name, rep.lab"
    )
    groups: dict[str, dict[str, Any]] = {}
    for canonical_id, raw_name, lab, n in cur.fetchall():
        g = groups.setdefault(
            canonical_id,
            {"canonical_id": canonical_id, "raw_names": {}, "variants": [], "num_results": 0, "labs": set()},
        )
        g["raw_names"][raw_name] = g["raw_names"].get(raw_name, 0) + n
        g["variants"].append((raw_name, lab, n))
        g["num_results"] += n
        g["labs"].add(lab)
    for g in groups.values():
        g["raw_names"] = sorted(g["raw_names"].items(), key=lambda t: -t[1])
        g["variants"].sort(key=lambda t: (t[1] or "", -t[2]))
        g["labs"] = sorted(lab for lab in g["labs"] if lab)
    return sorted(groups.values(), key=lambda g: -g["num_results"])


class MergeBlockedError(ValueError):
    """Fusión rechazada por `merge_check`: los ids son pruebas distintas."""


def merge_check(con, canonical_ids: list[str]) -> tuple[list[str], list[str]]:
    """Comprueba si fusionar `canonical_ids` mezclaría pruebas distintas.
    Devuelve `(bloqueos, avisos)`, textos para mostrar al usuario.

    - Bloqueo: dos de los ids aparecen en un MISMO informe. El laboratorio
      las midió a la vez, así que no son la misma prueba (p. ej. glucosa en
      sangre y en orina). Excepción: ambos con el mismo LOINC, que es el
      mismo dato repetido en el informe.
    - Aviso: códigos LOINC distintos, o unidades de dimensión distinta.

    Dos nombres del mismo laboratorio que nunca coinciden en un informe no
    bloquean nada: suelen ser la misma prueba renombrada entre versiones de
    plantilla ("Ferritina" / "Ferritina sèrum")."""
    from analitix.alias_audit import unit_relation

    ids = sorted(set(canonical_ids))
    if len(ids) < 2:
        return [], []
    placeholders = ",".join("?" * len(ids))
    loinc: dict[str, set[str]] = {cid: set() for cid in ids}
    units: dict[str, set[str]] = {cid: set() for cid in ids}
    for cid, code, unit in con.execute(
        f"SELECT DISTINCT canonical_id, loinc_code, unit FROM results WHERE canonical_id IN ({placeholders})",  # noqa: S608
        ids,
    ).fetchall():
        if code:
            loinc[cid].add(code)
        if unit:
            units[cid].add(unit)
    blocked, warnings = [], []
    for a, b, n_reports in con.execute(
        "SELECT a.canonical_id, b.canonical_id, COUNT(DISTINCT a.report_id) FROM results a "
        "JOIN results b ON b.report_id = a.report_id AND a.canonical_id < b.canonical_id "
        f"WHERE a.canonical_id IN ({placeholders}) AND b.canonical_id IN ({placeholders}) "  # noqa: S608
        "GROUP BY a.canonical_id, b.canonical_id",
        (*ids, *ids),
    ).fetchall():
        if loinc[a] and loinc[a] == loinc[b]:
            continue
        blocked.append(f"«{a}» y «{b}» aparecen juntas en {n_reports} informe(s): son pruebas distintas.")
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if loinc[a] and loinc[b] and not loinc[a] & loinc[b]:
                warnings.append(
                    f"«{a}» y «{b}» tienen códigos LOINC distintos "
                    f"({', '.join(sorted(loinc[a]))} / {', '.join(sorted(loinc[b]))})."
                )
            if units[a] and units[b] and unit_relation(units[a], units[b]) in ("convertible", "incompatible"):
                warnings.append(
                    f"«{a}» y «{b}» usan unidades distintas "
                    f"({', '.join(sorted(units[a]))} / {', '.join(sorted(units[b]))})."
                )
    return blocked, warnings


def merge_canonical_ids(con, source_ids: list[str], target_id: str) -> int:
    """Funde uno o más `canonical_id` (variantes que en realidad son la misma
    prueba) en `target_id`: actualiza ya mismo los resultados guardados y
    registra un alias permanente (`catalog.add_aliases`) para cada variante
    de nombre involucrada, así las próximas importaciones también las
    reconocen como la misma prueba sin tener que repetir la fusión.

    Devuelve el nº de filas de `results` actualizadas. Lanza
    `MergeBlockedError` si `merge_check` la bloquea.
    """
    source_ids = [sid for sid in source_ids if sid != target_id]
    if not source_ids:
        return 0
    blocked, _warnings = merge_check(con, [*source_ids, target_id])
    if blocked:
        raise MergeBlockedError(" ".join(blocked))
    placeholders = ",".join("?" * len(source_ids))
    raw_names = [
        row[0]
        for row in con.execute(
            f"SELECT DISTINCT raw_name FROM results WHERE canonical_id IN ({placeholders})",  # noqa: S608
            source_ids,
        ).fetchall()
    ]
    cur = con.execute(
        f"UPDATE results SET canonical_id = ? WHERE canonical_id IN ({placeholders})",  # noqa: S608
        (target_id, *source_ids),
    )
    updated = cur.rowcount
    con.commit()
    add_aliases({normalize_test_name(name): target_id for name in raw_names})
    return updated


def get_series(con, canonical_id: str, patient_id: int) -> list[dict[str, Any]]:
    # Un punto sin ninguna fecha (ni de muestra, ni de validación, ni de
    # petición) no se puede situar en el eje X del gráfico; se excluye aquí
    # en vez de dejar que llegue a `charts.py` con `fecha=None`, que antes
    # hacía fallar `_parse_fecha`. En la
    # práctica no debería descartar nada: `pdf_parser.py` ya reconoce la
    # fecha de petición/recepción de todas las plantillas soportadas.
    cur = con.execute(
        f"SELECT {_FECHA_SQL} AS fecha, "
        "r.value_num, r.unit, r.ref_low, r.ref_high, r.flag_calc, r.raw_name, rep.lab "
        "FROM results r JOIN reports rep ON rep.id = r.report_id "
        "WHERE r.canonical_id = ? AND rep.patient_id = ? AND r.value_num IS NOT NULL "
        f"AND {_FECHA_SQL} IS NOT NULL AND {_LAB_FILTER_SQL} "
        "ORDER BY fecha",
        (canonical_id, patient_id),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_merged_series(con, canonical_ids: tuple[str, ...], patient_id: int) -> dict[str, dict[str, Any]]:
    """Fusiona la serie de varios `canonical_id` que en realidad son el mismo
    parámetro clínico (distintas plantillas del laboratorio lo nombran de
    forma algo distinta, ver `lipid_risk.TOTAL_IDS` como precedente) en un
    único dict `fecha -> fila`. Si dos variantes tuvieran valor la misma
    fecha (no debería ocurrir: cada informe usa el nombre de una única
    plantilla), se queda con la primera que encuentra. Usada por
    `lipid_risk.py`, `hepatic_risk.py` y `renal_risk.py`."""
    merged: dict[str, dict[str, Any]] = {}
    for canonical_id in canonical_ids:
        for row in get_series(con, canonical_id, patient_id):
            merged.setdefault(row["fecha"], row)
    return merged


def get_latest_report_summary(con, patient_id: int) -> Optional[dict[str, Any]]:
    """Resultados numéricos del informe más reciente del paciente (para el
    "semáforo"/resumen de la última analítica), cada
    uno con el valor del informe anterior si existe (`valor_anterior`,
    para que `gui.py` pueda marcar cambios bruscos sin recalcular la serie
    entera a mano). El "informe más reciente" es el que tiene la fecha
    efectiva (`_FECHA_SQL`, igual
    que `get_series`) más tardía entre sus propios resultados — no el de
    `report_number` más alto, que no tiene por qué ir en orden cronológico.
    `None` si el paciente no tiene ningún resultado numérico con fecha."""
    row = con.execute(
        f"SELECT rep.id, {_FECHA_SQL} AS fecha "
        "FROM results r JOIN reports rep ON rep.id = r.report_id "
        "WHERE rep.patient_id = ? AND r.value_num IS NOT NULL "
        f"AND {_FECHA_SQL} IS NOT NULL AND {_LAB_FILTER_SQL} "
        "ORDER BY fecha DESC LIMIT 1",
        (patient_id,),
    ).fetchone()
    if row is None:
        return None
    report_id, fecha = row

    cur = con.execute(
        "SELECT canonical_id, raw_name, value_num, unit, ref_low, ref_high, flag_calc "
        "FROM results WHERE report_id = ? AND value_num IS NOT NULL AND canonical_id IS NOT NULL "
        "ORDER BY raw_name",
        (report_id,),
    )
    cols = [d[0] for d in cur.description]
    resultados = [dict(zip(cols, r)) for r in cur.fetchall()]
    for resultado in resultados:
        serie = get_series(con, resultado["canonical_id"], patient_id)
        resultado["valor_anterior"] = serie[-2]["value_num"] if len(serie) >= 2 else None
        # Laboratorio de los dos últimos puntos: el RCV (`rcv.py`) no es
        # válido si cambian de laboratorio.
        resultado["lab"] = serie[-1]["lab"] if serie else None
        resultado["lab_anterior"] = serie[-2]["lab"] if len(serie) >= 2 else None

    return {"fecha": fecha, "resultados": resultados}


def get_all_results(con, patient_id: Optional[int] = None) -> list[dict[str, Any]]:
    q = (
        "SELECT p.full_name AS paciente, "
        f"{_FECHA_SQL} AS fecha, "
        "r.section, r.test_group, r.raw_name, r.canonical_id, r.value_raw, r.value_num, r.unit, "
        "r.ref_low, r.ref_high, r.ref_text, r.flag_calc, rep.source_file "
        "FROM results r JOIN reports rep ON rep.id = r.report_id JOIN patients p ON p.id = rep.patient_id"
    )
    params: tuple = ()
    if patient_id is not None:
        q += " WHERE rep.patient_id = ?"
        params = (patient_id,)
    q += " ORDER BY paciente, fecha, r.section"
    cur = con.execute(q, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_setting(con, key: str, default: Optional[str] = None) -> Optional[str]:
    row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(con, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    con.commit()


def list_files_needing_review(con) -> list[dict[str, Any]]:
    cur = con.execute(
        "SELECT filename, error_message, processed_at FROM processed_files "
        "WHERE status = 'review' ORDER BY processed_at DESC"
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def delete_patient(con, patient_id: int) -> None:
    """Borra un paciente y todos sus informes/resultados/marcas de
    importación asociados (irreversible)."""
    cur = con.execute("SELECT id FROM reports WHERE patient_id = ?", (patient_id,))
    report_ids = [row[0] for row in cur.fetchall()]
    for report_id in report_ids:
        con.execute("DELETE FROM results WHERE report_id = ?", (report_id,))
        con.execute("DELETE FROM processed_files WHERE report_id = ?", (report_id,))
        con.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    con.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    con.commit()


def list_orphan_reports(con, existing_filenames: set[str]) -> list[dict[str, Any]]:
    """Informes candidatos a limpieza manual: sin ningún resultado, o cuyo
    PDF de origen ya no está en la carpeta de informes. Un PDF *renombrado*
    (no borrado) no cae aquí: `upsert_report` ya actualiza `source_file` al
    nombre vigente en la siguiente importación (ver `ingest.py`), así que si
    de verdad aparece con un nombre que no existe es porque el PDF se
    eliminó de la carpeta sin más, no porque se haya movido/renombrado."""
    cur = con.execute(
        "SELECT r.id, r.patient_id, p.full_name, r.report_number, r.source_file, "
        "COALESCE(r.request_date, r.validation_date) AS fecha, COUNT(res.id) AS num_results "
        "FROM reports r JOIN patients p ON p.id = r.patient_id "
        "LEFT JOIN results res ON res.report_id = r.id "
        "GROUP BY r.id ORDER BY p.full_name, fecha"
    )
    cols = [d[0] for d in cur.description]
    orphans = []
    for row in cur.fetchall():
        item = dict(zip(cols, row))
        item["missing_file"] = item["source_file"] not in existing_filenames
        if item["num_results"] == 0 or item["missing_file"]:
            orphans.append(item)
    return orphans


def delete_reports(con, report_ids: list[int]) -> int:
    """Borra informes concretos (con sus resultados y su marca de
    importación) — para limpiar los huérfanos de `list_orphan_reports`. Si
    el paciente al que pertenecían se queda sin ningún informe, también se
    borra (mismo criterio que `clear_previous_import`/`delete_patient`).
    Devuelve cuántos informes se han borrado."""
    if not report_ids:
        return 0
    cur = con.cursor()
    patient_ids: set[int] = set()
    for report_id in report_ids:
        row = cur.execute("SELECT patient_id FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            continue
        patient_ids.add(row[0])
        cur.execute("DELETE FROM results WHERE report_id = ?", (report_id,))
        cur.execute("DELETE FROM processed_files WHERE report_id = ?", (report_id,))
        cur.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    for patient_id in patient_ids:
        remaining = cur.execute(
            "SELECT COUNT(*) FROM reports WHERE patient_id = ?", (patient_id,)
        ).fetchone()[0]
        if remaining == 0:
            cur.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    con.commit()
    return len(report_ids)


def delete_all_data(con) -> None:
    """Vacía por completo pacientes/informes/resultados/marcas de
    importación (irreversible). No toca `settings` (preferencias de la app)."""
    for table in ("results", "processed_files", "reports", "patients"):
        con.execute(f"DELETE FROM {table}")
    con.commit()


def get_stats(con) -> dict[str, Any]:
    def scalar(query: str, params: tuple = ()) -> Any:
        return con.execute(query, params).fetchone()[0]

    return {
        "num_patients": scalar("SELECT COUNT(*) FROM patients"),
        "num_reports": scalar("SELECT COUNT(*) FROM reports"),
        "num_results": scalar("SELECT COUNT(*) FROM results"),
        "num_results_out_of_range": scalar(
            "SELECT COUNT(*) FROM results WHERE flag_calc IN ('alto', 'bajo')"
        ),
        "num_files_ok": scalar("SELECT COUNT(*) FROM processed_files WHERE status = 'ok'"),
        "num_files_review": scalar("SELECT COUNT(*) FROM processed_files WHERE status = 'review'"),
        "num_files_error": scalar("SELECT COUNT(*) FROM processed_files WHERE status = 'error'"),
        "fecha_min": scalar("SELECT MIN(COALESCE(request_date, validation_date)) FROM reports"),
        "fecha_max": scalar("SELECT MAX(COALESCE(validation_date, request_date)) FROM reports"),
    }


# Tablas que se pueden inspeccionar desde la pestaña "Explorador BD" (de
# solo lectura). Se enumeran explícitamente para no interpolar nunca un
# nombre de tabla arbitrario en una sentencia SQL.
EXPLORABLE_TABLES = ("patients", "reports", "results", "processed_files", "settings")


def get_table_rows(con, table: str) -> tuple[list[str], list[tuple]]:
    """Devuelve (columnas, filas) de una tabla de `EXPLORABLE_TABLES`, para
    la pestaña de solo lectura "Explorador BD"."""
    if table not in EXPLORABLE_TABLES:
        raise ValueError(f"Tabla no permitida: {table}")
    cur = con.execute(f"SELECT * FROM {table} ORDER BY rowid")  # noqa: S608 - tabla validada contra la lista blanca
    columns = [d[0] for d in cur.description]
    return columns, cur.fetchall()
