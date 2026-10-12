import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from kura import db
from kura.migrations import MIGRATIONS


def test_migrate_brings_a_new_database_to_the_latest_version(tmp_path: Path):
    with closing(db.connect(tmp_path / "kura.db")) as conn:
        assert db.migrate(conn) == len(MIGRATIONS)
        assert db.schema_version(conn) == len(MIGRATIONS)


def test_migrate_is_safe_to_run_again(tmp_path: Path):
    with closing(db.connect(tmp_path / "kura.db")) as conn:
        db.migrate(conn)
        assert db.migrate(conn) == len(MIGRATIONS)


def test_a_database_from_a_newer_kura_is_left_alone(tmp_path: Path):
    with closing(db.connect(tmp_path / "kura.db")) as conn:
        conn.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")

        with pytest.raises(db.NewerDatabaseError):
            db.migrate(conn)

        assert db.schema_version(conn) == len(MIGRATIONS) + 1


def test_a_failing_migration_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    broken = "CREATE TABLE half_done (id INTEGER); THIS IS NOT SQL;"
    monkeypatch.setattr(db, "MIGRATIONS", (*MIGRATIONS, broken))

    with closing(db.connect(tmp_path / "kura.db")) as conn:
        with pytest.raises(sqlite3.OperationalError):
            db.migrate(conn)

        assert db.schema_version(conn) == len(MIGRATIONS)
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master")}
        assert "settings" in tables
        assert "half_done" not in tables


def test_identification_keeps_every_scan_and_file_from_before(tmp_path: Path):
    with closing(db.connect(tmp_path / "kura.db")) as conn:
        conn.executescript("".join(f"BEGIN;{sql}COMMIT;" for sql in MIGRATIONS[:3]))
        conn.execute("PRAGMA user_version = 3")
        conn.execute("INSERT INTO folders (path, added_at) VALUES ('D:/Anime', '2026-10-11')")
        conn.execute(
            "INSERT INTO files (folder_id, path, size, modified, found_at, seen_at)"
            " VALUES (1, 'D:/Anime/Trigun - 01.mkv', 1, 1, 'then', 'then')"
        )
        conn.execute(
            "INSERT INTO scans (started_at, finished_at, state, stage)"
            " VALUES ('2026-10-11T09:00', '2026-10-11T09:05', 'done', 'done')"
        )
        conn.commit()

        db.migrate(conn)

        scan = conn.execute("SELECT * FROM scans").fetchone()
        assert (scan["state"], scan["stage"], scan["note"]) == ("done", "done", None)
        file = conn.execute("SELECT * FROM files").fetchone()
        assert (file["path"], file["matched"], file["pinned"]) == (
            "D:/Anime/Trigun - 01.mkv",
            None,
            0,
        )
        conn.execute(  # the new stages are allowed
            "INSERT INTO scans (started_at, state, stage)"
            " VALUES ('later', 'running', 'identifying')"
        )


def test_files_waiting_for_a_match_are_looked_up_again(tmp_path: Path):
    with closing(db.connect(tmp_path / "kura.db")) as conn:
        conn.executescript("".join(f"BEGIN;{sql}COMMIT;" for sql in MIGRATIONS[:13]))
        conn.execute("PRAGMA user_version = 13")
        conn.execute("INSERT INTO folders (path, added_at) VALUES ('D:/Anime', 'then')")
        for name, matched, pinned in [
            ("no guess", "none", 0),
            ("a guess", "unsure", 0),
            ("matched", "sure", 0),
            ("chosen", "sure", 1),
            ("not anime", "ignored", 1),
            ("an extra", "extra", 0),
        ]:
            conn.execute(
                """INSERT INTO files (folder_id, path, size, modified, found_at, seen_at, matched,
                                      pinned, identified_at)
                   VALUES (1, ?, 1, 1, 'then', 'then', ?, ?, 'then')""",
                (name, matched, pinned),
            )
        conn.commit()

        db.migrate(conn)

        again = conn.execute("SELECT path FROM files WHERE identified_at IS NULL").fetchall()
        assert {row["path"] for row in again} == {"no guess", "a guess"}


def test_earlier_tidy_ups_stop_naming_a_media_server(tmp_path: Path):
    with closing(db.connect(tmp_path / "kura.db")) as conn:
        conn.executescript("".join(f"BEGIN;{sql}COMMIT;" for sql in MIGRATIONS[:8]))
        conn.execute("PRAGMA user_version = 8")
        conn.execute(
            "INSERT INTO plans (title, created_at) VALUES (?, 'then')",
            ("Renamed 3 Trigun files for Plex",),
        )
        conn.execute(
            "INSERT INTO changes (plan_id, position, kind, source, target, label, reason, state)"
            " VALUES (1, 0, 'move', 'a.mkv', 'b.mkv', 'Trigun · S01E01', 'Named for Plex', 'done')"
        )
        conn.commit()

        db.migrate(conn)

        assert conn.execute("SELECT title FROM plans").fetchone()[0] == "Renamed 3 Trigun files"
        assert conn.execute("SELECT reason FROM changes").fetchone()[0] == "Named and filed"
