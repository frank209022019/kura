import codecs
import csv
import io
import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from kura import db
from kura.changes import apply_plan, save_plan
from kura.config import DataPaths
from kura.core.plan import Change, ChangeKind, Plan
from kura.export import export_data
from kura.migrations import MIGRATIONS

NOW = datetime(2026, 10, 10, 14, 20, tzinfo=UTC)


def _library_with_one_setting(paths: DataPaths) -> None:
    with closing(db.connect(paths.database)) as conn:
        db.migrate(conn)
        with conn:
            conn.execute(
                "INSERT INTO settings VALUES ('standard', ?)", [json.dumps("Cinema 1080p")]
            )


def test_export_writes_one_zip_with_the_database_settings_and_manifest(
    paths: DataPaths, tmp_path: Path
):
    _library_with_one_setting(paths)

    archive = export_data(paths, tmp_path / "exports", now=NOW)

    expected = tmp_path / "exports" / "Kura export 2026-10-10.zip"
    assert archive == expected
    with zipfile.ZipFile(expected) as zipped:
        assert sorted(zipped.namelist()) == [
            "changes.csv",
            "kura.db",
            "manifest.json",
            "settings.json",
        ]
        assert json.loads(zipped.read("settings.json")) == {"standard": "Cinema 1080p"}
        manifest = json.loads(zipped.read("manifest.json"))
        assert manifest["exportedAt"] == "2026-10-10T14:20:00+00:00"
        assert manifest["schemaVersion"] == len(MIGRATIONS)


def test_the_exported_database_opens_on_its_own(paths: DataPaths, tmp_path: Path):
    _library_with_one_setting(paths)
    archive = export_data(paths, tmp_path / "exports", now=NOW)
    assert archive is not None

    with zipfile.ZipFile(archive) as zipped:
        zipped.extract("kura.db", tmp_path / "unzipped")
    with closing(sqlite3.connect(tmp_path / "unzipped" / "kura.db")) as conn:
        assert conn.execute("SELECT key FROM settings").fetchall() == [("standard",)]


def test_the_export_lists_every_change_kura_made(paths: DataPaths, tmp_path: Path):
    source = tmp_path / "Downloads" / "[DB] Death_Note_07 (720p).mkv"
    source.parent.mkdir()
    source.write_text("video", encoding="utf-8")
    target = tmp_path / "Anime" / "デスノート (2006)" / "デスノート (2006) - S01E07.mkv"
    with closing(db.connect(paths.database)) as conn:
        db.migrate(conn)
        change = Change(ChangeKind.MOVE, source, target, "デスノート · S01E07", "Named for Plex")
        plan_id = save_plan(conn, Plan((change,)), "Tidy up: デスノート", now=NOW)
        apply_plan(conn, plan_id, now=NOW)

    archive = export_data(paths, tmp_path / "exports", now=NOW)

    assert archive is not None
    with zipfile.ZipFile(archive) as zipped:
        raw = zipped.read("changes.csv")
    assert raw.startswith(codecs.BOM_UTF8)  # so Excel reads the Japanese title
    assert list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))) == [
        {
            "plan": "1",
            "plan_title": "Tidy up: デスノート",
            "planned_at": "2026-10-10T14:20:00+00:00",
            "applied_at": "2026-10-10T14:20:00+00:00",
            "undone_at": "",
            "position": "1",
            "kind": "move",
            "state": "done",
            "source": str(source),
            "target": str(target),
            "label": "デスノート · S01E07",
            "reason": "Named for Plex",
            "problem": "",
        }
    ]


def test_a_second_export_on_the_same_day_keeps_both(paths: DataPaths, tmp_path: Path):
    _library_with_one_setting(paths)

    first = export_data(paths, tmp_path, now=NOW)
    second = export_data(paths, tmp_path, now=NOW)

    assert first == tmp_path / "Kura export 2026-10-10.zip"
    assert second == tmp_path / "Kura export 2026-10-10 (2).zip"


def test_there_is_nothing_to_export_before_kura_has_data(paths: DataPaths, tmp_path: Path):
    assert export_data(paths, tmp_path, now=NOW) is None
    assert list(tmp_path.iterdir()) == []
