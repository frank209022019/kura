"""The scan job: find every video, read each one, pause, and carry on after an exit."""

import itertools
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kura.config import DataPaths
from kura.core.media import Json
from kura.library import add_folder
from kura.probe import ProbeError
from kura.scan import ScanBusyError, Scanner
from kura.tools import Tools
from tests.fake_ffprobe import REPORT

NOW = datetime(2026, 10, 11, 9, 30, tzinfo=UTC)


def reads(path: Path) -> Json:
    return REPORT


def scanner(paths: DataPaths, read: Callable[[Path], Json] | None = reads) -> Scanner:
    """A scanner whose clock moves on a second each time it's read."""
    seconds = itertools.count(1)
    return Scanner(
        paths, Tools(paths, items=()), read=read, now=lambda: NOW + timedelta(seconds=next(seconds))
    )


def finished(scan: Scanner) -> None:
    scan.wait(timeout=10)


def test_a_scan_finds_and_reads_every_video(
    paths: DataPaths, conn: sqlite3.Connection, anime: Path
):
    add_folder(conn, anime, now=NOW)
    scan = scanner(paths)

    scan.start()
    finished(scan)

    status = scan.status()
    assert (status.state, status.stage) == ("done", "done")
    assert (status.found, status.to_read, status.read, status.problems) == (3, 3, 3, 0)
    assert status.finished_at is not None
    assert status.unavailable == ()


def test_a_second_scan_reads_only_new_files(
    paths: DataPaths, conn: sqlite3.Connection, anime: Path
):
    add_folder(conn, anime, now=NOW)
    scan = scanner(paths)
    scan.start()
    finished(scan)
    (anime / "Dragon Ball" / "Dragon Ball - 002 - The Emperor`s Quest.mkv").write_bytes(b"new")

    scan.start()
    finished(scan)

    status = scan.status()
    assert (status.found, status.to_read, status.read) == (4, 1, 1)


def test_files_that_cant_be_read_are_counted(
    paths: DataPaths, conn: sqlite3.Connection, anime: Path
):
    def picky(path: Path) -> Json:
        if path.suffix == ".avi":
            raise ProbeError(
                "Kura couldn't read it (Invalid data). It may be damaged, or not a video."
            )
        return REPORT

    add_folder(conn, anime, now=NOW)
    scan = scanner(paths, picky)
    scan.start()
    finished(scan)

    assert scan.status().problems == 1


def test_pausing_stops_between_files_and_resuming_carries_on(
    paths: DataPaths, conn: sqlite3.Connection, anime: Path
):
    reading, go_on = threading.Event(), threading.Event()

    def slow(path: Path) -> Json:
        reading.set()
        go_on.wait(10)
        return REPORT

    add_folder(conn, anime, now=NOW)
    scan = scanner(paths, slow)
    scan.start()
    assert reading.wait(10)

    scan.pause()
    go_on.set()
    finished(scan)
    paused = scan.status()
    assert (paused.state, paused.stage, paused.read) == ("paused", "reading", 1)

    scan.resume()
    finished(scan)
    done = scan.status()
    assert (done.state, done.read, done.to_read) == ("done", 3, 3)


def test_a_scan_stopped_by_an_exit_carries_on_at_the_next_start(
    paths: DataPaths, conn: sqlite3.Connection, anime: Path
):
    add_folder(conn, anime, now=NOW)
    with conn:
        conn.execute(
            "INSERT INTO scans (started_at, state, stage) VALUES (?, 'running', 'finding')",
            (NOW.isoformat(),),
        )
    scan = scanner(paths)  # a fresh engine, after the exit

    scan.recover()
    finished(scan)

    status = scan.status()
    assert (status.state, status.found, status.read) == ("done", 3, 3)


def test_a_paused_scan_stays_paused_after_a_restart(
    paths: DataPaths, conn: sqlite3.Connection, anime: Path
):
    add_folder(conn, anime, now=NOW)
    with conn:
        conn.execute(
            "INSERT INTO scans (started_at, state, stage) VALUES (?, 'paused', 'reading')",
            (NOW.isoformat(),),
        )
    scan = scanner(paths)

    scan.recover()

    assert scan.status().state == "paused"


def test_only_one_scan_runs_at_a_time(paths: DataPaths, conn: sqlite3.Connection, anime: Path):
    reading, go_on = threading.Event(), threading.Event()

    def slow(path: Path) -> Json:
        reading.set()
        go_on.wait(10)
        return REPORT

    add_folder(conn, anime, now=NOW)
    scan = scanner(paths, slow)
    scan.start()
    assert reading.wait(10)

    with pytest.raises(ScanBusyError):
        scan.start()
    go_on.set()
    finished(scan)


def test_without_ffmpeg_the_scan_says_what_to_do(
    paths: DataPaths, conn: sqlite3.Connection, anime: Path
):
    add_folder(conn, anime, now=NOW)
    scan = scanner(paths, read=None)  # the real ffprobe, which hasn't been downloaded

    scan.start()
    finished(scan)

    status = scan.status()
    assert (status.state, status.found, status.read) == ("failed", 3, 0)
    assert status.problem == (
        "Kura needs ffmpeg to read the files it found. Download it, then scan again."
    )


def test_a_folder_on_an_unplugged_drive_is_named_and_the_rest_is_scanned(
    paths: DataPaths, conn: sqlite3.Connection, anime: Path, tmp_path: Path
):
    other = tmp_path / "Other anime"
    other.mkdir()
    add_folder(conn, anime, now=NOW)
    add_folder(conn, other, now=NOW)
    other.rmdir()  # as if its drive were unplugged
    scan = scanner(paths)

    scan.start()
    finished(scan)

    status = scan.status()
    assert status.state == "done"
    assert status.unavailable == (str(other),)
    assert status.read == 3


def test_before_any_scan_there_is_nothing_to_report(paths: DataPaths, conn: sqlite3.Connection):
    status = scanner(paths).status()

    assert (status.state, status.stage, status.found) == ("idle", None, 0)
