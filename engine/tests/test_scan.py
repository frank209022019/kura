"""The scan job: find every video, read each one, pause, and carry on after an exit."""

import itertools
import json
import os
import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import kura.scan
from kura import db
from kura.config import DataPaths
from kura.core.media import Json
from kura.library import Folder, Found, add_folder
from kura.probe import ProbeError, ProbeToolError
from kura.scan import ScanBusyError, Scanner
from kura.tools import Tools, manifest
from tests.fake_ffprobe import REPORT
from tests.fake_web import FakeWeb
from tests.services import internet

NOW = datetime(2026, 10, 11, 9, 30, tzinfo=UTC)


def reads(path: Path) -> Json:
    return REPORT


_SECONDS = itertools.count(1)  # one clock for every scanner, so a later scan starts later


def scanner(
    paths: DataPaths,
    read: Callable[[Path], Json] | None = reads,
    tools: Tools | None = None,
    web: FakeWeb | None = None,
) -> Scanner:
    """A scanner whose clock moves on a second each time it's read. Nothing it asks of AniList
    or TMDB is answered unless `web` says so."""
    return Scanner(
        paths,
        tools or Tools(paths, items=()),
        read=read,
        now=lambda: NOW + timedelta(seconds=next(_SECONDS)),
        transport=web or FakeWeb(),
    )


def installed_ffmpeg(paths: DataPaths) -> Tools:
    """Kura's tools with ffmpeg downloaded and unpacked, as after setup."""
    ffmpeg = next(item for item in manifest() if item.id == "ffmpeg")
    folder = paths.tools / "ffmpeg"
    folder.mkdir(parents=True)
    program = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    (folder / program).write_bytes(b"probe")
    marker = {"version": ffmpeg.version, "sha256": ffmpeg.sha256, "files": [program]}
    (folder / "kura-download.json").write_text(json.dumps(marker), encoding="utf-8")
    tools = Tools(paths, items=(ffmpeg,))
    assert tools.path("ffprobe") == folder / program
    return tools


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


def test_a_broken_ffprobe_stops_the_scan_and_marks_no_file(
    paths: DataPaths, conn: sqlite3.Connection, anime: Path
):
    def broken(path: Path) -> Json:
        raise ProbeToolError("ffprobe stopped with code 0xC0000135")

    add_folder(conn, anime, now=NOW)
    tools = installed_ffmpeg(paths)
    scan = scanner(paths, broken, tools)
    scan.start()
    finished(scan)

    status = scan.status()
    assert (status.state, status.read, status.problems) == ("failed", 0, 0)
    assert status.problem == (
        "ffprobe couldn't run (ffprobe stopped with code 0xC0000135), so Kura stopped the scan "
        "without marking any file. Get ffmpeg again in Setup, then scan again."
    )
    [(_, ffmpeg)] = tools.status()
    assert ffmpeg.state == "missing"  # so Setup offers to download it again

    again = scanner(paths)
    again.start()
    finished(again)
    assert (again.status().state, again.status().read) == ("done", 3)


def test_a_new_scan_tries_again_the_files_that_couldnt_be_read(
    paths: DataPaths, conn: sqlite3.Connection, anime: Path
):
    def picky(path: Path) -> Json:
        if path.suffix == ".avi":
            raise ProbeError(
                "Kura couldn't read it (Invalid data). It may be damaged, or not a video."
            )
        return REPORT

    add_folder(conn, anime, now=NOW)
    first = scanner(paths, picky)
    first.start()
    finished(first)
    assert first.status().problems == 1

    second = scanner(paths)
    second.start()
    finished(second)

    status = second.status()
    assert (status.problems, status.to_read, status.read) == (0, 1, 1)


def test_a_folder_added_while_the_scan_is_finding_is_scanned_too(
    paths: DataPaths,
    conn: sqlite3.Connection,
    anime: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    more = tmp_path / "More anime"
    (more / "Trigun").mkdir(parents=True)
    (more / "Trigun" / "Trigun - 03.mkv").write_bytes(b"three")
    add_folder(conn, anime, now=NOW)
    walk = kura.scan.find_files

    def while_walking(conn: sqlite3.Connection, folder: Folder, **options: Any) -> Found | None:
        if folder.path == anime:
            with closing(db.connect(paths.database)) as other:
                add_folder(other, more, now=NOW)
        return walk(conn, folder, **options)

    monkeypatch.setattr(kura.scan, "find_files", while_walking)
    scan = scanner(paths)
    scan.start()
    finished(scan)

    assert (scan.status().found, scan.status().read) == (4, 4)


def test_a_file_whose_folder_vanishes_mid_scan_is_left_for_the_next_one(
    paths: DataPaths, conn: sqlite3.Connection, anime: Path
):
    downloads = anime / "Downloads"

    def moving_downloads(path: Path) -> Json:
        if downloads.exists():
            downloads.rename(anime / "Downloads, moved")  # as if its drive dropped out
        return REPORT

    add_folder(conn, anime, now=NOW)
    scan = scanner(paths, moving_downloads)
    scan.start()
    finished(scan)

    row = conn.execute(
        "SELECT gone_at, probed_at FROM files WHERE path LIKE '%[Group] DBZ%'"
    ).fetchone()
    assert (row["gone_at"], row["probed_at"]) == (None, None)


def test_a_scan_identifies_what_it_read(paths: DataPaths, conn: sqlite3.Connection, anime: Path):
    add_folder(conn, anime, now=NOW)
    scan = scanner(paths, web=internet(tmdb=False))

    scan.start()
    finished(scan)

    status = scan.status()
    assert (status.state, status.stage) == ("done", "done")
    # [Group] DBZ - 001 is Dragon Ball Z; Dragon Ball and Broly aren't in the stood-in AniList.
    assert (status.titles, status.waiting, status.note) == (1, 2, None)


def test_offline_a_scan_still_finishes_and_says_titles_wait(
    paths: DataPaths, conn: sqlite3.Connection, anime: Path
):
    add_folder(conn, anime, now=NOW)
    offline = internet()
    offline.offline = True
    scan = scanner(paths, web=offline)

    scan.start()
    finished(scan)

    status = scan.status()
    assert status.state == "done"
    assert (status.note or "").startswith(
        "Titles wait for the next scan: AniList couldn't be asked"
    )


def test_a_folder_holding_two_anime_is_counted_as_mixed(
    paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    root = tmp_path / "Library"
    for name in (
        "Downloads/Dragon Ball Z - 001.mkv",
        "Downloads/Cowboy Bebop - 01.mkv",
        "Cowboy Bebop/Cowboy Bebop - 02.mkv",
    ):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(name.encode())
    add_folder(conn, root, now=NOW)
    scan = scanner(paths, web=internet(tmdb=False))

    scan.start()
    finished(scan)

    status = scan.status()
    assert (status.titles, status.mixed) == (2, 1)  # Downloads holds both


def test_no_scan_starts_or_resumes_while_kura_moves_files(
    paths: DataPaths, conn: sqlite3.Connection, anime: Path
):
    add_folder(conn, anime, now=NOW)
    with conn:
        conn.execute(
            "INSERT INTO scans (started_at, state, stage) VALUES (?, 'paused', 'reading')",
            (NOW.isoformat(),),
        )
    scan = scanner(paths)

    with scan.hold():
        with pytest.raises(ScanBusyError, match="Kura is moving files"):
            scan.start()
        with pytest.raises(ScanBusyError, match="Kura is moving files"):
            scan.resume()
        with pytest.raises(ScanBusyError, match="Kura is moving files"), scan.hold():
            pass

    scan.resume()
    finished(scan)
    assert scan.status().state == "done"


def test_files_never_move_while_a_scan_runs(
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

    with pytest.raises(ScanBusyError, match="A scan is running"), scan.hold():
        pass
    go_on.set()
    finished(scan)
