"""What Kura did, newest first, for the History screen: each tidy-up applied (and whether it was
undone), each file converted (and whether its original is back), and each scan. History comes a
few days at a time, and the owner can clear it, all or what's older than a day, a week or a
month, by hand or every day (Settings > Your data)."""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from kura.changes import ChangeState, changes_of, tally
from kura.core.media import media_from_ffprobe
from kura.core.plan import DELETED

log = logging.getLogger(__name__)

DAYS_A_PAGE = 7  # days with something on them, a page of History


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
    # Copies set aside, and still there (their subtitles uncounted): a conversion's original
    # is gone once cleared out, or at once when the owner chose to delete originals.
    quarantined: int
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
    added: int | None = None  # videos it found new; None for a scan from before Kura counted
    gone: int | None = None  # videos it found gone


@dataclass(frozen=True)
class Page:
    """What Kura did on a few days, newest first, and where the page after it starts."""

    plans: list[PlanDone]
    scans: list[ScanDone]
    older: str | None  # the day the next page starts before ("2026-10-07"); None: that's all


def page(conn: sqlite3.Connection, *, before: str | None = None, days: int = DAYS_A_PAGE) -> Page:
    """Everything on the `days` latest days that have anything on them, before the day `before`
    ("2026-10-14"; None: from today). A day is the local one a thing happened on (scans keep UTC
    times, tidy-ups local ones). A tidy-up undone on a later day is on that day's page too, so
    the undo shows where it happened, whichever page its tidy-up is on."""
    found = [
        row[0]
        for row in conn.execute(
            """SELECT day FROM (
                   SELECT date(applied_at, 'localtime') AS day FROM plans
                   UNION SELECT date(undone_at, 'localtime') FROM plans
                   UNION SELECT date(started_at, 'localtime') FROM scans)
               WHERE day IS NOT NULL AND (?1 IS NULL OR day < ?1)
               ORDER BY day DESC LIMIT ?2""",
            (before, days + 1),
        )
    ]
    shown = found[:days]
    if not shown:
        return Page(plans=[], scans=[], older=None)
    first, last = shown[-1], shown[0]
    rows = conn.execute(
        """SELECT id, kind, title, applied_at, undone_at FROM plans
           WHERE applied_at IS NOT NULL
             AND (date(applied_at, 'localtime') BETWEEN ?1 AND ?2
                  OR date(undone_at, 'localtime') BETWEEN ?1 AND ?2)
           ORDER BY applied_at DESC, id DESC""",
        (first, last),
    ).fetchall()
    scanned = conn.execute(
        """SELECT id, started_at, finished_at, state, problem, note, added, gone FROM scans
           WHERE date(started_at, 'localtime') BETWEEN ? AND ? ORDER BY id DESC""",
        (first, last),
    )
    return Page(
        plans=_done(conn, rows),
        scans=[ScanDone(**dict(row)) for row in scanned],
        older=first if len(found) > days else None,
    )


def clear(conn: sqlite3.Connection, *, keep: timedelta, now: datetime) -> int:
    """Forgets what Kura did more than `keep` ago: tidy-ups and conversions applied (and undone,
    if they were) before then, and scans. What has a copy still in quarantine stays, since
    History puts it back and the clear-out finds it through it, and so does a change still under
    way, the latest scan and one not over yet. Nothing on disk changes. Returns how many went."""
    cutoff = now - keep
    plans = [
        row["id"]
        for row in conn.execute(
            """SELECT p.id, COALESCE(p.undone_at, p.applied_at) AS last FROM plans AS p
               WHERE p.applied_at IS NOT NULL
                 AND NOT EXISTS (
                     SELECT 1 FROM changes AS c WHERE c.plan_id = p.id AND (
                         (c.kind = 'quarantine' AND c.state = 'done' AND c.cleared_at IS NULL)
                         OR c.state IN (?, ?, ?)))
                 AND NOT EXISTS (
                     SELECT 1 FROM jobs AS j WHERE j.plan_id = p.id AND j.state = 'replacing')""",
            (ChangeState.PLANNED, ChangeState.MOVING, ChangeState.UNDOING),
        )
        if _before(row["last"], cutoff)
    ]
    latest = conn.execute("SELECT MAX(id) FROM scans").fetchone()[0]
    scans = [
        row["id"]
        for row in conn.execute(
            "SELECT id, started_at FROM scans WHERE state IN ('done', 'failed') AND id != ?",
            (latest,),
        )
        if _before(row["started_at"], cutoff)
    ]
    with conn:
        for plan_id in plans:
            conn.execute("UPDATE jobs SET plan_id = NULL WHERE plan_id = ?", (plan_id,))
            conn.execute("DELETE FROM changes WHERE plan_id = ?", (plan_id,))
            conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        conn.executemany("DELETE FROM scans WHERE id = ?", [(scan_id,) for scan_id in scans])
    if plans or scans:
        log.info(
            "Cleared %d tidy-ups and conversions and %d scans from History", len(plans), len(scans)
        )
    return len(plans) + len(scans)


def _before(stamp: str, cutoff: datetime) -> bool:
    """Whether a stored time is before `cutoff`: one without an offset is this PC's local time,
    and one Kura can't read stays."""
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    return (moment if moment.tzinfo else moment.astimezone()) < cutoff


def plans(conn: sqlite3.Connection) -> list[PlanDone]:
    """Every tidy-up and conversion that was applied, newest first."""
    rows = conn.execute(
        """SELECT id, kind, title, applied_at, undone_at FROM plans
           WHERE applied_at IS NOT NULL
           ORDER BY applied_at DESC, id DESC"""
    ).fetchall()
    return _done(conn, rows)


def _done(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[PlanDone]:
    """The plans those rows are, with what became of their changes."""
    done: list[PlanDone] = []
    for row in rows:
        changes = changes_of(conn, row["id"])
        states = [change.state for change in changes]
        moved, quarantined = tally(
            c for c in changes if c.state is ChangeState.DONE and c.cleared_at is None
        )
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
        """SELECT id, started_at, finished_at, state, problem, note, added, gone
           FROM scans ORDER BY id DESC LIMIT ?""",
        (count,),
    )
    return [ScanDone(**dict(row)) for row in rows]
