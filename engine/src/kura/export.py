"""Export: everything Kura knows, in one zip you can open without Kura."""

import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

from kura import __version__, db
from kura.config import DataPaths


def export_data(paths: DataPaths, folder: Path, now: datetime | None = None) -> Path | None:
    """Write `Kura export <date>.zip` into `folder` and return its path.

    Returns None when Kura has no data yet. Never overwrites a file: a second
    export on the same day becomes `Kura export <date> (2).zip`.
    """
    if not paths.database.exists():
        return None
    now = now or datetime.now().astimezone()
    folder.mkdir(parents=True, exist_ok=True)
    target = _unused_name(folder / f"Kura export {now:%Y-%m-%d}.zip")

    with tempfile.TemporaryDirectory() as scratch:
        snapshot = Path(scratch) / "kura.db"
        with (
            closing(db.connect(paths.database)) as source,
            closing(sqlite3.connect(snapshot)) as copy,
        ):
            source.backup(copy)
            copy.execute("PRAGMA journal_mode = DELETE")  # one self-contained file
            settings = _settings(source)
            schema_version = db.schema_version(source)

        manifest = {
            "app": "Kura",
            "version": __version__,
            "exportedAt": now.isoformat(timespec="seconds"),
            "schemaVersion": schema_version,
        }
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "kura.db")
            archive.writestr("settings.json", json.dumps(settings, indent=2))
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return target


def _settings(conn: sqlite3.Connection) -> dict[str, object]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'settings'"
    ).fetchone()
    if not exists:
        return {}
    rows = conn.execute("SELECT key, value FROM settings ORDER BY key")
    return {row["key"]: json.loads(row["value"]) for row in rows}


def _unused_name(path: Path) -> Path:
    candidate, number = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        number += 1
    return candidate
