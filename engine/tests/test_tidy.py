"""Tidying up a real library in a temporary folder: what Kura proposes, applying it, undoing it."""

import sqlite3
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

import pytest

from kura import credentials
from kura.config import DataPaths
from kura.reports import write_reports
from kura.tidy import ProposalChangedError, Proposed, Reviewed, apply, propose, undo
from tests.services import internet
from tests.shelf import NOW, identify, library


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "Anime"


pytestmark = pytest.mark.usefixtures("quarantine")


@pytest.fixture
def downloads(paths: DataPaths, conn: sqlite3.Connection, root: Path) -> sqlite3.Connection:
    """A Downloads folder holding two anime, as on the tidy board, and a show of its own."""
    credentials.save(paths, "tmdb", "a-test-key")
    library(
        conn,
        root,
        [
            "Downloads/[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv",
            "Downloads/[Hi10] Cowboy_Bebop_-_02_(BD_720p).mkv",
            "Downloads/Dragon Ball Z - 150.mkv",
            "Dragon Ball Z/Dragon Ball Z - 001.mkv",
        ],
    )
    identify(paths, conn, internet())
    return conn


def reviewed(changes: Iterable[Proposed]) -> list[Reviewed]:
    """Changes as the owner saw them, which is what applying is given."""
    return [Reviewed(str(p.change.source), p.change.kind, str(p.change.target)) for p in changes]


def where(root: Path) -> list[str]:
    """Every file under the library folder, relative to it."""
    return sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())


def test_kura_proposes_plexs_layout_and_says_which_moves_leave_a_mixed_folder(
    downloads: sqlite3.Connection, root: Path
):
    proposal = propose(downloads, day=NOW.date())

    found = [
        (p.category, p.title, p.change.source.name, str(p.change.target.relative_to(root)))
        for p in proposal.changes
    ]
    assert found == [
        (
            "mixed",
            "Cowboy Bebop",
            "[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv",
            r"TV\Cowboy Bebop (1998)\Season 01\Cowboy Bebop (1998) - S01E01 - Asteroid Blues.mkv",
        ),
        (
            "mixed",
            "Cowboy Bebop",
            "[Hi10] Cowboy_Bebop_-_02_(BD_720p).mkv",
            r"TV\Cowboy Bebop (1998)\Season 01\Cowboy Bebop (1998) - S01E02 - Stray Dog Strut.mkv",
        ),
        (
            "rename",
            "Dragon Ball Z",
            "Dragon Ball Z - 001.mkv",
            r"TV\Dragon Ball Z (1989)\Season 01\Dragon Ball Z (1989) - S01E01.mkv",
        ),
        (
            "mixed",
            "Dragon Ball Z",
            "Dragon Ball Z - 150.mkv",
            r"TV\Dragon Ball Z (1989)\Season 05\Dragon Ball Z (1989) - S05E11.mkv",
        ),
    ]
    assert proposal.changes[0].root == root
    assert proposal.skipped == ()


def test_applying_files_the_videos_and_keeps_what_they_are(
    downloads: sqlite3.Connection, root: Path
):
    (root / "Dragon Ball Z" / "Dragon Ball Z - 001.en.srt").write_text("subtitles", "utf-8")
    write_reports(downloads, now=NOW)  # a gap analysis in the show's own folder
    changes = reviewed(propose(downloads, day=NOW.date()).changes)

    done = apply(downloads, changes, now=NOW)

    assert (done.moved, done.quarantined, done.problems) == (5, 0, ())
    assert where(root) == [
        r"TV\Cowboy Bebop (1998)\Kura - Gap analysis.md",
        r"TV\Cowboy Bebop (1998)\Season 01\Cowboy Bebop (1998) - S01E01 - Asteroid Blues.mkv",
        r"TV\Cowboy Bebop (1998)\Season 01\Cowboy Bebop (1998) - S01E02 - Stray Dog Strut.mkv",
        r"TV\Dragon Ball Z (1989)\Kura - Gap analysis.md",
        r"TV\Dragon Ball Z (1989)\Season 01\Dragon Ball Z (1989) - S01E01.en.srt",
        r"TV\Dragon Ball Z (1989)\Season 01\Dragon Ball Z (1989) - S01E01.mkv",
        r"TV\Dragon Ball Z (1989)\Season 05\Dragon Ball Z (1989) - S05E11.mkv",
    ]  # the emptied folders went, the old report with them
    rows = downloads.execute(
        "SELECT path, matched, season, episode FROM files WHERE gone_at IS NULL ORDER BY path"
    ).fetchall()
    assert [(Path(row[0]).name, *tuple(row)[1:]) for row in rows] == [
        ("Cowboy Bebop (1998) - S01E01 - Asteroid Blues.mkv", "sure", 1, 1),
        ("Cowboy Bebop (1998) - S01E02 - Stray Dog Strut.mkv", "sure", 1, 2),
        ("Dragon Ball Z (1989) - S01E01.mkv", "sure", 1, 1),
        ("Dragon Ball Z (1989) - S05E11.mkv", "sure", 5, 11),
    ]
    assert propose(downloads, day=NOW.date()).changes == ()  # nothing left to tidy


def test_a_video_left_out_keeps_its_subtitles_with_it(downloads: sqlite3.Connection, root: Path):
    (root / "Dragon Ball Z" / "Dragon Ball Z - 001.en.srt").write_text("subtitles", "utf-8")
    proposal = propose(downloads, day=NOW.date()).changes
    [video] = [p for p in proposal if p.change.source.name == "Dragon Ball Z - 001.mkv"]
    [subtitles] = [p for p in proposal if p.change.source.name.endswith(".en.srt")]
    assert (video.video, subtitles.video) == (video.change.source, video.change.source)

    apply(downloads, reviewed(p for p in proposal if p is not video), now=NOW)  # skipped

    assert (root / "Dragon Ball Z" / "Dragon Ball Z - 001.mkv").exists()
    assert (root / "Dragon Ball Z" / "Dragon Ball Z - 001.en.srt").exists()  # stayed with it


def test_undo_puts_it_all_back(downloads: sqlite3.Connection, root: Path):
    before = where(root)
    done = apply(downloads, reviewed(propose(downloads, day=NOW.date()).changes), now=NOW)
    assert done.plan_id is not None

    back = undo(downloads, done.plan_id, now=NOW)

    assert (back.moved, back.problems) == (4, ())
    assert where(root) == before
    paths = {Path(row[0]).name for row in downloads.execute("SELECT path FROM files")}
    assert "Dragon Ball Z - 150.mkv" in paths


def test_undo_leaves_a_video_being_converted_where_it_is(downloads: sqlite3.Connection, root: Path):
    done = apply(downloads, reviewed(propose(downloads, day=NOW.date()).changes), now=NOW)
    assert done.plan_id is not None
    bebop = downloads.execute("SELECT id FROM files WHERE path LIKE '%Bebop (1998) - S01E01%'")
    with downloads:
        downloads.execute(
            "INSERT INTO jobs (file_id, method, position, state, added_at)"
            " VALUES (?, 'best', 1, 'running', 'now')",
            (bebop.fetchone()[0],),
        )

    back = undo(downloads, done.plan_id, now=NOW)

    assert back.moved == 3
    assert [p.problem for p in back.problems] == [
        "Kura couldn't put it back. It's being converted: put it back once it's done."
    ]


def test_only_the_files_asked_for_move(downloads: sqlite3.Connection, root: Path):
    proposal = propose(downloads, day=NOW.date())
    dbz = reviewed(p for p in proposal.changes if p.title == "Dragon Ball Z")

    done = apply(downloads, dbz, now=NOW)

    assert done.moved == 2
    assert r"Downloads\[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv" in where(root)
    title = downloads.execute("SELECT title FROM plans WHERE id = ?", (done.plan_id,)).fetchone()
    assert title[0] == "Tidied 2 files: Dragon Ball Z"


def test_a_change_proposed_differently_now_stops_them_all(
    downloads: sqlite3.Connection, root: Path
):
    before = where(root)
    changes = reviewed(propose(downloads, day=NOW.date()).changes)
    changes[-1] = Reviewed(changes[-1].source, changes[-1].kind, str(root / "Elsewhere.mkv"))

    with pytest.raises(ProposalChangedError):
        apply(downloads, changes, now=NOW)

    assert where(root) == before


def test_nothing_asked_for_changes_nothing(downloads: sqlite3.Connection, root: Path):
    before = where(root)

    done = apply(downloads, [], now=NOW)

    assert (done.plan_id, done.moved) == (None, 0)
    assert where(root) == before


def test_a_second_copy_is_set_aside_unless_the_owner_keeps_it(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    library(conn, root, ["Bebop/Cowboy Bebop - 01.mkv", "Bebop/Cowboy Bebop - 01 (copy).mkv"])
    identify(paths, conn, internet())

    proposal = propose(conn, day=NOW.date())

    [duplicate] = proposal.duplicates
    assert duplicate.label == "Cowboy Bebop · S01E01"
    assert duplicate.keep.path.name == "Cowboy Bebop - 01.mkv"
    assert [copy.path.name for copy in duplicate.drop] == ["Cowboy Bebop - 01 (copy).mkv"]
    assert duplicate.reason == "Kept Cowboy Bebop - 01.mkv instead: the other is named as a copy"
    first = proposal.changes[0]
    assert (first.category, first.change.kind.value) == ("duplicate", "quarantine")

    swapped = propose(conn, day=NOW.date(), keep=[str(duplicate.drop[0].path)])

    assert swapped.duplicates[0].keep.path.name == "Cowboy Bebop - 01 (copy).mkv"
    assert swapped.duplicates[0].reason.endswith("instead: you chose it")


def test_a_quarantined_copy_leaves_the_library_until_its_put_back(
    paths: DataPaths, conn: sqlite3.Connection, root: Path, tmp_path: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    library(conn, root, ["Bebop/Cowboy Bebop - 01.mkv", "Bebop/Cowboy Bebop - 01 (copy).mkv"])
    identify(paths, conn, internet())
    done = apply(conn, reviewed(propose(conn, day=NOW.date()).changes), now=NOW)

    assert (done.moved, done.quarantined) == (1, 1)
    gone = conn.execute("SELECT path FROM files WHERE gone_at IS NOT NULL").fetchone()
    set_aside = Path(gone[0])
    assert set_aside.parent.parent.name == "Kura quarantine"
    assert set_aside.is_file()
    assert done.plan_id is not None

    undo(conn, done.plan_id, now=NOW)

    assert conn.execute("SELECT COUNT(*) FROM files WHERE gone_at IS NULL").fetchone()[0] == 2
    assert not set_aside.exists()
    assert (root / "Bebop" / "Cowboy Bebop - 01 (copy).mkv").is_file()


def test_a_special_kura_cant_number_stays_where_it_is(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    library(conn, root, ["Bebop/Cowboy Bebop - 01.mkv"])
    identify(paths, conn, internet())
    with conn:
        conn.execute("UPDATE files SET season = 0, episode = NULL")

    proposal = propose(conn, day=NOW.date())

    assert proposal.changes == ()
    assert [(path.name, why) for path, why in proposal.skipped] == [
        ("Cowboy Bebop - 01.mkv", "Kura doesn't know which episode it is")
    ]


def test_a_film_in_two_files_is_filed_as_its_two_parts(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    names = [f"Movies/Cowboy Bebop - The Movie (2001) CD{part}.mkv" for part in (1, 2)]
    library(conn, root, names, minutes=58)
    identify(paths, conn, internet())

    proposal = propose(conn, day=NOW.date())

    film = r"Movies\Cowboy Bebop - The Movie (2001)\Cowboy Bebop - The Movie (2001)"
    assert [str(p.change.target.relative_to(root)) for p in proposal.changes] == [
        f"{film} - pt1.mkv",
        f"{film} - pt2.mkv",
    ]
    assert proposal.duplicates == ()


def test_one_file_named_part_2_is_a_whole_film(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    library(conn, root, ["Movies/Cowboy Bebop - The Movie (2001) Part 2.mkv"], minutes=115)
    identify(paths, conn, internet())

    [proposed] = propose(conn, day=NOW.date()).changes

    assert proposed.change.target.name == "Cowboy Bebop - The Movie (2001).mkv"


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows'")
def test_a_folder_that_is_a_link_is_never_a_place_to_file(
    paths: DataPaths, conn: sqlite3.Connection, root: Path, tmp_path: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    library(conn, root, ["Bebop/Cowboy Bebop - 01.mkv"])
    identify(paths, conn, internet())
    (tmp_path / "Elsewhere").mkdir()
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(root / "TV"), str(tmp_path / "Elsewhere")],  # noqa: S607
        check=True,
        capture_output=True,
    )

    proposal = propose(conn, day=NOW.date())

    assert proposal.changes == ()
    assert [(path.name, why) for path, why in proposal.skipped] == [
        ("Cowboy Bebop - 01.mkv", "Its new folder is a link to another place, which scans skip")
    ]


def test_a_copy_is_never_set_aside_on_top_of_one_set_aside_earlier(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    library(conn, root, ["Bebop/Cowboy Bebop - 01.mkv", "Bebop/Cowboy Bebop - 01 (copy).mkv"])
    identify(paths, conn, internet())
    earlier = Path(root.anchor) / "Kura quarantine" / NOW.date().isoformat()
    earlier.mkdir(parents=True, exist_ok=True)
    (earlier / "Cowboy Bebop - 01 (copy).mkv").write_bytes(b"set aside this morning")

    first = propose(conn, day=NOW.date()).changes[0]

    assert first.change.target == earlier / "Cowboy Bebop - 01 (copy) (2).mkv"


def test_a_folder_already_there_keeps_its_own_spelling(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    (root / "tv" / "cowboy bebop (1998)" / "season 01").mkdir(parents=True)
    library(conn, root, ["Downloads/Cowboy Bebop - 01.mkv"])
    identify(paths, conn, internet())

    [proposed] = propose(conn, day=NOW.date()).changes

    assert str(proposed.change.target) == str(
        root
        / "tv"
        / "cowboy bebop (1998)"
        / "season 01"
        / "Cowboy Bebop (1998) - S01E01 - Asteroid Blues.mkv"
    )


# Converting, or made and waiting beside its original for another app to let go of it.
BUSY = pytest.mark.parametrize(
    ("state", "retry_at"), [("running", None), ("queued", "2026-10-11T10:05:00+02:00")]
)


@BUSY
def test_a_video_being_converted_stays_where_it_is_till_its_done(
    downloads: sqlite3.Connection, root: Path, state: str, retry_at: str | None
):
    bebop = downloads.execute("SELECT id FROM files WHERE path LIKE '%Bebop_-_01%'").fetchone()[0]
    with downloads:
        downloads.execute(
            "INSERT INTO jobs (file_id, method, position, state, added_at, retry_at)"
            " VALUES (?, 'best', 1, ?, ?, ?)",
            (bebop, state, NOW.isoformat(), retry_at),
        )

    proposal = propose(downloads, day=NOW.date())

    assert "[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv" not in {
        p.change.source.name for p in proposal.changes
    }
    assert ("[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv", "It's being converted") in {
        (path.name, why) for path, why in proposal.skipped
    }


def test_copies_of_a_video_being_converted_wait_for_it_too(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    library(conn, root, ["Bebop/Cowboy Bebop - 01.mp4", "Downloads/Cowboy Bebop - 01.mkv"])
    identify(paths, conn, internet())
    with conn:  # the MP4 becomes an MKV of the name the other copy would be filed under
        conn.execute(
            "INSERT INTO jobs (file_id, method, position, state, added_at)"
            " SELECT id, 'best', 1, 'running', 'now' FROM files WHERE path LIKE '%.mp4'"
        )

    proposal = propose(conn, day=NOW.date())

    assert [p.change.source.name for p in proposal.changes] == []
    assert {(path.name, why) for path, why in proposal.skipped} == {
        ("Cowboy Bebop - 01.mp4", "It's being converted"),
        ("Cowboy Bebop - 01.mkv", "A copy of it is being converted"),
    }


def test_with_names_kept_a_video_moves_into_its_folder_under_its_own_name(
    downloads: sqlite3.Connection, root: Path
):
    with downloads:
        downloads.execute("INSERT INTO settings (key, value) VALUES ('naming', '\"keep\"')")

    proposal = propose(downloads, day=NOW.date())

    bebop = next(p for p in proposal.changes if p.change.source.name.startswith("[Hi10]"))
    assert str(bebop.change.target.relative_to(root)) == (
        r"TV\Cowboy Bebop (1998)\Season 01\[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv"
    )
