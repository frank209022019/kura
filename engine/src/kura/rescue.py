"""When Kura's records are damaged (kura.db scribbled over by a disk fault, or cut short by a power
cut mid-write), the engine starts without them: nothing else can work, so the app asks only what
to do. It offers the newest backup that opens, which brings Kura back to when it was made; with
none, new records, as on Kura's first day. Either way the damaged file is kept beside them as it
is, never deleted (kura/backups.py, `set_aside`). The files in the library aren't touched.
"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime

from kura import db
from kura.backups import (
    Backup,
    BackupError,
    backups,
    checks_out,
    damaged,
    note_restored,
    restore,
    set_aside,
    unreadable,
)
from kura.config import DataPaths


@dataclass(frozen=True)
class Damage:
    """Kura's records are damaged: what's wrong, and the backup to restore."""

    problem: str  # in SQLite's words: "file is not a database"
    backup: Backup | None  # the newest backup that opens, if there is one


def damage(paths: DataPaths) -> Damage | None:
    """As the engine starts: what's wrong with Kura's records, if they're damaged, and the newest
    backup that opens. None when they're fine, or there are none yet (a first start)."""
    problem = unreadable(paths.database) or _fault(paths)
    if problem is None:
        return None
    return Damage(problem, next((b for b in backups(paths) if checks_out(paths, b)), None))


def restore_newest(paths: DataPaths, now: datetime) -> Backup:
    """Restores the newest backup that opens over damaged records, setting them aside as they
    are, and notes how it went for Settings. Raises BackupError when it can't."""
    found = next((b for b in backups(paths) if checks_out(paths, b)), None)
    if found is None:
        raise BackupError("No backup opens, so there's none to restore.")
    restore(paths, found.name, now, damaged=True)
    note_restored(paths, found.name, now, None)
    return found


def start_afresh(paths: DataPaths, now: datetime) -> None:
    """Sets damaged records aside as they are, so Kura starts again with new ones, as on its
    first day. Raises BackupError when they can't be moved."""
    set_aside(paths, now)


def _fault(paths: DataPaths) -> str | None:
    """What's wrong inside records that open, in SQLite's words; None when they check out."""
    if not paths.database.exists():
        return None
    try:
        with closing(db.connect(paths.database)) as conn:
            [verdict] = conn.execute("PRAGMA quick_check(1)").fetchone()
    except sqlite3.DatabaseError as error:
        if not damaged(error):
            raise  # not damage (another program holding it, say): the engine says why
        return str(error)
    return None if verdict == "ok" else str(verdict)
