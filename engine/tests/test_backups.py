"""Backups of the database: one a night from 03:00, the last seven kept, checked, restorable."""

import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from kura import db
from kura.backups import (
    BackupError,
    Restored,
    ask_to_import,
    ask_to_restore,
    back_up,
    backups,
    due,
    last_restore,
    restore,
    restore_asked,
)
from kura.config import DataPaths
from kura.export import export_data

NIGHT = datetime(2026, 10, 11, 3, 0).astimezone()


def test_a_backup_is_a_checked_copy_of_the_database(paths: DataPaths, conn: sqlite3.Connection):
    with conn:
        conn.execute("INSERT INTO settings (key, value) VALUES ('naming', '\"keep\"')")

    made = back_up(paths, NIGHT)

    assert made.name == "kura 2026-10-11 0300.db"
    copy = sqlite3.connect(paths.root / "backups" / made.name)
    assert copy.execute("SELECT value FROM settings WHERE key = 'naming'").fetchone() == ('"keep"',)
    copy.close()


def test_tonights_backup_is_due_from_three_until_its_made(
    paths: DataPaths, conn: sqlite3.Connection
):
    assert due(paths, NIGHT - timedelta(hours=2)) is True  # last night's isn't there either
    back_up(paths, NIGHT - timedelta(hours=2))
    assert due(paths, NIGHT - timedelta(minutes=1)) is False
    assert due(paths, NIGHT) is True

    back_up(paths, NIGHT + timedelta(minutes=5))

    assert due(paths, NIGHT + timedelta(hours=20)) is False


def test_only_the_last_seven_are_kept(paths: DataPaths, conn: sqlite3.Connection):
    for night in range(9):
        back_up(paths, NIGHT + timedelta(days=night))

    kept = backups(paths)

    assert len(kept) == 7
    assert kept[0].made == (NIGHT + timedelta(days=8)).replace(tzinfo=None)


def test_restoring_puts_that_nights_records_back_and_keeps_todays_aside(
    paths: DataPaths, conn: sqlite3.Connection
):
    with conn:
        conn.execute("INSERT INTO settings (key, value) VALUES ('naming', '\"keep\"')")
    made = back_up(paths, NIGHT)
    with conn:
        conn.execute("UPDATE settings SET value = '\"plex\"' WHERE key = 'naming'")

    restore(paths, made.name, NIGHT + timedelta(hours=10))

    naming = conn.execute("SELECT value FROM settings WHERE key = 'naming'").fetchone()[0]
    assert naming == '"keep"'
    before = [b for b in backups(paths) if b.before_restoring]
    assert [b.name for b in before] == ["kura 2026-10-11 1300 before restoring.db"]


def test_a_backup_that_isnt_there_cant_be_restored(paths: DataPaths, conn: sqlite3.Connection):
    with pytest.raises(BackupError, match="no such backup"):
        restore(paths, "kura 2026-01-01 0300.db", NIGHT)
    with pytest.raises(BackupError, match="no such backup"):
        restore(paths, "..\\kura.db", NIGHT)


def test_a_backup_asked_for_is_restored_at_the_engines_next_start(
    paths: DataPaths, conn: sqlite3.Connection
):
    with conn:
        conn.execute("INSERT INTO settings (key, value) VALUES ('naming', '\"keep\"')")
    made = back_up(paths, NIGHT)
    with conn:
        conn.execute("UPDATE settings SET value = '\"plex\"' WHERE key = 'naming'")

    ask_to_restore(paths, made.name)
    restored = restore_asked(paths, NIGHT + timedelta(hours=10))

    assert restored is True
    naming = conn.execute("SELECT value FROM settings WHERE key = 'naming'").fetchone()[0]
    assert naming == '"keep"'
    at = (NIGHT + timedelta(hours=10)).isoformat(timespec="seconds")
    assert last_restore(conn) == Restored(made.name, at, None)
    assert restore_asked(paths, NIGHT + timedelta(hours=11)) is False  # asked once, done once


def test_a_backup_gone_by_the_next_start_isnt_restored_and_says_why(
    paths: DataPaths, conn: sqlite3.Connection
):
    made = back_up(paths, NIGHT)
    ask_to_restore(paths, made.name)
    (paths.root / "backups" / made.name).unlink()

    assert restore_asked(paths, NIGHT + timedelta(hours=10)) is False

    found = last_restore(conn)
    assert found is not None
    assert (found.name, found.problem) == (made.name, "Kura has no such backup.")


def test_only_a_backup_there_is_can_be_asked_for(paths: DataPaths, conn: sqlite3.Connection):
    with pytest.raises(BackupError, match="no such backup"):
        ask_to_restore(paths, "kura 2026-01-01 0300.db")


def test_the_last_seven_copies_made_before_restoring_are_kept_too(
    paths: DataPaths, conn: sqlite3.Connection
):
    for hour in range(9):
        back_up(paths, NIGHT + timedelta(hours=hour), before_restoring=True)

    kept = backups(paths)

    assert len(kept) == 7
    assert all(backup.before_restoring for backup in kept)


def test_an_export_is_imported_as_the_engine_starts_again(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    elsewhere = DataPaths(tmp_path / "Another PC")
    with closing(db.connect(elsewhere.database)) as other, other:
        db.migrate(other)
        other.execute("INSERT INTO settings (key, value) VALUES ('naming', '\"keep\"')")
    archive = export_data(elsewhere, tmp_path / "Exports", now=NIGHT)
    assert archive is not None

    ask_to_import(paths, archive, NIGHT + timedelta(hours=10))
    assert restore_asked(paths, NIGHT + timedelta(hours=10)) is True

    naming = conn.execute("SELECT value FROM settings WHERE key = 'naming'").fetchone()[0]
    assert naming == '"keep"'
    kept = backups(paths)
    assert [(b.from_export, b.before_restoring) for b in kept] == [(True, False), (False, True)]


def test_a_zip_that_isnt_a_kura_export_isnt_imported(paths: DataPaths, tmp_path: Path):
    archive = tmp_path / "photos.zip"
    with zipfile.ZipFile(archive, "w") as photos:
        photos.writestr("holiday.jpg", b"a photo")

    with pytest.raises(BackupError, match="isn't a Kura export"):
        ask_to_import(paths, archive, NIGHT)


def test_an_export_from_a_newer_kura_waits_for_an_update(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    archive = tmp_path / "Kura export 2030-01-01.zip"
    with zipfile.ZipFile(archive, "w") as newer:
        newer.writestr("manifest.json", json.dumps({"app": "Kura", "schemaVersion": 999}))
        newer.writestr("kura.db", b"")

    with pytest.raises(BackupError, match="newer Kura"):
        ask_to_import(paths, archive, NIGHT)
