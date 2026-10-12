"""Converting the library to its standard: what can be converted, with estimates for each way of
converting it, the queue that converts it, one file at a time, and making room for it."""

import json
import shutil
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import Field

from kura import preview
from kura import queue as conversions
from kura.api.common import ApiModel, Database, Paths, Scans
from kura.convert import CONVERTED, ConvertError, Programs, label_of, lighter
from kura.core.estimate import estimate
from kura.core.library import drive_of
from kura.core.media import media_from_ffprobe
from kura.core.standard import Method, decide
from kura.gpu import Gpu
from kura.preferences import library_standard
from kura.quarantine import empty, set_aside_by_drive
from kura.scan import ScanBusyError

router = APIRouter()

type Chosen = Literal["best", "fast", "reencode"]  # the ways the owner can pick from
_CHOICES: tuple[Chosen, ...] = ("best", "fast", "reencode")


class Estimate(ApiModel):
    method: Literal["remux", "reencode", "fast", "best"]  # what the file gets
    gpu_seconds: float


class Convertible(ApiModel):
    """A video not at the library's standard yet."""

    file_id: int
    label: str  # "Dragon Ball Z · S01E06"
    title_id: int | None
    title: str | None
    season: int | None
    episode: int | None
    seconds: float  # how long it plays
    height: int
    aspect: str  # "4:3", "16:9"
    size: int
    drive: str  # "D:"
    # What each way of converting gives it (never more than suits it), and how long it takes.
    ways: dict[str, Estimate]
    output_bytes: int  # the result's size, about
    waiting: bool  # in the queue already, or converting
    broken: bool  # it won't play: it can't be converted


class ConvertOptions(ApiModel):
    standard: str  # "Cinema 1080p"
    files: list[Convertible]
    free: dict[str, int]  # bytes free on each drive the files are on
    set_aside: dict[str, int]  # bytes emptying each drive's quarantine would free


class Job(ApiModel):
    id: int
    file_id: int
    path: str
    label: str
    title_id: int | None
    title: str | None
    season: int | None
    episode: int | None
    method: Literal["remux", "reencode", "fast", "best"]
    state: Literal["queued", "running", "replacing", "done", "failed", "skipped", "restored"]
    gpu_seconds: float
    added_at: str
    started_at: str | None
    finished_at: str | None
    problem: str | None
    source_size: int
    output_size: int | None
    width: int | None  # the result's picture, for a file still to finish
    height: int | None
    drive_missing: bool  # waiting, and its drive isn't connected
    # Made, and waiting beside its original for another app (a player) to let go of it: when
    # Kura tries again to put it in place.
    retry_at: str | None
    log: str | None  # what ffmpeg said, when a conversion failed ("Copy full log")
    no_room: bool  # waiting for room on its drive while the others go


class Room(ApiModel):
    """A drive without room for the files waiting to convert on it."""

    drive: str  # "D:"
    paused: bool  # the queue paused for it; else the files that don't fit wait while others go
    files: int  # files waiting to convert on it
    needed: int  # the free space their results want, in bytes
    free: int  # bytes free on it now
    fit: int  # how many of them fit now, in turn
    set_aside: int  # bytes its quarantine would free, emptied now


class Running(ApiModel):
    job: Job
    stage: Literal["looking", "converting", "checking", "replacing"]
    frames: int
    total: int
    seconds_left: float | None
    fps: float | None


class GpuReading(ApiModel):
    busy: int  # percent
    celsius: int


class QueueStatus(ApiModel):
    paused: bool
    schedule: Literal["now", "nights"]
    waits_for_night: bool  # nights only, and it's day (or tonight's run is over)
    problem: str | None  # why nothing converts though files wait
    running: Running | None
    queued: list[Job]  # in the order they'll go
    gpu_seconds: float  # the work left
    today: list[Job]  # finished today, newest first
    gpu: GpuReading | None  # the card's load and temperature, while a file converts
    room: Room | None  # a drive without room for what waits on it
    # Nights only, at night: when tonight's run takes its last file (07:00, or earlier when the
    # owner said to stop early), local time; and whether they did.
    ends_at: str | None
    early: bool


class AddRequest(ApiModel):
    files: list[int]
    method: Chosen | None = None  # the owner's choice; else what suits each file
    # When they convert: "now" or "nights" set the schedule and resume the queue if it was
    # paused; "after" leaves the queue as it is, so they go after what waits.
    when: Literal["now", "nights", "after"] = "after"
    # Drives ("D:") without room for them all: the files that fit there convert, and the rest
    # wait for room while the others go.
    fit: list[str] = Field(default_factory=list[str])


class DriveRequest(ApiModel):
    drive: str  # "D:"


class Emptied(ApiModel):
    files: int  # files deleted from the drive's quarantine


class Added(ApiModel):
    added: int


class MoveRequest(ApiModel):
    before: int | None = Field(default=None, description="The job to go before; None: last")


class ScheduleRequest(ApiModel):
    schedule: Literal["now", "nights"]


class TonightRequest(ApiModel):
    early: bool  # stop at 03:00 tonight (past it, after the file converting), or go on till 07:00


def _queue(request: Request) -> conversions.Queue:
    worker: conversions.Queue = request.app.state.queue
    return worker


def _gpu(request: Request) -> Gpu:
    gpu: Gpu = request.app.state.gpu
    return gpu


Queue = Annotated[conversions.Queue, Depends(_queue)]
Card = Annotated[Gpu, Depends(_gpu)]


@router.get("/convert")
def what_to_convert(conn: Database) -> ConvertOptions:
    """Every video not at the standard yet, with what each way of converting it would take."""
    standard = library_standard(conn)
    rows = conn.execute(
        """SELECT f.id, f.path, f.probe, f.problem, f.season, f.episode, f.title_id,
                  t.name AS title,
                  EXISTS (SELECT 1 FROM jobs AS j WHERE j.file_id = f.id
                          AND j.state IN ('queued', 'running', 'replacing')) AS waiting
           FROM files AS f LEFT JOIN titles AS t ON t.id = f.title_id
           WHERE f.gone_at IS NULL AND f.probe IS NOT NULL AND f.matched != 'ignored'
           ORDER BY t.released, t.name, f.season, f.episode, f.path"""
    ).fetchall()
    found: list[Convertible] = []
    for row in rows:
        media = media_from_ffprobe(json.loads(row["probe"]))
        video = media.video
        decision = decide(media, standard)
        if video is None or decision.method not in CONVERTED:
            continue
        broken = row["problem"] is not None
        ways: dict[str, Estimate] = {}
        output = 0
        if not broken:
            for choice in _CHOICES:
                method = lighter(decision.method, Method(choice))
                made = estimate(media, replace(decision, method=method), standard)
                ways[choice] = Estimate.model_validate(
                    {"method": method.value, "gpu_seconds": made.gpu_seconds}
                )
                output = made.output_bytes
        found.append(
            Convertible(
                file_id=row["id"],
                label=label_of(row),
                title_id=row["title_id"],
                title=row["title"],
                season=row["season"],
                episode=row["episode"],
                seconds=media.duration or 0.0,
                height=video.height,
                aspect=f"{video.display_aspect.numerator}:{video.display_aspect.denominator}",
                size=media.size or 0,
                drive=drive_of(row["path"]),
                ways=ways,
                output_bytes=output,
                waiting=bool(row["waiting"]),
                broken=broken,
            )
        )
    return ConvertOptions(
        standard=standard.name,
        files=found,
        free=_free({file.drive for file in found}),
        set_aside=set_aside_by_drive(conn),
    )


@router.get(
    "/convert/{file_id}/preview/{side}",
    response_class=FileResponse,
    responses={200: {"content": {"image/png": {}}}},
)
def see_it_first(
    file_id: int,
    side: Literal["before", "after"],
    conn: Database,
    paths: Paths,
    request: Request,
    way: Chosen = "best",
    point: int = 1,
) -> FileResponse:
    """One side of the comparison: a frame of the file as it is (`before`), or as `way` makes
    it (`after`), taken at one of three points (0, 1 or 2: 15%, 50% and 80% of the way in)."""
    kit: Programs | None = request.app.state.programs()
    if kit is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, conversions.NO_FFMPEG)
    row = conn.execute(
        "SELECT path, probe FROM files WHERE id = ? AND gone_at IS NULL", (file_id,)
    ).fetchone()
    if row is None or row["probe"] is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That file isn't in the library any more.")
    media = media_from_ffprobe(json.loads(row["probe"]))
    try:
        picture = preview.frame(
            paths,
            kit,
            Path(row["path"]),
            media,
            library_standard(conn),
            side=side,
            way=Method(way),
            point=point,
        )
    except preview.PreviewError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return FileResponse(picture, media_type="image/png")


@router.get("/queue")
def queue_status(queue: Queue, card: Card) -> QueueStatus:
    return _status(queue.status(), card)


@router.post("/queue")
def add_to_queue(body: AddRequest, queue: Queue) -> Added:
    """Puts files at the end of the queue, to convert now, at night, or after what waits."""
    for drive in body.fit:  # before they join too: one without room never pauses the queue
        queue.convert_what_fits(drive)
    if body.when != "after":
        queue.plan(body.when)  # before they join: the worker never sees the old schedule
        queue.resume()
    added = queue.add(body.files, Method(body.method) if body.method else None)
    return Added(added=added)


@router.post("/queue/pause")
def pause_queue(queue: Queue, card: Card) -> QueueStatus:
    """Stops the file converting now (it starts over on resuming) and takes no other."""
    queue.pause()
    return _status(queue.status(), card)


@router.post("/queue/resume")
def resume_queue(queue: Queue, card: Card) -> QueueStatus:
    queue.resume()
    return _status(queue.status(), card)


@router.post("/queue/fit")
def convert_what_fits(body: DriveRequest, queue: Queue, card: Card) -> QueueStatus:
    """On a drive without room for all that waits on it, the files that fit convert, and the
    rest wait for room while the others go. The queue goes on if it paused."""
    queue.convert_what_fits(body.drive)
    queue.resume()
    return _status(queue.status(), card)


@router.post("/quarantine/empty")
def empty_quarantine(body: DriveRequest, conn: Database, scans: Scans, queue: Queue) -> Emptied:
    """Deletes everything set aside on a drive now, however recently, to make room there: it
    can't be put back after. Kura asks the owner first. Files waiting for room look again."""
    try:
        with scans.hold():
            cleared = empty(conn, body.drive, now=datetime.now().astimezone())
    except ScanBusyError as busy:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{busy} Empty it once that's done."
        ) from None
    queue.wake()
    return Emptied(files=cleared)


@router.put("/queue/schedule")
def plan_queue(body: ScheduleRequest, queue: Queue, card: Card) -> QueueStatus:
    """Converts whenever files wait, or only at night (23:00 to 07:00)."""
    queue.plan(body.schedule)
    return _status(queue.status(), card)


@router.put("/queue/tonight")
def plan_tonight(body: TonightRequest, queue: Queue, card: Card) -> QueueStatus:
    """On the nights-only schedule: tonight's run stops taking files at 03:00, so Windows' sleep
    comes back sooner, or goes on till 07:00."""
    queue.stop_early(early=body.early)
    return _status(queue.status(), card)


@router.post("/queue/{job_id}/skip", status_code=status.HTTP_204_NO_CONTENT)
def skip_job(job_id: int, queue: Queue) -> None:
    """Passes over a file: the one converting stops, one waiting leaves the line."""
    with _known():
        queue.skip(job_id)


@router.delete("/queue/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_job(job_id: int, queue: Queue) -> None:
    with _known():
        queue.remove(job_id)


@router.post("/queue/{job_id}/move", status_code=status.HTTP_204_NO_CONTENT)
def move_job(job_id: int, body: MoveRequest, queue: Queue) -> None:
    with _known():
        queue.move(job_id, body.before)


@router.post("/queue/{job_id}/broken", status_code=status.HTTP_204_NO_CONTENT)
def mark_broken(job_id: int, queue: Queue) -> None:
    """Marks a file whose conversion failed as broken: the library counts it among the files
    that won't play, and it isn't converted again till it changes."""
    with _known():
        queue.mark_broken(job_id)


@router.post("/queue/{job_id}/retry", status_code=status.HTTP_204_NO_CONTENT)
def retry_job(job_id: int, queue: Queue) -> None:
    """A failed or skipped file goes back in the queue, last; one made and waiting for another
    app to let go of its original is tried again now ("Try now")."""
    with _known():
        queue.retry(job_id)


@router.post("/queue/{job_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_original(job_id: int, queue: Queue) -> None:
    """Puts a converted file's original back in its place, from quarantine."""
    try:
        queue.restore(job_id)
    except ScanBusyError as busy:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{busy} Put it back once that's done."
        ) from None
    except ConvertError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None


@contextmanager
def _known() -> Generator[None]:
    """A job the queue doesn't have (or not in that state) is a 404."""
    try:
        yield
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None


def _status(found: conversions.QueueStatus, card: Gpu) -> QueueStatus:
    reading = card.reading() if found.running is not None else None
    return QueueStatus(
        paused=found.paused,
        schedule=found.schedule,
        waits_for_night=found.waits_for_night,
        problem=found.problem,
        running=Running(
            job=_job(found.running.job),
            stage=found.running.stage,
            frames=found.running.frames,
            total=found.running.total,
            seconds_left=found.running.seconds_left,
            fps=found.running.fps,
        )
        if found.running
        else None,
        queued=[_job(job) for job in found.queued],
        gpu_seconds=found.gpu_seconds,
        today=[_job(job) for job in found.today],
        gpu=GpuReading(busy=reading.busy, celsius=reading.celsius) if reading else None,
        room=Room.model_validate(found.room.__dict__) if found.room else None,
        ends_at=found.ends_at,
        early=found.early,
    )


def _job(job: conversions.Job) -> Job:
    return Job.model_validate({**job.__dict__, "method": job.method.value})


def _free(drives: set[str]) -> dict[str, int]:
    free: dict[str, int] = {}
    for drive in sorted(drives):
        try:
            free[drive] = shutil.disk_usage(f"{drive}\\").free
        except OSError:
            continue  # unplugged
    return free
