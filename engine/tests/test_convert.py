"""Converting one file on disk, with stand-ins for ffmpeg, ffprobe and the AI model."""

import json
import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

import pytest

from kura.convert import (
    WORKING,
    ConvertError,
    Programs,
    Progress,
    Stopped,
    convert,
    lighter,
    restore,
)
from kura.core.standard import CINEMA_1080, Method
from tests.converting import BEST_TAG, programs, report
from tests.shelf import NOW, library

pytestmark = pytest.mark.usefixtures("quarantine")


@pytest.fixture
def episode(conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An SD episode, read and waiting in the queue. Its picture is tiny (8x6), so the stand-in
    decoder's frames are too."""
    library(conn, tmp_path / "Anime", ["Trigun (1998)/Season 01/Trigun (1998) - S01E03.mkv"])
    monkeypatch.setenv("KURA_FAKE_SIZE", "8x6")
    with conn:
        conn.execute("UPDATE files SET probe = ?", (json.dumps(report(8, 6, codec="h264")),))
        conn.execute(
            "INSERT INTO jobs (file_id, method, position, added_at) VALUES (1, 'best', 1, ?)",
            (NOW.isoformat(),),
        )
    return tmp_path / "Anime" / "Trigun (1998)" / "Season 01" / "Trigun (1998) - S01E03.mkv"


def run(
    conn: sqlite3.Connection,
    kit: Programs,
    *,
    seen: list[Progress] | None = None,
    stop: Callable[[], bool] = lambda: False,
) -> None:
    heard = seen if seen is not None else []
    convert(conn, 1, kit, CINEMA_1080, now=lambda: NOW, report=heard.append, stop=stop)


def test_an_sd_episode_goes_through_the_ai_model_and_takes_its_originals_place(
    conn: sqlite3.Connection, episode: Path
):
    original = episode.read_bytes()
    seen: list[Progress] = []

    run(conn, programs(report(1440, 1080, tag=BEST_TAG)), seen=seen)

    assert episode.read_text() == f"converted {5 * 16 * 12 * 3 * 4} bytes of frames"  # doubled
    assert not list(episode.parent.glob(f"*{WORKING}"))
    stages = list(dict.fromkeys(progress.stage for progress in seen))
    assert stages == ["looking", "converting", "checking", "replacing"]
    file = conn.execute("SELECT path, probe, gone_at FROM files").fetchone()
    assert (Path(file["path"]), file["gone_at"]) == (episode, None)
    assert json.loads(file["probe"])["streams"][0]["height"] == 1080
    job = conn.execute("SELECT state, plan_id, source_size FROM jobs").fetchone()
    assert (job["state"], job["source_size"]) == ("done", len(original))
    kind = conn.execute("SELECT kind FROM plans WHERE id = ?", (job["plan_id"],)).fetchone()
    assert kind[0] == "convert"


def test_restoring_puts_the_original_back(conn: sqlite3.Connection, episode: Path):
    original = episode.read_bytes()
    run(conn, programs(report(1440, 1080, tag=BEST_TAG)))

    restore(conn, 1, now=NOW)

    assert episode.read_bytes() == original
    assert not list(episode.parent.glob(f"*{WORKING}"))
    file = conn.execute("SELECT path, probe FROM files").fetchone()
    assert Path(file["path"]) == episode
    assert json.loads(file["probe"])["streams"][0]["height"] == 6  # the original's
    assert conn.execute("SELECT state FROM jobs").fetchone()[0] == "restored"


def test_a_720p_episode_is_made_in_one_command(conn: sqlite3.Connection, episode: Path):
    with conn:
        conn.execute("UPDATE files SET probe = ?", (json.dumps(report(1280, 720, codec="h264")),))
        conn.execute("UPDATE jobs SET method = 'fast'")
    seen: list[Progress] = []
    commands: list[Sequence[str]] = []

    run(
        conn,
        programs(report(1920, 1080, tag="fast to 1080p · Kura 0.1.0"), commands),
        seen=seen,
    )

    assert episode.read_bytes().startswith(b"converted ")
    assert [p.frames for p in seen if p.stage == "converting"] == [10, 20, 30, 30]
    assert any("libplacebo" in part for command in commands for part in command)


def test_a_failed_encode_leaves_the_original_as_it_was(
    conn: sqlite3.Connection, episode: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KURA_FAKE_FAIL", "encode")
    original = episode.read_bytes()

    with pytest.raises(ConvertError, match="No capable devices found"):
        run(conn, programs(report(1440, 1080, tag=BEST_TAG)))

    assert episode.read_bytes() == original
    assert not list(episode.parent.glob(f"*{WORKING}"))


def test_a_result_that_doesnt_play_never_replaces_the_original(
    conn: sqlite3.Connection, episode: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KURA_FAKE_FAIL", "play")
    original = episode.read_bytes()

    with pytest.raises(ConvertError, match="didn't play"):
        run(conn, programs(report(1440, 1080, tag=BEST_TAG)))

    assert episode.read_bytes() == original


def test_a_result_that_isnt_right_never_replaces_the_original(
    conn: sqlite3.Connection, episode: Path
):
    with pytest.raises(ConvertError, match="not hevc 10-bit 1440x1080"):
        run(conn, programs(report(720, 540, tag=BEST_TAG)))

    assert not episode.read_bytes().startswith(b"converted")


def test_stopping_leaves_everything_as_it_was(conn: sqlite3.Connection, episode: Path):
    original = episode.read_bytes()

    with pytest.raises(Stopped):
        run(conn, programs(report(1440, 1080, tag=BEST_TAG)), stop=lambda: True)

    assert episode.read_bytes() == original
    assert not list(episode.parent.glob(f"*{WORKING}"))


def test_a_file_that_changed_since_it_was_read_waits_for_a_scan(
    conn: sqlite3.Connection, episode: Path
):
    episode.write_bytes(b"a different file now")

    with pytest.raises(ConvertError, match="changed since Kura read it"):
        run(conn, programs(report(1440, 1080, tag=BEST_TAG)))


def test_a_picture_ffprobe_couldnt_place_is_looked_at_for_interlacing(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    library(conn, tmp_path / "Anime", ["Old/interlaced episode.mkv"])
    monkeypatch.setenv("KURA_FAKE_SIZE", "8x6")
    unsure = report(8, 6, codec="h264")
    cast("list[dict[str, object]]", unsure["streams"])[0].pop("field_order")
    with conn:
        conn.execute("UPDATE files SET probe = ?", (json.dumps(unsure),))
        conn.execute(
            "INSERT INTO jobs (file_id, method, position, added_at) VALUES (1, 'best', 1, 'now')"
        )
    commands: list[Sequence[str]] = []

    run(conn, programs(report(1440, 1080, tag=BEST_TAG), commands))

    decoder = next(c for c in commands if c[-1] == "-" and "rawvideo" in c)
    assert "bwdif=mode=send_frame" in decoder


def test_the_owner_can_choose_a_lighter_method_never_a_heavier_one():
    assert lighter(Method.BEST, Method.REENCODE) is Method.REENCODE  # SD, re-encoded for speed
    assert lighter(Method.BEST, Method.FAST) is Method.FAST
    assert lighter(Method.FAST, Method.BEST) is Method.FAST  # the model is for SD only
    assert lighter(Method.REMUX, Method.BEST) is Method.REMUX  # nothing to upscale


def test_an_sd_episode_can_be_only_re_encoded(conn: sqlite3.Connection, episode: Path):
    with conn:
        conn.execute("UPDATE jobs SET method = 'reencode'")
    commands: list[Sequence[str]] = []

    run(conn, programs(report(1440, 1080, tag="reencode to 1080p · Kura 0.1.0"), commands))

    assert episode.read_bytes().startswith(b"converted ")
    assert not any("rawvideo" in command for command in commands)
