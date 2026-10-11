"""Tidying up: what Kura proposes, applying the changes the owner keeps, and History, where any
tidy-up can be undone. Nothing moves while a scan runs, and no scan starts while files move."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import Field

from kura import history, tidy
from kura.api.common import ApiModel, Database, Scans
from kura.changes import SavedChange
from kura.core.plan import ChangeKind
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


class PlanDone(ApiModel):
    id: int
    title: str
    applied_at: str
    undone_at: str | None
    moved: int
    quarantined: int
    failed: int
    undone: int


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


@router.get("/history")
def what_kura_did(conn: Database) -> History:
    """Every tidy-up applied and every scan, newest first."""
    return History(
        plans=[PlanDone.model_validate(plan.__dict__) for plan in history.plans(conn)],
        scans=[ScanDone.model_validate(scan.__dict__) for scan in history.scans(conn)],
    )


@router.post("/plans/{plan_id}/undo")
def undo_plan(plan_id: int, conn: Database, scans: Scans) -> TidyResult:
    """Puts back what a tidy-up moved, or what couldn't go back last time."""
    if conn.execute("SELECT 1 FROM plans WHERE id = ?", (plan_id,)).fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kura has no such tidy-up.")
    try:
        with scans.hold():
            done = tidy.undo(conn, plan_id, now=_now())
    except ScanBusyError as busy:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{busy} Undo it once that's done.") from None
    return _result(done)


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
