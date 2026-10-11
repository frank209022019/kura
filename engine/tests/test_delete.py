"""Deleting videos the way Kura deletes: into the quarantine, with their subtitles, put back from
History until the quarantine is cleared out."""

import sqlite3
from pathlib import Path

import pytest

from kura.core.library import QUARANTINE_FOLDER
from kura.core.report import GAP_ANALYSIS_FILE
from kura.history import plans
from kura.tidy import ConvertingError, delete, undo
from tests.shelf import NOW, library

pytestmark = pytest.mark.usefixtures("quarantine")


@pytest.fixture
def season(conn: sqlite3.Connection, tmp_path: Path) -> Path:
    """Trigun's first two episodes in a season folder of their own, the first with subtitles."""
    root = tmp_path / "Anime"
    names = [f"Trigun (1998)/Season 01/Trigun (1998) - S01E0{n}.mkv" for n in (1, 2)]
    library(conn, root, names)
    folder = root / "Trigun (1998)" / "Season 01"
    (folder / "Trigun (1998) - S01E01.en.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n")
    with conn:
        conn.execute(
            "INSERT INTO titles (id, kind, name, year) VALUES (1, 'series', 'Trigun', 1998)"
        )
        conn.execute("UPDATE files SET title_id = 1, season = 1, episode = id, matched = 'sure'")
    return folder


def quarantined(folder: Path) -> list[str]:
    day = Path(folder.anchor) / QUARANTINE_FOLDER / NOW.date().isoformat()
    return sorted(path.name for path in day.iterdir()) if day.is_dir() else []


def test_a_deleted_video_goes_to_quarantine_with_its_subtitles_and_can_come_back(
    conn: sqlite3.Connection, season: Path
):
    episode = season / "Trigun (1998) - S01E01.mkv"

    done = delete(conn, [1], now=NOW)

    assert (done.moved, done.quarantined, done.problems) == (0, 1, ())
    assert sorted(path.name for path in season.iterdir()) == ["Trigun (1998) - S01E02.mkv"]
    assert quarantined(season) == ["Trigun (1998) - S01E01.en.srt", "Trigun (1998) - S01E01.mkv"]
    assert conn.execute("SELECT gone_at FROM files WHERE id = 1").fetchone()[0] is not None
    [plan] = plans(conn)
    assert (plan.title, plan.deleted) == ("Deleted Trigun · S01E01", True)

    assert done.plan_id is not None
    undo(conn, done.plan_id, now=NOW)

    assert episode.is_file()
    assert (season / "Trigun (1998) - S01E01.en.srt").is_file()
    assert conn.execute("SELECT gone_at FROM files WHERE id = 1").fetchone()[0] is None


def test_deleting_a_whole_show_takes_the_folders_it_empties_and_its_report(
    conn: sqlite3.Connection, season: Path
):
    show = season.parent
    (show / GAP_ANALYSIS_FILE).write_text("# Trigun (1998) — gap analysis\n", encoding="utf-8")

    done = delete(conn, [1, 2], now=NOW)

    assert not show.exists()
    [plan] = plans(conn)
    assert plan.title == "Deleted 2 Trigun files"
    assert done.plan_id is not None
    undo(conn, done.plan_id, now=NOW)
    assert sorted(path.name for path in season.iterdir() if path.suffix == ".mkv") == [
        "Trigun (1998) - S01E01.mkv",
        "Trigun (1998) - S01E02.mkv",
    ]


def test_a_video_being_converted_isnt_deleted(conn: sqlite3.Connection, season: Path):
    with conn:
        conn.execute(
            "INSERT INTO jobs (file_id, method, position, state, added_at)"
            " VALUES (1, 'best', 1, 'running', 'now')"
        )

    with pytest.raises(ConvertingError, match=r"^Trigun · S01E01 is being converted"):
        delete(conn, [1, 2], now=NOW)

    assert len(list(season.glob("*.mkv"))) == 2
    assert plans(conn) == []


def test_a_video_waiting_to_convert_leaves_the_queue(conn: sqlite3.Connection, season: Path):
    with conn:
        conn.execute(
            "INSERT INTO jobs (file_id, method, position, added_at) VALUES (1, 'best', 1, 'now')"
        )

    delete(conn, [1], now=NOW)

    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
