"""The conversion queue: files added in order, converted one at a time, paused, skipped,
reordered, tried again, put back, and settled after a crash."""

import json
import sqlite3
import threading
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from kura import changes
from kura.changes import changes_of
from kura.config import DataPaths
from kura.convert import WORKING, ConvertError, Programs
from kura.core.standard import Method
from kura.queue import Queue
from kura.scan import ScanBusyError, Scanner
from kura.tools import Tools
from tests.converting import BEST_TAG, programs, report
from tests.shelf import NOW, library

pytestmark = pytest.mark.usefixtures("quarantine")

RESULT = report(1440, 1080, tag=BEST_TAG)


@pytest.fixture
def shows(conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Three SD episodes of Trigun, read: tiny pictures (8x6), so the stand-in's frames are too."""
    root = tmp_path / "Anime"
    names = [f"Trigun (1998)/Season 01/Trigun (1998) - S01E0{n}.mkv" for n in (1, 2, 3)]
    library(conn, root, names)
    monkeypatch.setenv("KURA_FAKE_SIZE", "8x6")
    with conn:
        conn.execute("UPDATE files SET probe = ?", (json.dumps(report(8, 6, codec="h264")),))
        conn.execute(
            "INSERT INTO titles (id, kind, name, year) VALUES (1, 'series', 'Trigun', 1998)"
        )
        conn.execute("UPDATE files SET title_id = 1, season = 1, episode = id, matched = 'sure'")
    return root / "Trigun (1998)" / "Season 01"


def make_queue(
    paths: DataPaths, kit: Programs | None = None, scanner: Scanner | None = None
) -> Queue:
    clock = iter(range(1, 10_000))
    return Queue(
        paths,
        scanner or Scanner(paths, Tools(paths, items=())),
        lambda: kit,
        now=lambda: NOW + timedelta(seconds=next(clock)),
    )


@pytest.fixture
def queue(paths: DataPaths, shows: Path) -> Iterator[Queue]:
    worker = make_queue(paths, programs(RESULT))
    yield worker
    worker.stop()


def states(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    return [tuple(row) for row in conn.execute("SELECT file_id, state FROM jobs ORDER BY id")]


def test_files_join_in_order_and_once(queue: Queue, conn: sqlite3.Connection):
    assert queue.add([2, 1, 2]) == 2
    assert queue.add([1, 3]) == 1  # 1 is waiting already

    assert [job.file_id for job in queue.status().queued] == [2, 1, 3]
    assert {job.method for job in queue.status().queued} == {Method.BEST}


def test_a_lighter_method_is_kept_and_a_heavier_one_never_given(
    queue: Queue, conn: sqlite3.Connection
):
    with conn:
        conn.execute(
            "UPDATE files SET probe = ? WHERE id = 3",
            (json.dumps(report(1280, 720, codec="h264")),),
        )

    queue.add([1], Method.REENCODE)
    queue.add([3], Method.BEST)  # 720p: the fast upscale is the most it gets

    assert [job.method for job in queue.status().queued] == [Method.REENCODE, Method.FAST]


def test_files_with_nothing_to_convert_are_passed_over(queue: Queue, conn: sqlite3.Connection):
    with conn:
        at_standard = report(1440, 1080)
        conn.execute("UPDATE files SET probe = ? WHERE id = 1", (json.dumps(at_standard),))
        conn.execute("UPDATE files SET problem = 'damaged' WHERE id = 2")

    assert queue.add([1, 2, 3]) == 1


def test_the_first_file_waiting_is_converted_and_listed_today(
    queue: Queue, conn: sqlite3.Connection, shows: Path
):
    queue.add([1, 2])

    assert queue.work_once() is True

    assert states(conn) == [(1, "done"), (2, "queued")]
    assert (shows / "Trigun (1998) - S01E01.mkv").read_text().startswith("converted")
    status = queue.status()
    assert [job.label for job in status.today] == ["Trigun · S01E01"]
    assert status.today[0].output_size is not None
    assert [job.label for job in status.queued] == ["Trigun · S01E02"]
    assert status.gpu_seconds > 0


def test_a_file_that_fails_says_why_and_can_be_tried_again(
    queue: Queue, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    queue.add([1, 2])
    monkeypatch.setenv("KURA_FAKE_FAIL", "encode")

    queue.work_once()

    [failed] = queue.status().today
    assert (failed.state, failed.problem) == (
        "failed",
        "ffmpeg couldn't encode it: hevc_nvenc: No capable devices found.",
    )
    queue.retry(failed.id)
    assert [job.file_id for job in queue.status().queued] == [2, 1]  # back in line, last


def test_a_paused_queue_converts_nothing_until_resumed(
    queue: Queue, paths: DataPaths, conn: sqlite3.Connection
):
    queue.add([1])
    queue.pause()

    assert queue.work_once() is False
    assert queue.status().paused is True
    assert make_queue(paths).status().paused is True  # it stays paused, after a restart too

    queue.resume()
    assert queue.work_once() is True


def converting(queue: Queue, monkeypatch: pytest.MonkeyPatch) -> threading.Thread:
    """Starts the first file converting slowly, and waits until its frames are flowing."""
    monkeypatch.setenv("KURA_FAKE_SLOW", "1")
    worker = threading.Thread(target=queue.work_once)
    worker.start()
    for _ in range(200):
        running = queue.status().running
        if running is not None and running.stage == "converting":
            return worker
        threading.Event().wait(0.05)
    pytest.fail("The file never started converting")


def test_pausing_stops_the_file_and_puts_it_first_in_line(
    queue: Queue, conn: sqlite3.Connection, shows: Path, monkeypatch: pytest.MonkeyPatch
):
    original = (shows / "Trigun (1998) - S01E01.mkv").read_bytes()
    queue.add([1, 2])
    worker = converting(queue, monkeypatch)

    queue.pause()
    worker.join(timeout=20)

    assert states(conn) == [(1, "queued"), (2, "queued")]
    assert [job.file_id for job in queue.status().queued] == [1, 2]
    assert (shows / "Trigun (1998) - S01E01.mkv").read_bytes() == original
    assert not list(shows.glob(f"*{WORKING}"))


def test_skipping_the_file_converting_goes_on_to_the_next(
    queue: Queue, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    queue.add([1, 2])
    worker = converting(queue, monkeypatch)
    running = queue.status().running
    assert running is not None

    queue.skip(running.job.id)
    worker.join(timeout=20)

    assert states(conn) == [(1, "skipped"), (2, "queued")]


def test_files_waiting_can_be_skipped_moved_and_removed(queue: Queue, conn: sqlite3.Connection):
    queue.add([1, 2, 3])
    first, second, third = (job.id for job in queue.status().queued)

    queue.move(third, before=first)
    assert [job.file_id for job in queue.status().queued] == [3, 1, 2]
    queue.move(third, before=None)
    assert [job.file_id for job in queue.status().queued] == [1, 2, 3]

    queue.skip(second)
    queue.remove(third)

    assert states(conn) == [(1, "queued"), (2, "skipped")]
    with pytest.raises(LookupError):
        queue.remove(second)


def test_without_ffmpeg_files_wait_and_the_queue_says_why(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection
):
    queue = make_queue(paths, None)
    queue.add([1])

    assert queue.work_once() is False

    assert queue.status().problem == (
        "Kura needs ffmpeg to convert. It's downloaded on the setup's Tools step."
    )
    assert states(conn) == [(1, "queued")]


def test_putting_back_an_original_waits_for_no_scan(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection
):
    scanner = Scanner(paths, Tools(paths, items=()))
    queue = make_queue(paths, programs(RESULT), scanner)
    queue.add([1])
    queue.work_once()
    [done] = queue.status().today

    with scanner.hold(), pytest.raises(ScanBusyError):
        queue.restore(done.id)

    queue.restore(done.id)

    assert states(conn) == [(1, "restored")]
    with pytest.raises(ConvertError):
        queue.restore(done.id)


def test_after_a_crash_a_file_converting_waits_again_and_its_result_goes(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection
):
    queue = make_queue(paths, programs(RESULT))
    queue.add([1])
    with conn:
        conn.execute("UPDATE jobs SET state = 'running'")
    unfinished = shows / f"Trigun (1998) - S01E01{WORKING}"
    unfinished.write_bytes(b"half made")

    queue.recover()

    assert states(conn) == [(1, "queued")]
    assert not unfinished.exists()


def test_after_a_crash_a_result_half_in_place_is_finished(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    queue = make_queue(paths, programs(RESULT))
    queue.add([1])
    episode = shows / "Trigun (1998) - S01E01.mkv"
    renames = 0
    rename = Path.rename

    def stop_at_the_second(path: Path, target: Path) -> Path:
        nonlocal renames
        renames += 1
        if renames == 2:
            raise KeyboardInterrupt  # the engine stopping between the original and the result
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", stop_at_the_second)
    with pytest.raises(KeyboardInterrupt):
        queue.work_once()
    monkeypatch.undo()
    assert states(conn) == [(1, "replacing")]
    assert not episode.exists()  # the original set aside, the result not in place yet

    changes.recover(conn)  # at the next start, as the engine does
    queue.recover()

    assert states(conn) == [(1, "done")]
    assert episode.read_text().startswith("converted")
    plan = conn.execute("SELECT plan_id FROM jobs").fetchone()[0]
    assert [c.state.value for c in changes_of(conn, plan)] == ["done", "done"]


def test_on_nights_only_files_start_between_23_and_7(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection
):
    at = [NOW.replace(hour=12)]
    queue = Queue(
        paths, Scanner(paths, Tools(paths, items=())), lambda: programs(RESULT), now=lambda: at[0]
    )
    queue.add([1])
    queue.plan("nights")

    assert queue.work_once() is False
    assert (queue.status().schedule, queue.status().waits_for_night) == ("nights", True)

    at[0] = NOW.replace(hour=23, minute=30)
    assert queue.work_once() is True
    assert queue.status().waits_for_night is False


def test_a_file_on_a_drive_that_isnt_connected_waits_and_the_next_goes(
    queue: Queue, conn: sqlite3.Connection
):
    with conn:  # the first file's library folder is on a drive that's unplugged now
        conn.execute("INSERT INTO folders (path, added_at) VALUES ('Z:\\Anime', 'now')")
        conn.execute(
            "UPDATE files SET folder_id = 2, path = 'Z:\\Anime\\Trigun - 01.mkv' WHERE id = 1"
        )
    queue.add([1, 2])

    assert queue.work_once() is True

    assert states(conn) == [(1, "queued"), (2, "done")]
    [waiting] = queue.status().queued
    assert (waiting.file_id, waiting.drive_missing) == (1, True)
    assert queue.work_once() is False  # nothing else it can take


def test_a_full_drive_pauses_the_queue_and_says_so(
    queue: Queue, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    queue.add([1, 2])

    def full(path: object) -> SimpleNamespace:
        return SimpleNamespace(total=10**12, used=10**12 - 10**6, free=10**6)  # a megabyte left

    monkeypatch.setattr("kura.convert.shutil.disk_usage", full)

    assert queue.work_once() is True

    status = queue.status()
    assert states(conn) == [(1, "queued"), (2, "queued")]
    assert [job.file_id for job in status.queued] == [1, 2]  # still first in line
    assert status.paused is True
    assert status.problem is not None
    assert status.problem.startswith("There isn't room on")
