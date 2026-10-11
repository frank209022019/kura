"""What Kura did, newest first, for the History screen: each tidy-up applied (and whether it was
undone), and each scan."""

import sqlite3
from dataclasses import dataclass

from kura.changes import ChangeState, changes_of, tally


@dataclass(frozen=True)
class PlanDone:
    id: int
    title: str  # "Renamed 26 Cowboy Bebop files for Plex"
    applied_at: str
    undone_at: str | None
    moved: int  # videos and subtitles filed, and still there
    quarantined: int  # copies set aside, and still there (their subtitles uncounted)
    failed: int  # changes that couldn't be made
    undone: int  # changes put back


@dataclass(frozen=True)
class ScanDone:
    id: int
    started_at: str
    finished_at: str | None
    state: str  # running, paused, done or failed
    problem: str | None
    note: str | None


def plans(conn: sqlite3.Connection) -> list[PlanDone]:
    """Every tidy-up that was applied, newest first."""
    rows = conn.execute(
        """SELECT id, title, applied_at, undone_at FROM plans
           WHERE applied_at IS NOT NULL
           ORDER BY applied_at DESC, id DESC"""
    ).fetchall()
    done: list[PlanDone] = []
    for row in rows:
        changes = changes_of(conn, row["id"])
        states = [change.state for change in changes]
        moved, quarantined = tally(c for c in changes if c.state is ChangeState.DONE)
        done.append(
            PlanDone(
                **dict(row),
                moved=moved,
                quarantined=quarantined,
                failed=states.count(ChangeState.FAILED),
                undone=states.count(ChangeState.UNDONE),
            )
        )
    return done


def scans(conn: sqlite3.Connection, count: int = 50) -> list[ScanDone]:
    """The latest scans, newest first."""
    rows = conn.execute(
        """SELECT id, started_at, finished_at, state, problem, note
           FROM scans ORDER BY id DESC LIMIT ?""",
        (count,),
    )
    return [ScanDone(**dict(row)) for row in rows]
