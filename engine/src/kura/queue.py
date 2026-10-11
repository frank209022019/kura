"""The conversion queue: the files waiting to be converted, in the owner's order, and the worker
that converts them one at a time on a background thread (kura/convert.py converts each).

Jobs live in the jobs table (migration 6): queued, running, replacing (the result taking its
original's place), then done, failed, skipped or restored. The worker takes the first queued job
while the queue isn't paused, and on the nights-only schedule only between 23:00 and 07:00 (a
file started before 07:00 finishes). Pausing or skipping stops a file being made at once (ffmpeg
is stopped, and the original is as it was); paused, the file is first in line again and starts
over when the queue resumes. An exit does the same. A file made already is checked and put in
place though the queue pauses, and thrown away when it's skipped. A file whose drive isn't
connected waits while the others go; a drive without room for a result pauses the queue, saying
so. While a result takes its original's place no scan runs (Scanner.hold): the worker waits for
one that's running. While a file converts, Windows doesn't put the PC to sleep. After a crash,
`recover` puts a job that was converting back in line and settles one whose result was taking
its original's place. Once nothing waits, the app is told what the batch came to, and it's told
when the queue pauses itself: a Windows notification while Kura is in the tray.
"""

import ctypes
import json
import logging
import sqlite3
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Generator, Iterable
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from datetime import time as clock_time
from pathlib import Path
from typing import Literal

from kura import db
from kura.config import DataPaths
from kura.convert import (
    CONVERTED,
    SHADER,
    WORKING,
    ConvertError,
    NoRoomError,
    Programs,
    Progress,
    Stopped,
    convert,
    label_of,
    lighter,
    restore,
    settle,
)
from kura.core.estimate import estimate
from kura.core.media import media_from_ffprobe
from kura.core.standard import Method, Standard, decide
from kura.preferences import library_standard
from kura.probe import probe
from kura.scan import ScanBusyError, Scanner
from kura.tools import Tools
from kura.upscale import MODEL, model

log = logging.getLogger(__name__)

type JobState = Literal["queued", "running", "replacing", "done", "failed", "skipped", "restored"]
type Stage = Literal["looking", "converting", "checking", "replacing"]
type Schedule = Literal["now", "nights"]  # convert whenever files wait, or only at night

_IDLE = 30.0  # seconds the worker rests with nothing to do; adding or resuming wakes it at once
_HOLD_RETRY = 2.0  # seconds between asks for scans to hold off
_SPEED_WINDOW = 600.0  # seconds of frames the speed is measured over, as the queue board shows
_PAUSED = "queue_paused"  # the settings rows that keep the queue's state across restarts
_SCHEDULE = "queue_schedule"
_HELD_UP = "queue_problem"  # why the queue paused itself (a full drive), till it's resumed
NIGHT = (clock_time(23, 0), clock_time(7, 0))  # when the nights-only schedule converts
NO_FFMPEG = "Kura needs ffmpeg to convert. It's downloaded on the setup's Tools step."


@dataclass(frozen=True)
class Job:
    id: int
    file_id: int
    path: str
    label: str  # "Dragon Ball Z · S01E06"
    title_id: int | None
    title: str | None
    season: int | None
    episode: int | None
    method: Method  # what it gets: the owner's choice, never more than suits the file
    state: JobState
    position: int
    gpu_seconds: float  # how long it takes, as estimated
    added_at: str
    started_at: str | None
    finished_at: str | None
    problem: str | None  # why it failed, in words
    source_size: int  # the original, in bytes
    output_size: int | None  # the result, once there
    width: int | None = None  # the result's picture, for a file still to finish
    height: int | None = None
    drive_missing: bool = False  # waiting, and its library folder's drive isn't connected


@dataclass(frozen=True)
class Running:
    """The job converting now, and how it's going."""

    job: Job
    stage: Stage
    frames: int
    total: int
    seconds_left: float | None
    fps: float | None  # frames a second, over the last ten minutes


@dataclass(frozen=True)
class QueueStatus:
    paused: bool
    schedule: Schedule
    waits_for_night: bool  # nights only, and it's day: files start again at 23:00
    problem: str | None  # why nothing converts though files wait (no ffmpeg, say)
    running: Running | None
    queued: tuple[Job, ...]  # in the order they'll go
    gpu_seconds: float  # the work left: the running file's and the queued ones'
    today: tuple[Job, ...]  # finished today (done, failed or skipped), newest first


class Queue:
    """The conversion queue and its worker. One per engine."""

    def __init__(
        self,
        paths: DataPaths,
        scanner: Scanner,
        programs: Callable[[], Programs | None],
        *,
        now: Callable[[], datetime],
        clock: Callable[[], float] = time.monotonic,
        notify: Callable[[str, str], None] = lambda _title, _body: None,
    ) -> None:
        """`programs` gives what converting runs, or None while Kura has no ffmpeg. `notify`
        tells the app something worth a notification: a title and a line."""
        self._paths = paths
        self._notify = notify
        self._batch: list[int] = []  # files converted (or failed) since nothing last waited
        self._scanner = scanner
        self._programs = programs
        self._now = now
        self._clock = clock
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self._job_id: int | None = None  # the job converting now
        self._stop_for: Literal["pause", "skip"] | None = None
        self._progress: Progress | None = None
        self._frames: deque[tuple[float, int]] = deque()  # (when, frames done) while converting
        self._problem: str | None = None

    def start(self) -> None:
        """Converts until `stop`. Call `recover` first, before any scan starts."""
        self._thread = threading.Thread(target=self._loop, name="queue", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stops the worker: the file converting now is first in line at the next start."""
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=30)

    def recover(self) -> None:
        """At start: a job a crash stopped while converting waits in line again (its unfinished
        result goes), and one whose result was taking its original's place is settled."""
        programs = self._programs()
        read = programs.read if programs else None
        with closing(db.connect(self._paths.database)) as conn:
            for row in conn.execute(
                """SELECT f.path FROM jobs AS j JOIN files AS f ON f.id = j.file_id
                   WHERE j.state = 'running'"""
            ).fetchall():
                path = Path(row["path"])
                unfinished = path.with_name(path.stem + WORKING)
                try:
                    unfinished.unlink(missing_ok=True)
                except OSError:  # still open: converting the file again takes it away
                    log.warning("Couldn't remove %s", unfinished)
            with conn:
                conn.execute(
                    "UPDATE jobs SET state = 'queued', started_at = NULL WHERE state = 'running'"
                )
            for row in conn.execute("SELECT id FROM jobs WHERE state = 'replacing'").fetchall():
                settle(conn, row["id"], read, self._now())

    def add(self, file_ids: Iterable[int], method: Method | None = None) -> int:
        """Puts files at the end of the queue, in the order given. A file already in it, or one
        with nothing to convert (at the standard already, unreadable, or gone), is passed over.
        `method` is the owner's choice, which a file gets only when it suits it (the AI model is
        for SD). Returns how many joined."""
        stamp = self._now().isoformat()
        added = 0
        with closing(db.connect(self._paths.database)) as conn, conn:
            standard = library_standard(conn)
            waiting = {
                row[0]
                for row in conn.execute(
                    "SELECT file_id FROM jobs WHERE state IN ('queued', 'running', 'replacing')"
                )
            }
            last: int = conn.execute("SELECT COALESCE(MAX(position), 0) FROM jobs").fetchone()[0]
            for file_id in dict.fromkeys(file_ids):
                row = conn.execute(
                    """SELECT probe FROM files
                       WHERE id = ? AND gone_at IS NULL AND problem IS NULL""",
                    (file_id,),
                ).fetchone()
                if file_id in waiting or row is None or row["probe"] is None:
                    continue
                decided = decide(media_from_ffprobe(json.loads(row["probe"])), standard).method
                if decided not in CONVERTED:
                    continue  # at the standard already: tidying up renames it
                last += 1
                conn.execute(
                    "INSERT INTO jobs (file_id, method, position, added_at) VALUES (?, ?, ?, ?)",
                    (file_id, lighter(decided, method or decided).value, last, stamp),
                )
                added += 1
        self._wake.set()
        return added

    def pause(self) -> None:
        """Stops the file converting now and takes no other until `resume`."""
        self._set_paused(paused=True)
        with self._lock:
            if self._job_id is not None:
                self._stop_for = "pause"

    def resume(self) -> None:
        self._set_paused(paused=False)
        with closing(db.connect(self._paths.database)) as conn, conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (_HELD_UP,))
        self._wake.set()

    def plan(self, schedule: Schedule) -> None:
        """Converts whenever files wait ("now"), or only at night ("nights")."""
        with closing(db.connect(self._paths.database)) as conn, conn:
            _save(conn, _SCHEDULE, schedule)
        self._wake.set()

    def skip(self, job_id: int) -> None:
        """Passes over a file: the one converting now stops, and one waiting leaves the line.
        Raises LookupError when it's neither."""
        with self._lock:
            if self._job_id == job_id:
                self._stop_for = "skip"
                return
            with closing(db.connect(self._paths.database)) as conn, conn:
                done = conn.execute(
                    """UPDATE jobs SET state = 'skipped', finished_at = ?
                       WHERE id = ? AND state = 'queued'""",
                    (self._now().isoformat(), job_id),
                ).rowcount
        if not done:
            raise LookupError("That file isn't waiting or converting.")

    def remove(self, job_id: int) -> None:
        """Takes a waiting file out of the queue, as if it had never been added."""
        with self._lock, closing(db.connect(self._paths.database)) as conn, conn:
            gone = conn.execute(
                "DELETE FROM jobs WHERE id = ? AND state = 'queued'", (job_id,)
            ).rowcount
        if not gone:
            raise LookupError("That file isn't waiting in the queue.")

    def move(self, job_id: int, before: int | None) -> None:
        """Puts a waiting file before another (`before`), or last when that's None."""
        with closing(db.connect(self._paths.database)) as conn, conn:
            order = [
                row[0]
                for row in conn.execute(
                    "SELECT id FROM jobs WHERE state = 'queued' ORDER BY position, id"
                )
            ]
            if job_id not in order:
                raise LookupError("That file isn't waiting in the queue.")
            order.remove(job_id)
            order.insert(order.index(before) if before in order else len(order), job_id)
            first: int = conn.execute(
                "SELECT COALESCE(MIN(position), 1) FROM jobs WHERE state = 'queued'"
            ).fetchone()[0]
            conn.executemany(
                "UPDATE jobs SET position = ? WHERE id = ?",
                [(first + index, job) for index, job in enumerate(order)],
            )

    def retry(self, job_id: int) -> None:
        """A failed or skipped file goes back in the queue, last."""
        with closing(db.connect(self._paths.database)) as conn, conn:
            last: int = conn.execute("SELECT COALESCE(MAX(position), 0) FROM jobs").fetchone()[0]
            again = conn.execute(
                """UPDATE jobs SET state = 'queued', position = ?, problem = NULL,
                          started_at = NULL, finished_at = NULL
                   WHERE id = ? AND state IN ('failed', 'skipped')""",
                (last + 1, job_id),
            ).rowcount
        if not again:
            raise LookupError("That file didn't fail and wasn't skipped.")
        self._wake.set()

    def restore(self, job_id: int) -> None:
        """Puts a converted file's original back in its place. Raises ScanBusyError while a scan
        runs or files move, and ConvertError when it can't."""
        with self._scanner.hold(), closing(db.connect(self._paths.database)) as conn:
            restore(conn, job_id, now=self._now())

    def status(self) -> QueueStatus:
        with closing(db.connect(self._paths.database)) as conn:
            standard = library_standard(conn)
            paused = _paused(conn)
            schedule = _schedule(conn)
            held_up = _saved(conn, _HELD_UP)
            start_of_day = self._now().replace(hour=0, minute=0, second=0, microsecond=0)
            rows = conn.execute(
                f"""{_JOBS}
                    WHERE j.state IN ('queued', 'running', 'replacing') OR j.finished_at >= ?
                    ORDER BY j.position, j.id""",
                (start_of_day.isoformat(),),
            ).fetchall()
        connected = _Drives()
        jobs = [
            replace(_job(row, standard), drive_missing=not connected(row["root"]))
            if row["state"] == "queued"
            else _job(row, standard)
            for row in rows
        ]
        with self._lock:
            progress, running_id = self._progress, self._job_id
            fps = self._fps()
        running: Running | None = None
        for job in jobs:
            if job.state in ("running", "replacing"):
                running = self._running(job, progress if job.id == running_id else None, fps)
        queued = tuple(job for job in jobs if job.state == "queued")
        today = sorted(
            (job for job in jobs if job.finished_at is not None and job.state != "queued"),
            key=lambda job: job.finished_at or "",
            reverse=True,
        )
        left = sum(job.gpu_seconds for job in queued)
        if running is not None:
            left += running.seconds_left if running.seconds_left is not None else 0.0
        problem = self._problem if queued and not paused else None
        if isinstance(held_up, str):
            problem = held_up
        day = not _at_night(self._now())
        return QueueStatus(
            paused,
            schedule,
            schedule == "nights" and day,
            problem,
            running,
            queued,
            left,
            tuple(today),
        )

    def work_once(self) -> bool:
        """Converts the first file waiting, unless the queue is paused or waits for the night.
        False when there was none to convert (or no ffmpeg to convert it with)."""
        with closing(db.connect(self._paths.database)) as conn:
            if _paused(conn) or (_schedule(conn) == "nights" and not _at_night(self._now())):
                return False
            programs = self._programs()
            self._problem = None if programs else NO_FFMPEG
            if programs is None:
                return False
            # Taken under the lock skip and remove take too, so a file skipped or taken out a
            # moment before never converts; one whose drive isn't connected waits.
            with self._lock:
                connected = _Drives()
                waiting = conn.execute(
                    """SELECT j.id, d.path AS root FROM jobs AS j
                       JOIN files AS f ON f.id = j.file_id
                       JOIN folders AS d ON d.id = f.folder_id
                       WHERE j.state = 'queued' ORDER BY j.position, j.id"""
                ).fetchall()
                first = next((job["id"] for job in waiting if connected(job["root"])), None)
                if first is None:
                    return False
                with conn:
                    row = conn.execute(
                        """UPDATE jobs SET state = 'running', started_at = ?, problem = NULL
                           WHERE id = ? AND state = 'queued' RETURNING id""",
                        (self._now().isoformat(), first),
                    ).fetchone()
                if row is None:
                    return False
                self._job_id, self._stop_for, self._progress = row["id"], None, None
                self._frames.clear()
            self._work(conn, row["id"], programs)
        return True

    def _work(self, conn: sqlite3.Connection, job_id: int, programs: Programs) -> None:
        try:
            with _awake():
                convert(
                    conn,
                    job_id,
                    programs,
                    library_standard(conn),
                    now=self._now,
                    report=self._heard,
                    stop=self._stop_asked,
                    discard=self._discard_asked,
                    hold=self._hold,
                )
        except Stopped:
            self._stopped(conn, job_id)
        except NoRoomError as error:
            self._back_in_line(conn, job_id)  # it, and the rest, wait for room
            problem = f"{error} Make room, then resume the queue."
            with conn:
                _save(conn, _PAUSED, True)
                _save(conn, _HELD_UP, problem)
            self._notify("The queue paused", problem)
        except ConvertError as error:
            self._finished(conn, job_id, "failed", str(error))
        except Exception:
            log.exception("Converting job %d hit a problem", job_id)
            self._finished(conn, job_id, "failed", "Kura hit a problem converting it.")
        finally:
            with self._lock:
                self._job_id, self._stop_for, self._progress = None, None, None
        self._noted(conn, job_id)

    def _noted(self, conn: sqlite3.Connection, job_id: int) -> None:
        """A file converted (or failed) joins the batch, and once nothing waits, the app is told
        what the batch came to."""
        row = conn.execute("SELECT state FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is not None and row["state"] in ("done", "failed"):
            self._batch.append(job_id)
        waiting = conn.execute(
            "SELECT 1 FROM jobs WHERE state IN ('queued', 'running', 'replacing') LIMIT 1"
        ).fetchone()
        if waiting is not None or not self._batch:
            return
        marks = ", ".join("?" * len(self._batch))
        rows = conn.execute(
            f"""SELECT j.state, j.source_size, j.output_size, f.season, f.episode, f.title_id,
                       t.name AS title
                FROM jobs AS j JOIN files AS f ON f.id = j.file_id
                LEFT JOIN titles AS t ON t.id = f.title_id
                WHERE j.id IN ({marks})""",  # noqa: S608 - only placeholders go in
            self._batch,
        ).fetchall()
        self._batch.clear()
        self._notify(*_told(rows))

    def _stopped(self, conn: sqlite3.Connection, job_id: int) -> None:
        """A file stopped on purpose: skipped, or first in line again (paused, or Kura closing)."""
        with self._lock:
            skipped = self._stop_for == "skip"
        if skipped:
            self._finished(conn, job_id, "skipped", None)
            return
        self._back_in_line(conn, job_id)

    def _back_in_line(self, conn: sqlite3.Connection, job_id: int) -> None:
        """A file that stopped goes back to the queue, first in line."""
        with conn:
            first: int = conn.execute(
                "SELECT COALESCE(MIN(position), 1) FROM jobs WHERE state = 'queued'"
            ).fetchone()[0]
            conn.execute(
                """UPDATE jobs SET state = 'queued', started_at = NULL, position = ?
                   WHERE id = ?""",
                (first - 1, job_id),
            )

    def _finished(
        self, conn: sqlite3.Connection, job_id: int, state: JobState, problem: str | None
    ) -> None:
        with conn:
            conn.execute(
                "UPDATE jobs SET state = ?, problem = ?, finished_at = ? WHERE id = ?",
                (state, problem, self._now().isoformat(), job_id),
            )

    def _heard(self, progress: Progress) -> None:
        with self._lock:
            self._progress = progress
            if progress.stage == "converting":
                moment = self._clock()
                self._frames.append((moment, progress.frames))
                while self._frames and moment - self._frames[0][0] > _SPEED_WINDOW:
                    self._frames.popleft()

    def _fps(self) -> float | None:
        """Frames a second over the last ten minutes, once there's a second of them."""
        if len(self._frames) < 2:
            return None
        (began, first), (now, last) = self._frames[0], self._frames[-1]
        return (last - first) / (now - began) if now - began >= 1 and last > first else None

    def _running(self, job: Job, progress: Progress | None, fps: float | None) -> Running:
        if progress is None:
            return Running(
                job, "replacing" if job.state == "replacing" else "looking", 0, 0, None, None
            )
        left: float | None = None
        if progress.stage == "converting" and fps:
            left = max(progress.total - progress.frames, 0) / fps
        elif progress.stage in ("checking", "replacing"):
            left = 0.0
        return Running(job, progress.stage, progress.frames, progress.total, left, fps)

    def _stop_asked(self) -> bool:
        with self._lock:
            return self._stop_for is not None or self._stopping.is_set()

    def _discard_asked(self) -> bool:
        """Whether a result made already is thrown away: skipped, or Kura is closing. Paused,
        it's put in place."""
        with self._lock:
            return self._stop_for == "skip" or self._stopping.is_set()

    @contextmanager
    def _hold(self) -> Generator[None]:
        """Holds scans off while a result takes its original's place, waiting while one runs
        (or a tidy-up moves files)."""
        with ExitStack() as held:
            while True:
                try:
                    held.enter_context(self._scanner.hold())
                    break
                except ScanBusyError:
                    if self._discard_asked():
                        raise Stopped from None
                    self._stopping.wait(_HOLD_RETRY)
            yield

    def _set_paused(self, *, paused: bool) -> None:
        with closing(db.connect(self._paths.database)) as conn, conn:
            _save(conn, _PAUSED, paused)

    def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                worked = self.work_once()
            except Exception:  # the worker must outlive any one bad file
                log.exception("The conversion queue hit a problem")
                worked = False
            if not worked:
                self._wake.wait(_IDLE)
                self._wake.clear()


def _told(rows: list[sqlite3.Row]) -> tuple[str, str]:
    """What a finished batch is called and what it came to: "Dragon Ball Z, season 1 is done",
    "39 episodes · all checked · 9.1 GB → 17.5 GB"."""
    titles = {row["title_id"] for row in rows}
    seasons = {row["season"] for row in rows}
    name = rows[0]["title"]
    if len(titles) == 1 and name and len(seasons) == 1 and None not in seasons:
        season = rows[0]["season"]
        title = f"{name}, season {season} is done" if season else f"{name}, the specials are done"
    elif len(titles) == 1 and name:
        title = f"{name} is done"
    else:
        title = "The queue is done"
    done = [row for row in rows if row["state"] == "done"]
    failed = len(rows) - len(done)
    what = "episode" if all(row["episode"] is not None for row in rows) else "file"
    if failed:
        count = f"{len(done)} converted, {failed} failed"
    else:
        count = f"{len(done)} {what}{'' if len(done) == 1 else 's'} · all checked"
    before = sum(row["source_size"] or 0 for row in done)
    after = sum(row["output_size"] or 0 for row in done)
    return title, f"{count} · {_size(before)} → {_size(after)}" if done else count


def _size(count: int) -> str:
    """Bytes as the app writes them: "412 MB", "9.1 GB", "35 GB"."""
    if count >= 10**10:
        return f"{round(count / 10**9)} GB"
    if count >= 10**9:
        return f"{count / 10**9:.1f} GB"
    if count >= 10**6:
        return f"{round(count / 10**6)} MB"
    return f"{max(1, round(count / 10**3)) if count else 0} KB"


def programs_from(tools: Tools) -> Programs | None:
    """What converting runs: Kura's ffmpeg and ffprobe (None until they're downloaded), the AI
    model and Anime4K's shader, which ship inside Kura."""
    ffmpeg, ffprobe = tools.path("ffmpeg"), tools.path("ffprobe")
    if ffmpeg is None or ffprobe is None:
        return None
    return Programs(
        ffmpeg=[str(ffmpeg)],
        read=lambda path: probe(ffprobe, path),
        model=lambda width, height: model(width, height, MODEL),
        shader=SHADER,
    )


_JOBS = """SELECT j.*, f.path, f.probe, f.size, f.season, f.episode, f.title_id,
                  t.name AS title, d.path AS root
           FROM jobs AS j JOIN files AS f ON f.id = j.file_id
           JOIN folders AS d ON d.id = f.folder_id
           LEFT JOIN titles AS t ON t.id = f.title_id"""


class _Drives:
    """Whether library folders are there (a drive plugged in), each looked at once."""

    def __init__(self) -> None:
        self._seen: dict[str, bool] = {}

    def __call__(self, folder: str) -> bool:
        if folder not in self._seen:
            self._seen[folder] = Path(folder).is_dir()
        return self._seen[folder]


def _job(row: sqlite3.Row, standard: Standard) -> Job:
    """A job as the queue shows it. One still to finish gets what suits its file, with an
    estimate; a finished one says what it got (its file's record is the result's now)."""
    method = Method(row["method"])
    gpu_seconds = 0.0
    width = height = None
    if row["probe"] and row["state"] in ("queued", "running", "replacing"):
        media = media_from_ffprobe(json.loads(row["probe"]))
        decision = decide(media, standard)
        decision = replace(decision, method=lighter(decision.method, method))
        method, width, height = decision.method, decision.width, decision.height
        gpu_seconds = estimate(media, decision, standard).gpu_seconds
    return Job(
        id=row["id"],
        file_id=row["file_id"],
        path=row["path"],
        label=label_of(row),
        title_id=row["title_id"],
        title=row["title"],
        season=row["season"],
        episode=row["episode"],
        method=method,
        state=row["state"],
        position=row["position"],
        gpu_seconds=gpu_seconds,
        added_at=row["added_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        problem=row["problem"],
        source_size=row["source_size"] or row["size"],
        output_size=row["output_size"],
        width=width,
        height=height,
    )


def _paused(conn: sqlite3.Connection) -> bool:
    return _saved(conn, _PAUSED) is True


def _schedule(conn: sqlite3.Connection) -> Schedule:
    return "nights" if _saved(conn, _SCHEDULE) == "nights" else "now"


def _at_night(moment: datetime) -> bool:
    start, end = NIGHT
    return moment.time() >= start or moment.time() < end


def _saved(conn: sqlite3.Connection, key: str) -> object:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else None


def _save(conn: sqlite3.Connection, key: str, value: object) -> None:
    """One of the queue's settings rows, inside the caller's transaction."""
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


@contextmanager
def _awake() -> Generator[None]:
    """Keeps Windows from sleeping while a file converts (the display may still turn off)."""
    if sys.platform != "win32":
        yield
        return
    continuous, system = 0x80000000, 0x00000001  # ES_CONTINUOUS, ES_SYSTEM_REQUIRED
    kernel = ctypes.windll.kernel32
    kernel.SetThreadExecutionState(continuous | system)
    try:
        yield
    finally:
        kernel.SetThreadExecutionState(continuous)
