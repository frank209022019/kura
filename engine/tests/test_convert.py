"""Converting one file on disk, with stand-ins for ffmpeg, ffprobe and the AI model."""

import json
import sqlite3
import subprocess
from collections.abc import Callable, Sequence
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest

from kura.convert import (
    WORKING,
    ConvertError,
    InUseError,
    Programs,
    Progress,
    Stopped,
    convert,
    lighter,
    put_in,
    restore,
    start,
)
from kura.core.library import QUARANTINE_FOLDER
from kura.core.standard import CINEMA_1080, Method
from tests.converting import BEST_TAG, FAKE_FFMPEG, open_elsewhere, programs, report
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
    discard: Callable[[], bool] = lambda: False,
) -> None:
    heard = seen if seen is not None else []
    convert(
        conn, 1, kit, CINEMA_1080, now=lambda: NOW, report=heard.append, stop=stop, discard=discard
    )


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

    finished = conn.execute("SELECT finished_at FROM jobs").fetchone()[0]

    restore(conn, 1, now=NOW + timedelta(hours=3))

    assert episode.read_bytes() == original
    assert not list(episode.parent.glob(f"*{WORKING}"))
    file = conn.execute("SELECT path, probe FROM files").fetchone()
    assert Path(file["path"]) == episode
    assert json.loads(file["probe"])["streams"][0]["height"] == 6  # the original's
    job = conn.execute("SELECT state, finished_at FROM jobs").fetchone()
    # History still says how long converting took, not how long till it was put back.
    assert (job["state"], job["finished_at"]) == ("restored", finished)


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


def test_a_result_made_but_skipped_before_it_goes_in_is_thrown_away(
    conn: sqlite3.Connection, episode: Path
):
    original = episode.read_bytes()

    with pytest.raises(Stopped):
        run(conn, programs(report(1440, 1080, tag=BEST_TAG)), discard=lambda: True)

    assert episode.read_bytes() == original
    assert not list(episode.parent.glob(f"*{WORKING}"))
    assert conn.execute("SELECT plan_id FROM jobs").fetchone()[0] is None  # nothing journaled


def test_a_file_whose_results_name_is_taken_fails_before_anything_is_made(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    library(conn, tmp_path / "Anime", ["Old/Ep01.mp4"])
    (tmp_path / "Anime" / "Old" / "Ep01.mkv").write_bytes(b"another file, beside it")
    monkeypatch.setenv("KURA_FAKE_SIZE", "8x6")
    with conn:
        conn.execute("UPDATE files SET probe = ?", (json.dumps(report(8, 6, codec="h264")),))
        conn.execute(
            "INSERT INTO jobs (file_id, method, position, added_at) VALUES (1, 'best', 1, 'now')"
        )
    commands: list[Sequence[str]] = []

    with pytest.raises(ConvertError, match=r"^Ep01\.mkv is beside it already"):
        run(conn, programs(report(1440, 1080, tag=BEST_TAG), commands))

    assert commands == []


def test_an_original_set_aside_takes_a_name_still_free_in_quarantine(
    conn: sqlite3.Connection, episode: Path
):
    day = Path(episode.anchor) / QUARANTINE_FOLDER / NOW.date().isoformat()
    day.mkdir(parents=True, exist_ok=True)
    for name in (episode.name, f"{episode.stem} (2).mkv"):  # two set aside earlier today
        (day / name).write_bytes(b"set aside earlier")
    original = episode.read_bytes()

    run(conn, programs(report(1440, 1080, tag=BEST_TAG)))

    assert (day / f"{episode.stem} (3).mkv").read_bytes() == original
    assert episode.read_bytes().startswith(b"converted")


def test_a_copy_an_earlier_try_left_open_says_so(
    conn: sqlite3.Connection, episode: Path, monkeypatch: pytest.MonkeyPatch
):
    unlink = Path.unlink

    def open_still(path: Path, missing_ok: bool = False) -> None:
        if path.name.endswith(WORKING):  # an ffmpeg a crash left still writes it
            raise PermissionError(13, "The process cannot access the file", str(path))
        unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", open_still)

    with pytest.raises(ConvertError, match="still in use"):
        run(conn, programs(report(1440, 1080, tag=BEST_TAG)))


def test_a_file_that_changed_since_it_was_read_waits_for_a_scan(
    conn: sqlite3.Connection, episode: Path
):
    episode.write_bytes(b"a different file now")

    with pytest.raises(ConvertError, match="changed since Kura read it"):
        run(conn, programs(report(1440, 1080, tag=BEST_TAG)))


def test_a_file_saved_over_while_it_converted_keeps_what_was_saved(
    conn: sqlite3.Connection, episode: Path
):
    def heard(progress: Progress) -> None:
        if progress.stage == "checking":  # a better copy saved over it meanwhile
            episode.write_bytes(b"a better copy")

    with pytest.raises(ConvertError, match="changed since Kura read it"):
        convert(
            conn,
            1,
            programs(report(1440, 1080, tag=BEST_TAG)),
            CINEMA_1080,
            now=lambda: NOW,
            report=heard,
            stop=lambda: False,
            discard=lambda: False,
        )

    assert episode.read_bytes() == b"a better copy"
    assert not list(episode.parent.glob(f"*{WORKING}"))


def test_a_result_whose_original_is_open_in_another_app_waits_beside_it(
    conn: sqlite3.Connection, episode: Path, monkeypatch: pytest.MonkeyPatch
):
    open_in_player = open_elsewhere(monkeypatch)
    original = episode.read_bytes()
    kept = episode.with_name(episode.stem + WORKING)

    with pytest.raises(InUseError, match=r"^Trigun \(1998\) - S01E03 is open in another app"):
        run(conn, programs(report(1440, 1080, tag=BEST_TAG)))

    assert episode.read_bytes() == original
    assert kept.read_bytes().startswith(b"converted")
    with pytest.raises(InUseError):
        put_in(conn, 1, now=NOW)  # still open

    open_in_player[0] = False
    put_in(conn, 1, now=NOW)

    assert episode.read_bytes().startswith(b"converted")
    assert not kept.exists()
    job = conn.execute("SELECT state, output_probe FROM jobs").fetchone()
    assert job["state"] == "done"
    assert json.loads(job["output_probe"])["format"]["tags"] == {"KURA": BEST_TAG}


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


def test_a_file_to_remux_found_interlaced_is_encoded_anew(conn: sqlite3.Connection, tmp_path: Path):
    library(conn, tmp_path / "Anime", ["Old/interlaced episode.mp4"])
    unsure = dict(report(1440, 1080))  # the standard's picture, in an MP4
    cast("list[dict[str, object]]", unsure["streams"])[0].pop("field_order")
    unsure["format"] = {
        **cast("dict[str, object]", unsure["format"]),
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
    }
    with conn:
        conn.execute("UPDATE files SET probe = ?", (json.dumps(unsure),))
        conn.execute(
            "INSERT INTO jobs (file_id, method, position, added_at) VALUES (1, 'remux', 1, 'now')"
        )
    commands: list[Sequence[str]] = []

    run(conn, programs(report(1440, 1080, tag="reencode to 1080p · Kura 0.1.0"), commands))

    [made] = [command for command in commands if "-progress" in command]
    assert made[made.index("-c:v") + 1] == "hevc_nvenc"  # a filtered picture can't be copied
    assert any("bwdif=mode=send_frame" in part for part in made)


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


def test_programs_start_with_nothing_on_standard_input(monkeypatch: pytest.MonkeyPatch):
    started: dict[str, object] = {}

    def popen(command: list[str], **options: object) -> object:
        started.update(options)
        return object()

    monkeypatch.setattr(subprocess, "Popen", popen)

    start(["ffmpeg", "-version"])

    assert started["stdin"] == subprocess.DEVNULL


def test_a_test_play_reads_no_keys(conn: sqlite3.Connection, episode: Path):
    commands: list[Sequence[str]] = []

    run(conn, programs(report(1440, 1080, tag=BEST_TAG), commands))

    plays = [command for command in commands if "null" in command]
    assert plays
    assert all(command[len(FAKE_FFMPEG)] == "-nostdin" for command in plays)


def test_an_original_comes_back_where_a_tidy_up_filed_its_converted_file(
    conn: sqlite3.Connection, episode: Path
):
    original = episode.read_bytes()
    run(conn, programs(report(1440, 1080, tag=BEST_TAG)))
    filed = episode.parent / "Trigun (1998) - S01E03 - Murder Machine.mkv"
    episode.rename(filed)  # a tidy-up named it, and its record followed
    with conn:
        conn.execute("UPDATE files SET path = ?", (str(filed),))

    restore(conn, 1, now=NOW)

    assert filed.read_bytes() == original  # the original, under the name it's filed by now
    assert not episode.exists()
    assert not list(episode.parent.glob(f"*{WORKING}"))
    assert Path(conn.execute("SELECT path FROM files").fetchone()[0]) == filed
    assert conn.execute("SELECT state FROM jobs").fetchone()[0] == "restored"


def test_an_original_set_aside_by_a_conversion_that_failed_can_come_back(
    conn: sqlite3.Connection, episode: Path
):
    original = episode.read_bytes()
    run(conn, programs(report(1440, 1080, tag=BEST_TAG)))
    with conn:  # it went wrong after the original was set aside
        conn.execute("UPDATE jobs SET state = 'failed'")

    restore(conn, 1, now=NOW)

    assert episode.read_bytes() == original


def test_putting_an_original_back_twice_says_theres_nothing_to_put_back(
    conn: sqlite3.Connection, episode: Path
):
    run(conn, programs(report(1440, 1080, tag=BEST_TAG)))
    restore(conn, 1, now=NOW)

    with pytest.raises(ConvertError, match="no converted file to put back"):
        restore(conn, 1, now=NOW)
