"""Converting through the API: what can be converted and what it takes, and the queue."""

import json
import sqlite3
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kura.config import DataPaths
from kura.queue import Queue
from tests.converting import BEST_TAG, programs, report
from tests.shelf import NOW, library

pytestmark = pytest.mark.usefixtures("quarantine")


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
    client.post("/queue", json={"files": [1], "start": True})
    status = client.get("/queue").json()
    assert (status["paused"], status["schedule"]) == (False, "now")  # start now, it said


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
