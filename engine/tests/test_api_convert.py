"""Converting through the API: what can be converted and what it takes, and the queue."""

import json
import sqlite3
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kura.api import create_app
from kura.backups import ask_to_restore, back_up
from kura.config import DataPaths
from kura.core.standard import Method
from kura.queue import Queue
from kura.recovery import Recovery, asked_to_stop
from kura.scan import Scanner
from tests.conftest import TOKEN
from tests.converting import BEST_TAG, open_elsewhere, programs, report
from tests.shelf import NOW, library

pytestmark = pytest.mark.usefixtures("quarantine")

SD_PROBE = json.dumps(report(8, 6, codec="h264"))


@pytest.fixture
def shelf(conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Trigun: two SD episodes, one that won't play, and one at the standard already."""
    root = tmp_path / "Anime"
    names = [f"Trigun (1998)/Season 01/Trigun (1998) - S01E0{n}.mkv" for n in (1, 2, 3, 4)]
    library(conn, root, names)
    monkeypatch.setenv("KURA_FAKE_SIZE", "8x6")
    with conn:
        conn.execute("UPDATE files SET probe = ?", (json.dumps(report(8, 6, codec="h264")),))
        conn.execute("UPDATE files SET problem = 'damaged' WHERE id = 3")
        conn.execute("UPDATE files SET probe = ? WHERE id = 4", (json.dumps(report(1440, 1080)),))
        conn.execute("INSERT INTO titles (id, kind, name) VALUES (1, 'series', 'Trigun')")
        conn.execute("UPDATE files SET title_id = 1, season = 1, episode = id, matched = 'sure'")
    return root


def free_space(monkeypatch: pytest.MonkeyPatch, free: int) -> None:
    """Every drive has `free` bytes free."""

    def usage(path: object) -> SimpleNamespace:
        return SimpleNamespace(total=10**13, used=10**13 - free, free=free)

    monkeypatch.setattr("kura.convert.shutil.disk_usage", usage)


@pytest.fixture
def converting(client: TestClient, paths: DataPaths, shelf: Path) -> Queue:
    """The engine's queue, converting with stand-ins for ffmpeg and the AI model."""
    app = cast("FastAPI", client.app)
    queue = Queue(
        paths,
        app.state.scanner,
        lambda: programs(report(1440, 1080, tag=BEST_TAG)),
        now=lambda: NOW,
    )
    app.state.queue = queue
    return queue


def test_what_isnt_at_the_standard_is_listed_with_each_way_to_convert_it(
    client: TestClient, shelf: Path, conn: sqlite3.Connection
):
    with conn:  # DVD-sized pictures, as the estimates were measured on
        sd = json.dumps(report(720, 540, codec="h264"))
        conn.execute("UPDATE files SET probe = ? WHERE id < 4", (sd,))

    found = client.get("/convert").json()

    assert found["standard"] == "Cinema 1080p"
    assert [(f["label"], f["broken"]) for f in found["files"]] == [
        ("Trigun · S01E01", False),
        ("Trigun · S01E02", False),
        ("Trigun · S01E03", True),
    ]
    first = found["files"][0]
    assert (first["height"], first["aspect"], first["drive"]) == (540, "4:3", shelf.drive)
    ways = first["ways"]
    assert [ways[way]["method"] for way in ("best", "fast", "reencode")] == [
        "best",
        "fast",
        "reencode",
    ]
    assert ways["best"]["gpuSeconds"] > ways["fast"]["gpuSeconds"] > ways["reencode"]["gpuSeconds"]
    assert first["outputBytes"] == 450_000_000
    assert found["files"][2]["ways"] == {}
    assert found["free"][shelf.drive] > 0
    assert found["setAside"] == {}  # nothing in quarantine to empty


def test_files_join_the_queue_and_wait_their_turn(client: TestClient, shelf: Path):
    added = client.post("/queue", json={"files": [2, 1, 3, 4], "method": "fast"}).json()

    status = client.get("/queue").json()

    assert added == {"added": 2}  # a broken file and one at the standard aren't
    assert [(job["label"], job["method"]) for job in status["queued"]] == [
        ("Trigun · S01E02", "fast"),
        ("Trigun · S01E01", "fast"),
    ]
    assert (status["queued"][0]["width"], status["queued"][0]["height"]) == (1440, 1080)
    assert status["gpuSeconds"] == sum(job["gpuSeconds"] for job in status["queued"])
    assert (status["running"], status["gpu"], status["paused"]) == (None, None, False)
    assert [f["waiting"] for f in client.get("/convert").json()["files"]] == [True, True, False]


def test_the_queue_pauses_resumes_and_waits_for_night(client: TestClient, shelf: Path):
    assert client.post("/queue/pause").json()["paused"] is True
    assert client.post("/queue/resume").json()["paused"] is False

    planned = client.put("/queue/schedule", json={"schedule": "nights"}).json()

    assert planned["schedule"] == "nights"
    client.post("/queue/pause")
    client.post("/queue", json={"files": [2], "when": "after"})
    assert client.get("/queue").json()["paused"] is True  # after the rest: it goes on as it was
    client.post("/queue", json={"files": [1], "when": "now"})
    status = client.get("/queue").json()
    assert (status["paused"], status["schedule"]) == (False, "now")  # start now, it said


def test_files_added_for_the_night_never_start_by_day(
    client: TestClient, shelf: Path, monkeypatch: pytest.MonkeyPatch
):
    schedules: list[str] = []
    add = Queue.add

    def noting(queue: Queue, file_ids: Iterable[int], method: Method | None = None) -> int:
        schedules.append(queue.status().schedule)
        return add(queue, file_ids, method)

    monkeypatch.setattr(Queue, "add", noting)
    client.post("/queue/pause")

    client.post("/queue", json={"files": [1], "when": "nights"})

    assert schedules == ["nights"]  # set before they joined: the worker never saw "now"
    status = client.get("/queue").json()
    assert (status["paused"], status["schedule"]) == (False, "nights")  # so it runs tonight


def test_waiting_files_can_be_moved_skipped_removed_and_tried_again(
    client: TestClient, shelf: Path
):
    client.post("/queue", json={"files": [1, 2]})
    first, second = (job["id"] for job in client.get("/queue").json()["queued"])

    assert client.post(f"/queue/{second}/move", json={"before": first}).status_code == 204
    assert [job["id"] for job in client.get("/queue").json()["queued"]] == [second, first]
    assert client.post(f"/queue/{second}/skip").status_code == 204
    assert client.post(f"/queue/{second}/retry").status_code == 204
    assert client.delete(f"/queue/{first}").status_code == 204

    assert [job["id"] for job in client.get("/queue").json()["queued"]] == [second]
    assert client.delete(f"/queue/{first}").status_code == 404
    assert client.post("/queue/99/skip").status_code == 404


def test_a_drive_without_room_pauses_the_queue_till_it_converts_what_fits(
    client: TestClient, converting: Queue, shelf: Path, monkeypatch: pytest.MonkeyPatch
):
    client.post("/queue", json={"files": [1, 2]})
    free_space(monkeypatch, 10**6)
    converting.work_once()

    room = client.get("/queue").json()["room"]
    assert (room["drive"], room["paused"], room["files"], room["fit"]) == (shelf.drive, True, 2, 0)
    assert (room["free"], room["setAside"]) == (10**6, 0)
    assert room["needed"] > room["free"]

    status = client.post("/queue/fit", json={"drive": shelf.drive}).json()

    assert status["paused"] is False
    assert status["room"]["paused"] is False  # they wait for room while the others go
    assert [job["noRoom"] for job in status["queued"]] == [True, True]


def test_files_queued_to_convert_what_fits_wait_for_room_without_pausing(
    client: TestClient, converting: Queue, shelf: Path, monkeypatch: pytest.MonkeyPatch
):
    free_space(monkeypatch, 10**6)

    client.post("/queue", json={"files": [1, 2], "when": "now", "fit": [shelf.drive]})

    assert converting.work_once() is False
    status = client.get("/queue").json()
    assert status["paused"] is False
    assert [job["noRoom"] for job in status["queued"]] == [True, True]


def test_a_drives_quarantine_can_be_emptied_to_make_room(
    client: TestClient, converting: Queue, shelf: Path
):
    episode = shelf / "Trigun (1998)" / "Season 01" / "Trigun (1998) - S01E01.mkv"
    original = episode.stat().st_size
    client.post("/queue", json={"files": [1]})
    converting.work_once()  # its original is set aside
    assert client.get("/convert").json()["setAside"] == {shelf.drive: original}

    emptied = client.post("/quarantine/empty", json={"drive": shelf.drive})

    assert emptied.json() == {"files": 1}
    assert client.get("/convert").json()["setAside"] == {}
    [done] = client.get("/queue").json()["today"]
    again = client.post(f"/queue/{done['id']}/restore")
    assert (
        again.json()["detail"]
        == "Its original was cleared out of quarantine, so it can't come back."
    )


def test_a_file_open_in_another_app_waits_and_can_be_tried_now(
    client: TestClient, converting: Queue, shelf: Path, monkeypatch: pytest.MonkeyPatch
):
    open_in_player = open_elsewhere(monkeypatch)
    client.post("/queue", json={"files": [1]})
    converting.work_once()

    [waiting] = client.get("/queue").json()["queued"]
    assert waiting["retryAt"] == "2026-10-11T09:35:00+00:00"  # in 5 minutes
    assert waiting["problem"].startswith("Trigun · S01E01 is open in another app")
    assert waiting["gpuSeconds"] == 0

    open_in_player[0] = False
    assert client.post(f"/queue/{waiting['id']}/retry").status_code == 204
    converting.try_waiting()

    [done] = client.get("/queue").json()["today"]
    assert (done["state"], done["retryAt"]) == ("done", None)


def test_a_failed_file_can_be_marked_broken(
    client: TestClient, converting: Queue, monkeypatch: pytest.MonkeyPatch
):
    client.post("/queue", json={"files": [1]})
    monkeypatch.setenv("KURA_FAKE_FAIL", "encode")
    converting.work_once()
    [failed] = client.get("/queue").json()["today"]
    assert "hevc_nvenc" in failed["log"]

    assert client.post(f"/queue/{failed['id']}/broken").status_code == 204

    assert client.post(f"/queue/{failed['id']}/broken").status_code == 404
    assert client.get("/queue").json()["today"][0]["state"] == "skipped"


def test_a_converted_file_is_listed_today_and_its_original_can_come_back(
    client: TestClient, converting: Queue, shelf: Path
):
    client.post("/queue", json={"files": [1]})

    converting.work_once()

    [done] = client.get("/queue").json()["today"]
    assert (done["label"], done["state"]) == ("Trigun · S01E01", "done")
    assert client.post(f"/queue/{done['id']}/restore").status_code == 204
    again = client.post(f"/queue/{done['id']}/restore")
    assert again.status_code == 422
    assert again.json()["detail"] == "Kura has no converted file to put back for that."


def test_history_lists_a_conversion_and_undoing_it_puts_the_original_back(
    client: TestClient, converting: Queue, shelf: Path
):
    episode = shelf / "Trigun (1998)" / "Season 01" / "Trigun (1998) - S01E01.mkv"
    original = episode.read_bytes()
    client.post("/queue", json={"files": [1]})
    converting.work_once()

    [plan] = client.get("/history").json()["plans"]

    assert (plan["kind"], plan["title"]) == ("convert", "Converted Trigun · S01E01")
    made = plan["conversion"]
    assert (made["method"], made["restored"]) == ("best", False)
    assert made["before"] == {"height": 6, "codec": "h264", "size": len(original)}
    assert (made["after"]["height"], made["after"]["codec"]) == (1080, "hevc")

    answer = client.post(f"/plans/{plan['id']}/undo")

    assert answer.status_code == 200
    assert episode.read_bytes() == original
    [plan] = client.get("/history").json()["plans"]
    assert plan["conversion"]["restored"] is True


def test_a_frame_is_shown_before_and_after_converting(
    client: TestClient, shelf: Path, monkeypatch: pytest.MonkeyPatch
):
    app = cast("FastAPI", client.app)
    app.state.programs = lambda: programs({})

    before = client.get("/convert/1/preview/before", params={"point": 0})
    after = client.get("/convert/1/preview/after", params={"way": "best", "point": 0})

    assert (before.status_code, before.headers["content-type"]) == (200, "image/png")
    assert after.content.startswith(b"converted ")  # the AI model's frame, as a picture
    assert client.get("/convert/99/preview/before").status_code == 404


def test_without_ffmpeg_there_is_nothing_to_compare(client: TestClient, shelf: Path):
    answer = client.get("/convert/1/preview/before")

    assert answer.status_code == 503
    assert answer.json()["detail"].startswith("Kura needs ffmpeg")


def test_at_start_a_conversion_a_crash_stopped_is_settled_before_any_scan(
    paths: DataPaths, monkeypatch: pytest.MonkeyPatch
):
    order: list[str] = []

    class Scans:
        """A scanner that only notes when the startup scan is asked for."""

        def recover(self) -> None:
            order.append("scan")

        @contextmanager
        def hold(self) -> Generator[None]:
            yield

    def settled(_queue: Queue) -> Recovery:
        order.append("queue")
        return Recovery()

    monkeypatch.setattr(Queue, "recover", settled)
    app = create_app(TOKEN, paths, scanner=cast("Scanner", Scans()), work=True)

    with TestClient(app, base_url="http://127.0.0.1"):
        pass

    assert order == ["queue", "scan"]  # files settle in place before a scan looks at them


def test_after_a_crash_kura_says_what_it_settled_till_its_seen(
    paths: DataPaths, conn: sqlite3.Connection, shelf: Path
):
    with conn:  # Kura closed unexpectedly while a file converted
        conn.execute(
            "INSERT INTO jobs (file_id, method, position, state, added_at)"
            " VALUES (1, 'best', 1, 'running', 'then')"
        )
    app = create_app(TOKEN, paths, work=True)
    headers = {"Authorization": f"Bearer {TOKEN}"}

    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        found = client.get("/recovery").json()
        assert (found["restarted"], found["finished"], found["putBack"]) == (1, 0, 0)
        assert client.post("/recovery/seen").status_code == 204
        assert client.get("/recovery").json() is None


def test_after_a_stop_kura_was_asked_for_no_crash_is_told(
    paths: DataPaths, conn: sqlite3.Connection, shelf: Path
):
    with conn:  # the app ended the engine while a file converted, before it could stop
        conn.execute(
            "INSERT INTO jobs (file_id, method, position, state, added_at)"
            " VALUES (1, 'best', 1, 'running', 'then')"
        )
    asked_to_stop(paths)
    app = create_app(TOKEN, paths, work=True)
    headers = {"Authorization": f"Bearer {TOKEN}"}

    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        assert client.get("/recovery").json() is None
        assert [job["fileId"] for job in client.get("/queue").json()["queued"]] == [1]


def test_restoring_a_backup_made_mid_conversion_tells_of_no_crash(
    paths: DataPaths, conn: sqlite3.Connection, shelf: Path
):
    with conn:  # tonight's backup, made while a file converted
        conn.execute(
            "INSERT INTO jobs (file_id, method, position, state, added_at)"
            " VALUES (1, 'best', 1, 'running', 'then')"
        )
    made = back_up(paths, NOW)
    with conn:
        conn.execute("UPDATE jobs SET state = 'done'")
    ask_to_restore(paths, made.name)
    app = create_app(TOKEN, paths, work=True)
    headers = {"Authorization": f"Bearer {TOKEN}"}

    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        assert client.get("/recovery").json() is None


def test_a_record_left_at_the_results_name_gives_way(
    client: TestClient, converting: Queue, conn: sqlite3.Connection, tmp_path: Path
):
    root = tmp_path / "Anime"
    library(conn, root, ["Old/Ep01.mp4"])
    with conn:  # a file once at the result's name, gone since
        conn.execute("UPDATE files SET probe = ? WHERE path LIKE '%Ep01.mp4'", (SD_PROBE,))
        conn.execute(
            """INSERT INTO files (folder_id, path, size, modified, found_at, seen_at, gone_at)
               VALUES (1, ?, 1, 0, 'then', 'then', 'then')""",
            (str(root / "Old" / "Ep01.mkv"),),
        )
    mp4 = conn.execute("SELECT id FROM files WHERE path LIKE '%Ep01.mp4'").fetchone()[0]
    client.post("/queue", json={"files": [mp4]})

    converting.work_once()

    [done] = client.get("/queue").json()["today"]
    assert (done["state"], done["problem"]) == ("done", None)
    paths_now = [row[0] for row in conn.execute("SELECT path FROM files WHERE gone_at IS NULL")]
    assert str(root / "Old" / "Ep01.mkv") in paths_now
