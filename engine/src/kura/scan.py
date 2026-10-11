"""The scan: finds every video in the library folders, then reads each one with ffprobe.

One scan runs at a time, on a background thread with its own database connection. The scans
table holds where it is, and everything it learns is saved as it goes, so a scan that's paused, or
stopped by an exit or a crash, carries on where it was (`recover` at start). Later scans only read
new and changed files. Nothing in the folders changes: a scan only looks.
"""

import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Literal

from kura import db
from kura.config import DataPaths
from kura.core.library import time_left
from kura.core.media import Json
from kura.library import find_files, folders, read_file, unread
from kura.probe import probe
from kura.tools import Tools

log = logging.getLogger(__name__)

_STOPPING = 0.5  # seconds a resume waits for a scan that's still stopping for a pause

type State = Literal["idle", "running", "paused", "done", "failed"]
type Stage = Literal["finding", "reading", "done"]


class ScanBusyError(Exception):
    """A scan is already running."""


class _NoReaderError(Exception):
    """There's no ffprobe to read the files with."""


@dataclass(frozen=True)
class ScanStatus:
    state: State
    stage: Stage | None
    started_at: str | None
    finished_at: str | None
    found: int  # videos this scan found
    to_read: int  # of those, the new and changed ones to read
    read: int
    problems: int  # files in the library that couldn't be read
    current: str | None  # the file being looked at now
    seconds_left: float | None
    unavailable: tuple[str, ...]  # library folders that aren't there (a drive unplugged)
    problem: str | None  # why the scan stopped, when it failed


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Scanner:
    """Runs scans and says how the latest one is going. One per engine."""

    def __init__(
        self,
        paths: DataPaths,
        tools: Tools,
        *,
        read: Callable[[Path], Json] | None = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._paths = paths
        self._tools = tools
        self._read = read
        self._now = now
        self._lock = threading.Lock()
        self._pause = threading.Event()
        self._thread: threading.Thread | None = None
        self._current: Path | None = None
        self._reading_since: float | None = None
        self._read_live = 0
        self._to_read_live = 0

    def status(self) -> ScanStatus:
        with closing(db.connect(self._paths.database)) as conn:
            return self._status(conn)

    def start(self) -> ScanStatus:
        """Starts a new scan of every library folder."""
        with self._lock:
            if self._running():
                raise ScanBusyError
            self._pause.clear()
            started = self._now().isoformat()
            with closing(db.connect(self._paths.database)) as conn, conn:
                scan_id: int = conn.execute(
                    "INSERT INTO scans (started_at, state, stage) VALUES (?, 'running', 'finding') "
                    "RETURNING id",
                    (started,),
                ).fetchone()[0]
            self._launch(scan_id, started, "finding")
        return self.status()

    def pause(self) -> None:
        """Stops the running scan after the file it's on. `resume` carries on from there."""
        self._pause.set()

    def resume(self) -> ScanStatus:
        """Carries on a paused scan, or keeps a running one going."""
        with self._lock:
            was_paused = self._pause.is_set()
            self._pause.clear()
            if was_paused and self._thread is not None:
                # It may have seen the pause just before it was cleared, and be stopping now:
                # let it finish (one file at most), then start it again if it did stop.
                self._thread.join(timeout=_STOPPING)
            if not self._running():
                self._carry_on(states=("paused", "running"))
        return self.status()

    def recover(self) -> None:
        """At start: carries on a scan an exit or a crash stopped. A paused one stays paused."""
        with self._lock:
            self._carry_on(states=("running",))

    def wait(self, timeout: float | None = None) -> None:
        if thread := self._thread:
            thread.join(timeout)

    def _running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _carry_on(self, states: tuple[str, ...]) -> None:
        with closing(db.connect(self._paths.database)) as conn:
            latest = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
            if latest is None or latest["state"] not in states:
                return
            with conn:
                conn.execute("UPDATE scans SET state = 'running' WHERE id = ?", (latest["id"],))
        self._launch(latest["id"], latest["started_at"], latest["stage"])

    def _launch(self, scan_id: int, started: str, stage: Stage) -> None:
        self._thread = threading.Thread(
            target=self._run, args=(scan_id, started, stage), name="scan", daemon=True
        )
        self._thread.start()

    def _run(self, scan_id: int, started: str, stage: Stage) -> None:
        with closing(db.connect(self._paths.database)) as conn:
            try:
                if stage == "finding":
                    if not self._find(conn, started):
                        return self._stop(conn, scan_id, "finding")
                    _set(conn, scan_id, stage="reading")
                if not self._read_all(conn):
                    return self._stop(conn, scan_id, "reading")
                _set(conn, scan_id, state="done", stage="done", finished_at=self._now().isoformat())
            except _NoReaderError:
                _set(conn, scan_id, state="failed", problem=_NEEDS_FFMPEG)
            except Exception as error:
                log.exception("The scan stopped")
                _set(conn, scan_id, state="failed", problem=_stopped_by(error))
            finally:
                self._current = None
                self._reading_since = None
        return None

    def _find(self, conn: sqlite3.Connection, started: str) -> bool:
        """Walks every library folder. False when a pause stopped it."""
        for folder in folders(conn):
            found = find_files(
                conn, folder, stamp=started, on_file=self._looking_at, stop=self._pause.is_set
            )
            if self._pause.is_set():
                return False
            if found is not None:
                for problem in found.problems:
                    log.warning("%s", problem)
        return True

    def _read_all(self, conn: sqlite3.Connection) -> bool:
        """Reads every file still to read. False when a pause stopped it."""
        missing = [
            PureWindowsPath(folder.path) for folder in folders(conn) if not folder.path.is_dir()
        ]
        todo = [
            (file_id, path)
            for file_id, path in unread(conn)
            if not any(PureWindowsPath(path).is_relative_to(folder) for folder in missing)
        ]
        if not todo:
            return True
        read = self._reader()
        self._to_read_live, self._read_live = len(todo), 0
        self._reading_since = time.monotonic()
        for file_id, path in todo:
            if self._pause.is_set():
                return False
            self._looking_at(path)
            if path.is_file():
                read_file(conn, file_id, path, read, now=self._now())
            else:
                with conn:
                    conn.execute(
                        "UPDATE files SET gone_at = ? WHERE id = ?",
                        (self._now().isoformat(), file_id),
                    )
            self._read_live += 1
        return True

    def _reader(self) -> Callable[[Path], Json]:
        if self._read is not None:
            return self._read
        ffprobe = self._tools.path("ffprobe")
        if ffprobe is None:
            raise _NoReaderError
        return lambda path: probe(ffprobe, path)

    def _looking_at(self, path: Path) -> None:
        self._current = path

    def _stop(self, conn: sqlite3.Connection, scan_id: int, stage: Stage) -> None:
        _set(conn, scan_id, state="paused", stage=stage)

    def _status(self, conn: sqlite3.Connection) -> ScanStatus:
        latest = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        unavailable = tuple(str(f.path) for f in folders(conn) if not f.path.is_dir())
        problems: int = conn.execute(
            "SELECT COUNT(*) FROM files WHERE problem IS NOT NULL AND gone_at IS NULL"
        ).fetchone()[0]
        if latest is None:
            return ScanStatus(
                "idle", None, None, None, 0, 0, 0, problems, None, None, unavailable, None
            )
        started: str = latest["started_at"]
        found, read, waiting = conn.execute(
            """SELECT
                 COUNT(*) FILTER (WHERE seen_at = :started AND gone_at IS NULL),
                 COUNT(*) FILTER (WHERE probed_at >= :started AND seen_at = :started),
                 COUNT(*) FILTER (WHERE probed_at IS NULL AND gone_at IS NULL)
               FROM files""",
            {"started": started},
        ).fetchone()
        running = latest["state"] == "running" and self._running()
        state: State = latest["state"] if latest["state"] != "running" or running else "paused"
        left = None
        if running and self._reading_since is not None:
            elapsed = time.monotonic() - self._reading_since
            left = time_left(self._read_live, self._to_read_live, elapsed)
        current = self._current if running else None
        return ScanStatus(
            state=state,
            stage=latest["stage"],
            started_at=started,
            finished_at=latest["finished_at"],
            found=found,
            to_read=read + waiting,
            read=read,
            problems=problems,
            current=str(current) if current else None,
            seconds_left=left,
            unavailable=unavailable,
            problem=latest["problem"],
        )


_NEEDS_FFMPEG = "Kura needs ffmpeg to read the files it found. Download it, then scan again."


def _stopped_by(error: Exception) -> str:
    return (
        f"The scan stopped: {error}. Nothing in your folders was touched; scan again to carry on."
    )


def _set(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    state: str | None = None,
    stage: str | None = None,
    finished_at: str | None = None,
    problem: str | None = None,
) -> None:
    with conn:
        conn.execute(
            """UPDATE scans SET state = COALESCE(?, state), stage = COALESCE(?, stage),
                                finished_at = COALESCE(?, finished_at), problem = ?
               WHERE id = ?""",
            (state, stage, finished_at, problem, scan_id),
        )
