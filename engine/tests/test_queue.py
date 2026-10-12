"""The conversion queue: files added in order, converted one at a time, paused, skipped,
reordered, tried again, put back, and settled after a crash."""

import json
import sqlite3
import subprocess
import threading
from collections.abc import Callable, Iterator, Sequence
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from kura import changes
from kura.changes import changes_of, save_plan
from kura.config import DataPaths
from kura.convert import WORKING, ConvertError, Programs, room_for, work_of
from kura.convert import room_for as converting_reckons
from kura.core.fields import Json
from kura.core.media import media_from_ffprobe
from kura.core.plan import Change, ChangeKind, Plan
from kura.core.standard import Method, decide
from kura.history import plans
from kura.preferences import library_standard
from kura.queue import Queue, Room
from kura.scan import ScanBusyError, Scanner
from kura.tools import Tools
from tests.converting import BEST_TAG, open_elsewhere, programs, report
from tests.fake_web import FakeWeb
from tests.shelf import NOW, library

type Told = tuple[str, str, str | None]  # a notification: its title, its line, where it leads

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
    paths: DataPaths,
    kit: Programs | None = None,
    scanner: Scanner | None = None,
    told: list[Told] | None = None,
) -> Queue:
    """A queue on the test's data; what it tells the app (a notification: a title, a line and
    where in Kura it leads) goes into `told`."""
    clock = iter(range(1, 10_000))
    heard = told if told is not None else []
    return Queue(
        paths,
        scanner or Scanner(paths, Tools(paths, items=())),
        lambda: kit,
        now=lambda: NOW + timedelta(seconds=next(clock)),
        notify=lambda title, body, link=None: heard.append((title, body, link)),
    )


@pytest.fixture
def queue(paths: DataPaths, shows: Path) -> Iterator[Queue]:
    worker = make_queue(paths, programs(RESULT))
    yield worker
    worker.stop()


def states(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    return [tuple(row) for row in conn.execute("SELECT file_id, state FROM jobs ORDER BY id")]


def free_space(monkeypatch: pytest.MonkeyPatch, free: int) -> None:
    """Every drive has `free` bytes free."""

    def usage(path: object) -> SimpleNamespace:
        return SimpleNamespace(total=10**13, used=10**13 - free, free=free)

    monkeypatch.setattr("kura.convert.shutil.disk_usage", usage)


def room_of(conn: sqlite3.Connection, file_id: int) -> int:
    """The free space a file's result wants on its drive, as converting checks."""
    standard = library_standard(conn)
    row = conn.execute("SELECT probe FROM files WHERE id = ?", (file_id,)).fetchone()
    media = media_from_ffprobe(json.loads(row["probe"]))
    return room_for(media, decide(media, standard), standard)


def two_hours(made: Json) -> Json:
    """ffprobe's report on a file, playing two hours instead."""
    longer = json.loads(json.dumps(made))
    longer["format"]["duration"] = "7200.0"
    return longer


def a_film(conn: sqlite3.Connection, file_id: int) -> None:
    """The file plays two hours, so its result takes five episodes' room."""
    with conn:
        conn.execute(
            "UPDATE files SET probe = ? WHERE id = ?",
            (json.dumps(two_hours(report(8, 6, codec="h264"))), file_id),
        )


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


def test_a_failed_file_keeps_what_ffmpeg_said_and_can_be_marked_broken(
    queue: Queue, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    queue.add([1])
    monkeypatch.setenv("KURA_FAKE_FAIL", "encode")
    queue.work_once()
    [failed] = queue.status().today
    assert failed.log is not None
    assert "hevc_nvenc: No capable devices found" in failed.log

    queue.mark_broken(failed.id)

    assert states(conn) == [(1, "skipped")]
    file = conn.execute("SELECT problem FROM files WHERE id = 1").fetchone()
    assert file["problem"] == failed.problem
    assert queue.add([1]) == 0  # broken: it isn't converted again
    with pytest.raises(LookupError):
        queue.mark_broken(failed.id)  # only a file that failed


def test_a_file_marked_broken_stays_so_through_scans_till_it_changes(
    queue: Queue,
    paths: DataPaths,
    shows: Path,
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
):
    queue.add([1])
    monkeypatch.setenv("KURA_FAKE_FAIL", "encode")
    queue.work_once()
    [failed] = queue.status().today
    queue.mark_broken(failed.id)
    scanner = Scanner(
        paths,
        Tools(paths, items=()),
        read=lambda path: report(8, 6, codec="h264"),  # ffprobe reads it fine: it's the picture
        transport=FakeWeb(),
    )

    scanner.start()
    scanner.wait(30)
    assert conn.execute("SELECT problem FROM files WHERE id = 1").fetchone()[0] == failed.problem

    (shows / "Trigun (1998) - S01E01.mkv").write_bytes(b"a better copy, saved over it")
    scanner.start()
    scanner.wait(30)
    assert conn.execute("SELECT problem FROM files WHERE id = 1").fetchone()[0] is None


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


def owner_asks_while_checking(paths: DataPaths, ask: Callable[[Queue, int], None]) -> Queue:
    """A queue whose owner does `ask` (given the job's id) while a result is being checked."""
    queue: Queue | None = None

    def read(path: Path) -> Json:
        assert queue is not None
        running = queue.status().running
        assert running is not None
        assert running.stage == "checking"
        ask(queue, running.job.id)
        return RESULT

    queue = make_queue(paths, replace(programs(RESULT), read=read))
    return queue


def test_a_file_skipped_while_its_result_is_checked_isnt_put_in_place(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection
):
    episode = shows / "Trigun (1998) - S01E01.mkv"
    original = episode.read_bytes()
    queue = owner_asks_while_checking(paths, Queue.skip)
    queue.add([1, 2])

    queue.work_once()

    assert states(conn) == [(1, "skipped"), (2, "queued")]
    assert episode.read_bytes() == original
    assert not list(shows.glob(f"*{WORKING}"))


def test_a_file_paused_while_its_result_is_checked_still_goes_in(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection
):
    queue = owner_asks_while_checking(paths, lambda queue, _job: queue.pause())
    queue.add([1, 2])

    queue.work_once()

    assert states(conn) == [(1, "done"), (2, "queued")]  # it was made: only the next waits
    assert queue.status().paused is True
    assert queue.work_once() is False


def test_a_file_paused_while_it_waits_for_a_scan_goes_in_once_the_scan_is_done(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("kura.queue._HOLD_RETRY", 0.05)
    scanner = Scanner(paths, Tools(paths, items=()))
    queue = make_queue(paths, programs(RESULT), scanner)
    queue.add([1])
    with scanner.hold():  # a scan running as the result is ready to go in
        worker = threading.Thread(target=queue.work_once)
        worker.start()
        for _ in range(200):
            running = queue.status().running
            if running is not None and running.stage == "replacing":
                break
            threading.Event().wait(0.05)
        queue.pause()
        worker.join(timeout=0.3)
        assert worker.is_alive()  # waiting for the scan, paused or not
    worker.join(timeout=20)

    assert states(conn) == [(1, "done")]


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
    unfinished = work_of(shows / "Trigun (1998) - S01E01.mkv")
    unfinished.write_bytes(b"half made")

    settled = queue.recover()

    assert states(conn) == [(1, "queued")]
    assert not unfinished.exists()
    assert (settled.restarted, settled.finished, settled.put_back) == (1, 0, 0)


def test_at_start_a_copy_still_open_doesnt_keep_kura_from_starting(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    queue = make_queue(paths, programs(RESULT))
    queue.add([1])
    with conn:
        conn.execute("UPDATE jobs SET state = 'running'")

    def open_still(path: Path, missing_ok: bool = False) -> None:  # an ffmpeg a crash left
        raise PermissionError(13, "The process cannot access the file", str(path))

    monkeypatch.setattr(Path, "unlink", open_still)

    queue.recover()

    assert states(conn) == [(1, "queued")]


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
    settled = queue.recover()

    assert states(conn) == [(1, "done")]
    assert (settled.restarted, settled.finished, settled.put_back) == (0, 1, 0)
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


def test_stopping_at_three_takes_no_file_after_it_tonight_only(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection
):
    at = [
        (NOW + timedelta(days=1)).replace(hour=1, minute=0)
    ]  # 01:00, a night of the nights-only queue
    queue = Queue(
        paths, Scanner(paths, Tools(paths, items=())), lambda: programs(RESULT), now=lambda: at[0]
    )
    queue.add([1, 2, 3])
    queue.plan("nights")
    morning = at[0].replace(hour=7)
    assert (queue.status().ends_at, queue.status().early) == (morning.isoformat(), False)

    queue.stop_early(early=True)

    three = at[0].replace(hour=3)
    assert (queue.status().ends_at, queue.status().early) == (three.isoformat(), True)
    at[0] = three - timedelta(minutes=1)
    assert queue.work_once() is True  # one started before 03:00 goes, and finishes
    at[0] = three
    assert queue.work_once() is False  # none starts after
    assert queue.status().waits_for_night is True

    at[0] = three.replace(hour=23)  # the next night is a whole night again
    assert queue.status().ends_at == (morning + timedelta(days=1)).isoformat()
    assert queue.work_once() is True


def test_stopping_at_three_holds_though_the_clocks_change_that_night(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection
):
    summer, winter = timezone(timedelta(hours=2)), timezone(timedelta(hours=1))
    at = [datetime(2026, 10, 24, 23, 30, tzinfo=summer)]
    queue = Queue(
        paths, Scanner(paths, Tools(paths, items=())), lambda: programs(RESULT), now=lambda: at[0]
    )
    queue.add([1])
    queue.plan("nights")
    queue.stop_early(early=True)

    at[0] = datetime(2026, 10, 25, 2, 10, tzinfo=winter)  # the clocks went back at 03:00

    assert queue.status().early is True
    assert queue.work_once() is False  # 03:00 summer time has come and gone


def test_going_on_till_seven_undoes_stopping_early(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection
):
    at = [(NOW + timedelta(days=1)).replace(hour=2)]
    queue = Queue(
        paths, Scanner(paths, Tools(paths, items=())), lambda: programs(RESULT), now=lambda: at[0]
    )
    queue.add([1])
    queue.plan("nights")
    queue.stop_early(early=True)

    queue.stop_early(early=False)

    at[0] = at[0].replace(hour=4)
    assert (queue.status().early, queue.status().waits_for_night) == (False, False)
    assert queue.work_once() is True


def test_stopping_early_past_three_takes_no_file_after_the_one_converting(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection
):
    at = [(NOW + timedelta(days=1)).replace(hour=4, minute=10)]
    queue = Queue(
        paths, Scanner(paths, Tools(paths, items=())), lambda: programs(RESULT), now=lambda: at[0]
    )
    queue.add([1])
    queue.plan("nights")

    queue.stop_early(early=True)

    assert queue.status().ends_at == at[0].isoformat()
    assert queue.work_once() is False


def test_by_day_nothing_ends_tonight_yet(queue: Queue):
    queue.plan("nights")  # 09:30

    assert queue.status().ends_at is None


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


def test_a_full_drive_pauses_the_queue_and_says_what_it_needs(
    queue: Queue, conn: sqlite3.Connection, shows: Path, monkeypatch: pytest.MonkeyPatch
):
    queue.add([1, 2])
    free_space(monkeypatch, 10**6)  # a megabyte left

    assert queue.work_once() is True

    status = queue.status()
    assert states(conn) == [(1, "queued"), (2, "queued")]
    assert [job.file_id for job in status.queued] == [1, 2]  # still first in line
    assert status.paused is True
    assert status.problem is None  # the room it wants says it all
    assert status.room == Room(
        drive=shows.drive,
        paused=True,
        files=2,
        needed=room_of(conn, 1) + room_of(conn, 2),
        free=10**6,
        fit=0,
        set_aside=0,
    )

    queue.resume()  # the owner made room some other way

    assert queue.status().room is None


def test_converting_what_fits_passes_over_what_doesnt_and_goes_on(
    paths: DataPaths, conn: sqlite3.Connection, shows: Path, monkeypatch: pytest.MonkeyPatch
):
    def read(path: Path) -> Json:  # each result plays as long as its original
        return two_hours(RESULT) if "S01E01" in path.name else RESULT

    queue = make_queue(paths, replace(programs(RESULT), read=read))
    a_film(conn, 1)
    film, episode = room_of(conn, 1), room_of(conn, 2)
    original = (shows / "Trigun (1998) - S01E02.mkv").stat().st_size
    queue.add([1, 2])
    free_space(monkeypatch, episode)  # room for the episode, not the film
    queue.work_once()
    assert queue.status().room == Room(shows.drive, True, 2, film + episode, episode, 1, 0)

    queue.convert_what_fits(shows.drive)
    queue.resume()

    assert queue.work_once() is True  # the episode goes
    assert states(conn) == [(1, "queued"), (2, "done")]
    status = queue.status()
    assert status.paused is False
    assert [(job.file_id, job.no_room) for job in status.queued] == [(1, True)]
    # Its original is in quarantine now: emptying it would make room too.
    assert status.room == Room(shows.drive, False, 1, film, episode, 0, original)

    assert queue.work_once() is False  # the film waits for room; the queue doesn't pause
    assert queue.status().paused is False

    free_space(monkeypatch, 10**12)
    assert queue.work_once() is True  # room at last
    assert states(conn) == [(1, "done"), (2, "done")]
    assert queue.status().room is None


def test_files_added_to_convert_what_fits_wait_for_room_without_pausing(
    queue: Queue, conn: sqlite3.Connection, shows: Path, monkeypatch: pytest.MonkeyPatch
):
    free_space(monkeypatch, 10**6)
    queue.work_once()  # the worker looks as the owner adds them: nothing waits yet

    queue.add([1, 2], fit=[shows.drive])

    assert queue.work_once() is False
    status = queue.status()
    assert status.paused is False
    assert [job.no_room for job in status.queued] == [True, True]


def test_paused_by_the_owner_files_waiting_for_room_say_nothing_of_it(
    queue: Queue, conn: sqlite3.Connection, shows: Path, monkeypatch: pytest.MonkeyPatch
):
    free_space(monkeypatch, 10**6)
    queue.add([1], fit=[shows.drive])

    queue.pause()

    status = queue.status()
    assert status.room is None  # the queue is paused: that's what it says
    assert [job.no_room for job in status.queued] == [False]


def mounted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The library folder is a full volume mounted into a drive that has plenty of room."""

    def usage(path: object) -> SimpleNamespace:
        free = 10**12 if str(path).rstrip("\\").endswith(":") else 10**6
        return SimpleNamespace(total=10**13, used=10**13 - free, free=free)

    monkeypatch.setattr("kura.convert.shutil.disk_usage", usage)


def test_room_is_measured_where_the_file_is_as_converting_measures_it(
    queue: Queue, conn: sqlite3.Connection, shows: Path, monkeypatch: pytest.MonkeyPatch
):
    mounted(monkeypatch)
    queue.add([1], fit=[shows.drive])

    assert queue.work_once() is False  # it waits for room, rather than failing to start
    status = queue.status()  # and says so
    assert status.room is not None
    assert status.room.free == 10**6
    assert [job.no_room for job in status.queued] == [True]


def test_a_mounted_volume_without_room_pauses_the_queue_and_says_why(
    queue: Queue, conn: sqlite3.Connection, shows: Path, monkeypatch: pytest.MonkeyPatch
):
    mounted(monkeypatch)
    queue.add([1])

    queue.work_once()

    status = queue.status()
    assert status.paused is True
    assert status.room is not None  # the card, with its ways on
    assert (status.room.paused, status.room.free) == (True, 10**6)


def test_what_a_removed_file_wanted_is_forgotten_though_its_number_comes_again(
    queue: Queue, conn: sqlite3.Connection, shows: Path, monkeypatch: pytest.MonkeyPatch
):
    free_space(monkeypatch, 10**9)  # room for an episode, not a film
    a_film(conn, 1)
    queue.add([1], fit=[shows.drive])

    def reckoned(*_: object) -> int:  # the queue reckons the film fits
        return 1

    monkeypatch.setattr("kura.queue.room_for", reckoned)
    queue.work_once()  # converting finds it doesn't
    monkeypatch.setattr("kura.queue.room_for", converting_reckons)
    [film] = queue.status().queued
    queue.remove(film.id)

    queue.add([2], fit=[shows.drive])  # an episode, which SQLite numbers as the film was

    [episode] = queue.status().queued
    assert episode.id == film.id
    assert queue.work_once() is True  # what the film wanted isn't held against it


def test_a_file_converting_finds_without_room_waits_rather_than_starting_again_and_again(
    queue: Queue, conn: sqlite3.Connection, shows: Path, monkeypatch: pytest.MonkeyPatch
):
    """Converting can want more room than the queue reckoned (a picture found interlaced is
    made anew, not copied): the file then waits for that much room."""
    free_space(monkeypatch, 10**6)
    queue.add([1], fit=[shows.drive])

    def reckoned(*_: object) -> int:  # the queue reckons it fits
        return 1

    monkeypatch.setattr("kura.queue.room_for", reckoned)

    assert queue.work_once() is True  # taken, and converting finds no room
    assert queue.work_once() is False  # it waits for room, not taken again at once
    status = queue.status()
    assert status.paused is False
    assert [job.no_room for job in status.queued] == [True]


def test_by_day_on_nights_only_files_waiting_for_room_wait_for_the_night_first(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    queue = make_queue(paths, programs(RESULT))
    free_space(monkeypatch, 10**6)
    queue.plan("nights")  # 09:30
    queue.add([1], fit=[shows.drive])

    status = queue.status()

    assert status.waits_for_night is True
    assert status.room is None  # the night comes first: that's what the queue says
    assert [job.no_room for job in status.queued] == [False]


def test_once_nothing_waits_for_room_a_full_drive_pauses_the_queue_again(
    queue: Queue, conn: sqlite3.Connection, shows: Path, monkeypatch: pytest.MonkeyPatch
):
    queue.add([1])
    free_space(monkeypatch, 10**6)
    queue.work_once()
    queue.convert_what_fits(shows.drive)
    queue.resume()
    free_space(monkeypatch, 10**12)
    assert queue.work_once() is True
    assert queue.work_once() is False  # nothing waits on it: converting what fits is over

    queue.add([2])
    free_space(monkeypatch, 10**6)
    queue.work_once()

    status = queue.status()
    assert status.paused is True  # asked again
    assert status.room is not None
    assert status.room.paused is True


def test_once_nothing_waits_the_batch_is_told_of(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection
):
    told: list[Told] = []
    queue = make_queue(paths, programs(RESULT), told=told)
    queue.add([1, 2])

    queue.work_once()
    assert told == []  # one still waits
    queue.work_once()

    [(title, body, link)] = told
    assert title == "Trigun, season 1 is done"
    assert body.startswith("2 episodes · all checked · ")
    assert " → " in body
    assert link == "/titles/1"


def test_a_batch_with_a_failure_says_so(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    told: list[Told] = []
    queue = make_queue(paths, programs(RESULT), told=told)
    with conn:  # one from another show
        conn.execute("INSERT INTO titles (id, kind, name) VALUES (2, 'series', 'Cowboy Bebop')")
        conn.execute("UPDATE files SET title_id = 2 WHERE id = 2")
    queue.add([1, 2])
    queue.work_once()
    monkeypatch.setenv("KURA_FAKE_FAIL", "encode")

    queue.work_once()

    [(title, body, link)] = told
    assert title == "The queue is done"
    assert body.startswith("1 converted, 1 failed · ")
    assert link == "/history"


def test_a_full_drive_is_told_of(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    told: list[Told] = []
    queue = make_queue(paths, programs(RESULT), told=told)
    queue.add([1])

    free_space(monkeypatch, 10**6)

    queue.work_once()

    [(title, body, link)] = told
    assert title == "The queue paused"
    assert body == (
        f"There isn't room on {shows.drive} for the next file: it needs about 562 MB, and 1 MB"
        " is free."
    )
    assert link == "/convert/queue"


def test_a_file_open_in_another_app_waits_its_result_kept_and_goes_in_later(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    episode = shows / "Trigun (1998) - S01E01.mkv"
    open_in_player = open_elsewhere(monkeypatch, episode)
    commands: list[Sequence[str]] = []
    told: list[Told] = []
    queue = make_queue(paths, programs(RESULT, commands), told=told)
    queue.add([1, 2])
    kept = work_of(shows / "Trigun (1998) - S01E01.mkv")

    queue.work_once()  # made and checked, but the player has the original
    [waiting, _] = queue.status().queued
    assert waiting.file_id == 1
    assert waiting.problem == (
        "Trigun · S01E01 is open in another app, maybe your player. Kura will try again in 5 "
        "minutes."
    )
    assert waiting.retry_at is not None
    assert waiting.gpu_seconds == 0  # made already
    assert kept.is_file()  # the result, kept beside it

    queue.work_once()  # the next file goes meanwhile
    assert states(conn) == [(1, "queued"), (2, "done")]
    assert queue.work_once() is False  # the waiting one is never made again
    assert told == []  # one still waits

    open_in_player[0] = False
    assert queue.try_waiting() is False  # not due for 5 minutes
    queue.retry(waiting.id)  # Try now
    assert queue.try_waiting() is True

    assert states(conn) == [(1, "done"), (2, "done")]
    assert episode.read_text().startswith("converted")
    assert not kept.exists()
    made = [command for command in commands if command[-1] == str(kept)]
    assert len(made) == 1  # made once: the kept result went in
    [(title, _, _)] = told
    assert title == "Trigun, season 1 is done"


def test_history_times_a_result_that_waited_by_its_making(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    open_in_player = open_elsewhere(monkeypatch)
    at = [NOW]
    kit = programs(RESULT)

    def slowly(
        command: Sequence[str],
        *,
        stdin: int | None = None,
        stdout: int | None = None,
        stderr: int | None = None,
    ) -> subprocess.Popen[bytes]:  # each ffmpeg takes ten minutes, by the queue's clock
        at[0] += timedelta(minutes=10)
        return kit.start(command, stdin=stdin, stdout=stdout, stderr=stderr)

    scanner = Scanner(paths, Tools(paths, items=()))
    queue = Queue(paths, scanner, lambda: replace(kit, start=slowly), now=lambda: at[0])
    queue.add([1])
    queue.work_once()
    made = at[0]
    open_in_player[0] = False
    at[0] += timedelta(hours=2)  # the player let go two hours later

    queue.try_waiting()

    [plan] = plans(conn)
    assert plan.conversion is not None
    assert plan.conversion.seconds == (made - NOW).total_seconds()


def test_a_file_still_open_when_tried_again_waits_again(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    open_elsewhere(monkeypatch)
    queue = make_queue(paths, programs(RESULT))
    queue.add([1])
    queue.work_once()
    [waiting] = queue.status().queued

    queue.retry(waiting.id)
    queue.try_waiting()

    [still] = queue.status().queued
    assert still.retry_at is not None
    assert waiting.retry_at is not None
    assert still.retry_at > waiting.retry_at  # 5 minutes from this try
    assert still.problem == waiting.problem
    assert (work_of(shows / "Trigun (1998) - S01E01.mkv")).is_file()


def test_a_file_waiting_for_its_player_can_be_skipped_and_its_result_goes(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    open_elsewhere(monkeypatch)
    queue = make_queue(paths, programs(RESULT))
    queue.add([1, 2])
    queue.work_once()
    [first, second] = queue.status().queued

    queue.skip(first.id)
    assert states(conn) == [(1, "skipped"), (2, "queued")]
    assert not list(shows.glob(f"*{WORKING}"))

    queue.work_once()  # waits for its player too
    queue.remove(second.id)
    assert states(conn) == [(1, "skipped")]
    assert not list(shows.glob(f"*{WORKING}"))


def test_a_file_changed_while_its_result_waited_isnt_replaced(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    open_in_player = open_elsewhere(monkeypatch)
    queue = make_queue(paths, programs(RESULT))
    queue.add([1])
    queue.work_once()
    [waiting] = queue.status().queued
    episode = shows / "Trigun (1998) - S01E01.mkv"
    episode.write_bytes(b"a better copy, saved over it")
    with conn:  # and a scan read it since
        stat = episode.stat()
        conn.execute(
            "UPDATE files SET size = ?, modified = ? WHERE id = 1",
            (stat.st_size, stat.st_mtime_ns),
        )

    open_in_player[0] = False
    queue.retry(waiting.id)
    queue.try_waiting()

    [failed] = queue.status().today
    assert failed.state == "failed"
    assert failed.problem is not None
    assert failed.problem.startswith("It changed since Kura read it")
    assert episode.read_bytes() == b"a better copy, saved over it"
    assert not list(shows.glob(f"*{WORKING}"))


def test_after_a_crash_a_result_going_in_from_waiting_waits_again(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    open_elsewhere(monkeypatch)
    queue = make_queue(paths, programs(RESULT))
    queue.add([1])
    queue.work_once()
    with conn:  # the engine stopped as it began putting it in place
        conn.execute("UPDATE jobs SET state = 'replacing'")

    changes.recover(conn)
    queue.recover()

    [waiting] = queue.status().queued
    assert waiting.retry_at is not None
    assert (work_of(shows / "Trigun (1998) - S01E01.mkv")).is_file()


def test_after_a_crash_only_kuras_own_unfinished_result_is_removed(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection
):
    queue = make_queue(paths, programs(RESULT))
    queue.add([1])
    precious = shows / "thesis.docx"
    precious.write_text("years of work")
    episode = shows / "Trigun (1998) - S01E01.mkv"
    # A journal naming it as the result, as a damaged database or an imported one could hold.
    plan = Plan(
        (
            Change(ChangeKind.QUARANTINE, episode, shows / "aside" / episode.name, "x", "y"),
            Change(ChangeKind.MOVE, precious, episode, "x", "y"),
        )
    )
    plan_id = save_plan(conn, plan, "Converted x", now=NOW, kind="convert")
    with conn:
        conn.execute("UPDATE changes SET state = 'failed'")
        conn.execute("UPDATE jobs SET state = 'replacing', plan_id = ?", (plan_id,))

    queue.recover()

    assert precious.read_text() == "years of work"
    assert states(conn) == [(1, "queued")]


def test_after_a_crash_a_waiting_result_in_place_but_unread_waits_no_more(
    paths: DataPaths, shows: Path, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
):
    open_in_player = open_elsewhere(monkeypatch)
    queue = make_queue(paths, programs(RESULT))
    queue.add([1])
    queue.work_once()
    [waiting] = queue.status().queued
    open_in_player[0] = False
    queue.retry(waiting.id)

    def crash(*args: object, **kwargs: object) -> None:  # once both moves are made
        raise KeyboardInterrupt

    monkeypatch.setattr("kura.convert.finish", crash)
    with pytest.raises(KeyboardInterrupt):
        queue.try_waiting()
    monkeypatch.undo()

    make_queue(paths, None).recover()  # the next start, without ffprobe to read it

    job = conn.execute("SELECT state, retry_at FROM jobs").fetchone()
    assert (job["state"], job["retry_at"]) == ("done", None)


def test_a_file_converted_anew_is_timed_by_this_conversion(queue: Queue, conn: sqlite3.Connection):
    queue.add([1])
    with conn:  # left from an earlier try, its result put back since
        conn.execute("UPDATE jobs SET finished_at = '2020-01-01T00:00:00+00:00'")

    queue.work_once()

    [plan] = plans(conn)
    assert plan.conversion is not None
    assert plan.conversion.seconds is not None
    assert plan.conversion.seconds >= 0
