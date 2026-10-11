"""Tidying up a real library in a temporary folder: what Kura proposes, applying it, undoing it."""

import sqlite3
from pathlib import Path

import pytest

from kura import credentials
from kura.config import DataPaths
from kura.reports import write_reports
from kura.tidy import apply, propose, undo
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
    sources = [str(p.change.source) for p in propose(downloads, day=NOW.date()).changes]

    done = apply(downloads, sources, now=NOW)

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


def test_undo_puts_it_all_back(downloads: sqlite3.Connection, root: Path):
    before = where(root)
    sources = [str(p.change.source) for p in propose(downloads, day=NOW.date()).changes]
    done = apply(downloads, sources, now=NOW)
    assert done.plan_id is not None

    back = undo(downloads, done.plan_id, now=NOW)

    assert (back.moved, back.problems) == (4, ())
    assert where(root) == before
    paths = {Path(row[0]).name for row in downloads.execute("SELECT path FROM files")}
    assert "Dragon Ball Z - 150.mkv" in paths


def test_only_the_files_asked_for_move(downloads: sqlite3.Connection, root: Path):
    proposal = propose(downloads, day=NOW.date())
    dbz = [str(p.change.source) for p in proposal.changes if p.title == "Dragon Ball Z"]

    done = apply(downloads, dbz, now=NOW)

    assert done.moved == 2
    assert r"Downloads\[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv" in where(root)
    title = downloads.execute("SELECT title FROM plans WHERE id = ?", (done.plan_id,)).fetchone()
    assert title[0] == "Tidied 2 files: Dragon Ball Z"


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
    sources = [str(p.change.source) for p in propose(conn, day=NOW.date()).changes]

    done = apply(conn, sources, now=NOW)

    assert (done.moved, done.quarantined) == (1, 1)
    gone = conn.execute("SELECT path FROM files WHERE gone_at IS NOT NULL").fetchone()
    assert Path(gone[0]).parent.parent.name == "Kura quarantine"
    assert done.plan_id is not None

    undo(conn, done.plan_id, now=NOW)

    assert conn.execute("SELECT COUNT(*) FROM files WHERE gone_at IS NULL").fetchone()[0] == 2
    assert not list(tmp_path.rglob("Kura quarantine"))


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
