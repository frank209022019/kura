"""Tidying up: what Kura proposes, applying the changes the owner keeps, and History, where any
tidy-up can be undone. Nothing moves while a scan runs, and no scan starts while files move."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import Field

from kura import history, tidy
from kura.api.common import ApiModel, Database, Scans
from kura.changes import SavedChange
from kura.convert import ConvertError
from kura.core.plan import KEPT_BOTH, ChangeKind
from kura.queue import Queue
from kura.scan import ScanBusyError

router = APIRouter()


class CopyFacts(ApiModel):
    path: str
    height: int | None
    codec: str | None
    audio: list[str]  # languages
    subtitles: int  # tracks that can be switched off
    size: int
    plays: bool


class Duplicate(ApiModel):
    label: str  # "Cowboy Bebop · S01E01"
    keep: CopyFacts
    drop: list[CopyFacts]
    reason: str


class ProposedChange(ApiModel):
    kind: Literal["move", "quarantine"]
    source: str
    target: str
    root: str  # the library folder it's in
    label: str
    reason: str
    category: Literal["rename", "mixed", "duplicate"]
    title_id: int
    title: str
    taken: bool  # its name was another file's, so it gets "(2)": Kura never overwrites a file


class SkippedFile(ApiModel):
    path: str
    reason: str


class TidyProposal(ApiModel):
    changes: list[ProposedChange]
    skipped: list[SkippedFile]  # videos that stay where they are, and why
    duplicates: list[Duplicate]
    waiting: int  # videos that need a match first
    broken: int  # videos that won't play


class ReviewedChange(ApiModel):
    """A proposed change, as the owner saw it."""

    source: str
    kind: Literal["move", "quarantine"]
    target: str


class TidyRequest(ApiModel):
    # The changes to make (of videos, and the subtitles that go with them), as reviewed.
    changes: list[ReviewedChange]
    # Copies the owner chose to keep over others of the same episode.
    keep: list[str] = Field(default_factory=list[str])


class ChangeProblem(ApiModel):
    label: str
    source: str
    problem: str


class TidyResult(ApiModel):
    plan_id: int | None  # None when nothing was asked for
    moved: int
    quarantined: int
    problems: list[ChangeProblem]


class Picture(ApiModel):
    height: int | None
    codec: str | None
    size: int | None


class Conversion(ApiModel):
    job_id: int
    method: Literal["remux", "reencode", "fast", "best"]
    before: Picture
    after: Picture
    seconds: float | None  # how long converting took
    restored: bool  # the original is back in its place


class PlanDone(ApiModel):
    id: int
    kind: Literal["tidy", "convert"]
    title: str
    applied_at: str
    undone_at: str | None
    moved: int
    quarantined: int
    failed: int
    undone: int
    deleted: bool  # the owner deleted these videos: they went to quarantine
    conversion: Conversion | None  # for a conversion: what the file became


class ScanDone(ApiModel):
    id: int
    started_at: str
    finished_at: str | None
    state: str
    problem: str | None
    note: str | None


class History(ApiModel):
    plans: list[PlanDone]  # newest first
    scans: list[ScanDone]  # newest first


Keep = Annotated[list[str], Query(description="Copies to keep over the others of an episode")]


@router.get("/tidy")
def proposal(conn: Database, keep: Keep = []) -> TidyProposal:  # noqa: B006 - FastAPI's way
    """Where every identified video would go, filed for Plex. Nothing changes."""
    found = tidy.propose(conn, day=_now().date(), keep=keep)
    counts = conn.execute(
        """SELECT SUM(matched IN ('unsure', 'none') AND pinned = 0) AS waiting,
                  SUM(problem IS NOT NULL) AS broken
           FROM files WHERE gone_at IS NULL"""
    ).fetchone()
    return TidyProposal(
        changes=[
            ProposedChange(
                kind=p.change.kind.value,
                source=str(p.change.source),
                target=str(p.change.target),
                root=str(p.root),
                label=p.change.label,
                reason=p.change.reason,
                category=p.category,
                title_id=p.title_id,
                title=p.title,
                taken=p.change.reason.endswith(KEPT_BOTH),
            )
            for p in found.changes
        ],
        skipped=[SkippedFile(path=str(path), reason=why) for path, why in found.skipped],
        duplicates=[
            Duplicate(
                label=d.label,
                keep=_copy(d.keep),
                drop=[_copy(copy) for copy in d.drop],
                reason=d.reason,
            )
            for d in found.duplicates
        ],
        waiting=counts["waiting"] or 0,
        broken=counts["broken"] or 0,
    )


@router.post("/tidy")
def apply_tidy(body: TidyRequest, conn: Database, scans: Scans) -> TidyResult:
    """Makes the changes the owner reviewed, journaled so History can undo them. None is made
    when Kura proposes any of them differently now."""
    reviewed = [tidy.Reviewed(c.source, ChangeKind(c.kind), c.target) for c in body.changes]
    try:
        with scans.hold():
            done = tidy.apply(conn, reviewed, now=_now(), keep=body.keep)
    except ScanBusyError as busy:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{busy} Tidy up once it's done, so Kura knows every file."
        ) from None
    except tidy.ProposalChangedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Kura's proposal changed since you looked at it. Look it over again before applying.",
        ) from None
    return _result(done)


class DeleteRequest(ApiModel):
    files: list[int]  # the videos to delete, each with the subtitles named after it


@router.post("/files/delete")
def delete_files(body: DeleteRequest, conn: Database, scans: Scans) -> TidyResult:
    """Deletes videos the way Kura deletes: into the quarantine on their own drive, with their
    subtitles, journaled so History can put them back till the quarantine is cleared out."""
    try:
        with scans.hold():
            done = tidy.delete(conn, body.files, now=_now())
    except ScanBusyError as busy:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{busy} Delete it once that's done."
        ) from None
    except tidy.ConvertingError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    return _result(done)


@router.get("/history")
def what_kura_did(conn: Database) -> History:
    """Every tidy-up applied and every scan, newest first."""
    return History(
        plans=[PlanDone.model_validate(asdict(plan)) for plan in history.plans(conn)],
        scans=[ScanDone.model_validate(scan.__dict__) for scan in history.scans(conn)],
    )


@router.post("/plans/{plan_id}/undo")
def undo_plan(plan_id: int, conn: Database, scans: Scans, request: Request) -> TidyResult:
    """Puts back what a tidy-up moved, or what couldn't go back last time. For a conversion,
    the original comes back in the converted file's place."""
    plan = conn.execute("SELECT kind FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kura has no such tidy-up.")
    try:
        if plan["kind"] == "convert":
            return _put_back(conn, plan_id, request)
        with scans.hold():
            done = tidy.undo(conn, plan_id, now=_now())
    except ScanBusyError as busy:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{busy} Undo it once that's done.") from None
    return _result(done)


def _put_back(conn: Database, plan_id: int, request: Request) -> TidyResult:
    """A conversion undone: its original back from quarantine (kura/queue.py)."""
    job = conn.execute("SELECT id FROM jobs WHERE plan_id = ?", (plan_id,)).fetchone()
    worker: Queue = request.app.state.queue
    try:
        worker.restore(job["id"] if job else 0)
    except ConvertError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return TidyResult(plan_id=plan_id, moved=1, quarantined=0, problems=[])


def _result(done: tidy.Tidied) -> TidyResult:
    return TidyResult(
        plan_id=done.plan_id,
        moved=done.moved,
        quarantined=done.quarantined,
        problems=[_problem(change) for change in done.problems],
    )


def _problem(change: SavedChange) -> ChangeProblem:
    return ChangeProblem(
        label=change.label, source=str(change.source), problem=change.problem or "It failed."
    )


def _copy(copy: tidy.CopyFacts) -> CopyFacts:
    return CopyFacts(
        path=str(copy.path),
        height=copy.height,
        codec=copy.codec,
        audio=list(copy.audio),
        subtitles=copy.subtitles,
        size=copy.size,
        plays=copy.plays,
    )


def _now() -> datetime:
    return datetime.now().astimezone()
