"""Backups of Kura's database: one a night (the first chance after 03:00), the last seven kept,
each checked as it's written, in the data folder's `backups`. One can be restored: Kura's records
go back to that night, and the files themselves stay as they are. The owner asks for it in
Settings, and it's done as the engine starts again, before anything opens the database; what
Kura knew till then is backed up first.
"""

import json
import logging
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from kura import changes, db
from kura.config import DataPaths

log = logging.getLogger(__name__)

BACKUP_HOUR = 3  # a night's backup is made from 03:00
KEEP = 7  # nightly backups, and as many made before restoring

_NAME = re.compile(r"^kura (\d{4}-\d{2}-\d{2}) (\d{2})(\d{2})( before restoring)?\.db$")
_ASKED = "restore.txt"  # names the backup to restore when the engine next starts
_RESTORED = "backup_restored"  # the settings row saying how the last restore went


class BackupError(Exception):
    """A backup couldn't be made or restored. The message says why, in words."""


@dataclass(frozen=True)
class Backup:
    name: str  # "kura 2026-10-11 0300.db"
    made: datetime  # local time, to the minute
    size: int
    before_restoring: bool  # made just before another backup was restored


@dataclass(frozen=True)
class Restored:
    """How the last restore went."""

    name: str  # the backup
    at: str  # when, as the engine started
    problem: str | None  # why it couldn't be restored, if it couldn't


def backups(paths: DataPaths) -> list[Backup]:
    """Every backup there is, newest first."""
    found: list[Backup] = []
    folder = _folder(paths)
    if not folder.is_dir():
        return found
    for path in folder.iterdir():
        match = _NAME.match(path.name)
        if not match or not path.is_file():
            continue
        made = datetime.fromisoformat(f"{match[1]}T{match[2]}:{match[3]}")
        found.append(Backup(path.name, made, path.stat().st_size, match[4] is not None))
    return sorted(found, key=lambda backup: (backup.made, backup.name), reverse=True)


def due(paths: DataPaths, now: datetime) -> bool:
    """Whether tonight's backup is still to make: none since the last 03:00."""
    night = now.replace(hour=BACKUP_HOUR, minute=0, second=0, microsecond=0, tzinfo=None)
    if now.replace(tzinfo=None) < night:
        night -= timedelta(days=1)
    return not any(b.made >= night and not b.before_restoring for b in backups(paths))


def back_up(paths: DataPaths, now: datetime, *, before_restoring: bool = False) -> Backup:
    """Copies the live database into a backup, checks the copy, and keeps only the last seven
    (the ones made before restoring don't count)."""
    folder = _folder(paths)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y-%m-%d %H%M")
    name = f"kura {stamp}{' before restoring' if before_restoring else ''}.db"
    target = folder / name
    partial = target.with_suffix(".partial")
    try:
        with closing(db.connect(paths.database)) as live, closing(sqlite3.connect(partial)) as copy:
            live.backup(copy)
            copy.execute("PRAGMA journal_mode = DELETE")  # one self-contained file
            [verdict] = copy.execute("PRAGMA integrity_check").fetchone()
        if verdict != "ok":
            raise BackupError(f"The backup didn't check out ({verdict}), so Kura didn't keep it.")
        partial.replace(target)
    except (OSError, sqlite3.Error) as error:
        raise BackupError(f"Kura couldn't make a backup: {error}") from error
    finally:
        partial.unlink(missing_ok=True)
    _prune(paths)
    return next(backup for backup in backups(paths) if backup.name == name)


def ask_to_restore(paths: DataPaths, name: str) -> None:
    """Asks for a backup to be restored when the engine next starts, with nothing else using the
    database: the app starts it again right after."""
    if not _NAME.match(name) or not (_folder(paths) / name).is_file():
        raise BackupError("Kura has no such backup.")
    (_folder(paths) / _ASKED).write_text(name, encoding="utf-8")


def restore_asked(paths: DataPaths, now: datetime) -> bool:
    """As the engine starts: restores the backup the owner asked for, if they did, and keeps how
    it went for Settings to show (`last_restore`). True when one was restored."""
    asked = _folder(paths) / _ASKED
    try:
        name = asked.read_text(encoding="utf-8").strip()
    except OSError:
        return False  # none asked for
    asked.unlink(missing_ok=True)  # asked once, tried once
    problem: str | None = None
    try:
        restore(paths, name, now)
    except BackupError as error:
        problem = str(error)
        log.warning("The backup %s wasn't restored: %s", name, problem)
    outcome = {"name": name, "at": now.isoformat(timespec="seconds"), "problem": problem}
    try:
        with closing(db.connect(paths.database)) as conn, conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (_RESTORED, json.dumps(outcome)),
            )
    except sqlite3.Error:
        log.exception("Kura couldn't note how restoring %s went", name)
    return problem is None


def last_restore(conn: sqlite3.Connection) -> Restored | None:
    """How the last restore went, if there was one."""
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (_RESTORED,)).fetchone()
    if row is None:
        return None
    found = json.loads(row["value"])
    return Restored(str(found["name"]), str(found["at"]), found.get("problem"))


def restore(paths: DataPaths, name: str, now: datetime) -> None:
    """Puts a backup's records in place of the live ones, after backing those up first. The
    caller makes sure nothing else is writing (no scan, nothing converting)."""
    source = _folder(paths) / name
    if not _NAME.match(name) or not source.is_file():
        raise BackupError("Kura has no such backup.")
    back_up(paths, now, before_restoring=True)
    try:
        with (
            closing(sqlite3.connect(source)) as backup,
            closing(db.connect(paths.database)) as live,
        ):
            backup.backup(live)
            db.migrate(live)  # a backup from an older Kura is brought up to date
            changes.recover(live, now=now)
    except (OSError, sqlite3.Error) as error:
        raise BackupError(f"Kura couldn't restore that backup: {error}") from error


def _prune(paths: DataPaths) -> None:
    """Keeps the last seven of each: nightly backups, and those made before restoring."""
    found = backups(paths)
    for before_restoring in (False, True):
        kind = [backup for backup in found if backup.before_restoring is before_restoring]
        for old in kind[KEEP:]:
            (_folder(paths) / old.name).unlink(missing_ok=True)


def _folder(paths: DataPaths) -> Path:
    return paths.root / "backups"
