"""What Kura did, newest first, for the History screen: each tidy-up applied (and whether it was
undone), each file converted (and whether its original is back), and each scan."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from kura.changes import ChangeState, changes_of, tally
from kura.core.media import media_from_ffprobe
from kura.core.plan import DELETED


@dataclass(frozen=True)
class Picture:
    """A video's picture and size, before or after converting."""

    height: int | None
    codec: str | None
    size: int | None


@dataclass(frozen=True)
class Conversion:
    job_id: int
    method: str  # remux, reencode, fast or best
    before: Picture
    after: Picture
    seconds: float | None  # how long converting took
    restored: bool  # the original is back in its place


@dataclass(frozen=True)
class PlanDone:
    id: int
    kind: Literal["tidy", "convert"]
    title: str  # "Renamed 26 Cowboy Bebop files", "Converted Trigun · S01E03"
    applied_at: str
    undone_at: str | None
    moved: int  # videos and subtitles filed, and still there
    quarantined: int  # copies set aside, and still there (their subtitles uncounted)
    failed: int  # changes that couldn't be made
    undone: int  # changes put back
    deleted: bool = False  # the owner deleted these videos: they went to quarantine
    conversion: Conversion | None = None  # what a conversion made of its file


@dataclass(frozen=True)
class ScanDone:
    id: int
    started_at: str
    finished_at: str | None
    state: str  # running, paused, done or failed
    problem: str | None
    note: str | None


def plans(conn: sqlite3.Connection) -> list[PlanDone]:
    """Every tidy-up and conversion that was applied, newest first."""
    rows = conn.execute(
        """SELECT id, kind, title, applied_at, undone_at FROM plans
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
                deleted=bool(changes) and all(change.reason == DELETED for change in changes),
                conversion=_conversion(conn, row["id"]) if row["kind"] == "convert" else None,
            )
        )
    return done


def _conversion(conn: sqlite3.Connection, plan_id: int) -> Conversion | None:
    job = conn.execute("SELECT * FROM jobs WHERE plan_id = ?", (plan_id,)).fetchone()
    if job is None:
        return None
    took = None
    if job["started_at"] and job["finished_at"]:
        began, ended = (datetime.fromisoformat(job[key]) for key in ("started_at", "finished_at"))
        took = (ended - began).total_seconds()
    return Conversion(
        job_id=job["id"],
        method=job["method"],
        before=_picture(job["source_probe"], job["source_size"]),
        after=_picture(job["output_probe"], job["output_size"]),
        seconds=took,
        restored=job["state"] == "restored",
    )


def _picture(probe: str | None, size: int | None) -> Picture:
    video = media_from_ffprobe(json.loads(probe)).video if probe else None
    return Picture(video.height if video else None, video.codec if video else None, size)


def scans(conn: sqlite3.Connection, count: int = 50) -> list[ScanDone]:
    """The latest scans, newest first."""
    rows = conn.execute(
        """SELECT id, started_at, finished_at, state, problem, note
           FROM scans ORDER BY id DESC LIMIT ?""",
        (count,),
    )
    return [ScanDone(**dict(row)) for row in rows]
