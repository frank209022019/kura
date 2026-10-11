"""What Kura did, newest first, for the History screen: each tidy-up applied (and whether it was
undone), and each scan."""

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class PlanDone:
    id: int
    title: str  # "Renamed 26 Cowboy Bebop files for Plex"
    applied_at: str
    undone_at: str | None
    moved: int  # videos and subtitles moved, and still there
    quarantined: int  # copies set aside, and still there
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
        """SELECT p.id, p.title, p.applied_at, p.undone_at,
                  SUM(c.kind = 'move' AND c.state = 'done') AS moved,
                  SUM(c.kind = 'quarantine' AND c.state = 'done') AS quarantined,
                  SUM(c.state = 'failed') AS failed,
                  SUM(c.state = 'undone') AS undone
           FROM plans AS p JOIN changes AS c ON c.plan_id = p.id
           WHERE p.applied_at IS NOT NULL
           GROUP BY p.id
           ORDER BY p.applied_at DESC, p.id DESC"""
    )
    return [PlanDone(**dict(row)) for row in rows]


def scans(conn: sqlite3.Connection, count: int = 50) -> list[ScanDone]:
    """The latest scans, newest first."""
    rows = conn.execute(
        """SELECT id, started_at, finished_at, state, problem, note
           FROM scans ORDER BY id DESC LIMIT ?""",
        (count,),
    )
    return [ScanDone(**dict(row)) for row in rows]
