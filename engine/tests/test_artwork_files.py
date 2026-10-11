"""Poster and background pictures next to each show, for media servers: written when the owner
wants them, never over a file already there, and only Kura's own, unchanged, taken away."""

import sqlite3
from pathlib import Path

import pytest

from kura.artwork_files import forget_artwork, write_artwork
from kura.web import Reply
from tests.fake_web import FakeWeb
from tests.shelf import NOW, library

POSTER = "GET https://image.tmdb.org/t/p/w780/poster.jpg"
BACKDROP = "GET https://image.tmdb.org/t/p/w1280/backdrop.jpg"


@pytest.fixture
def show(conn: sqlite3.Connection, tmp_path: Path) -> Path:
    """Trigun's first episode in its own show folder, the owner wanting the pictures."""
    library(conn, tmp_path / "Anime", ["TV/Trigun (1998)/Season 01/Trigun (1998) - S01E01.mkv"])
    with conn:
        conn.execute(
            "INSERT INTO titles (id, kind, name, year, poster, backdrop)"
            " VALUES (1, 'series', 'Trigun', 1998, '/poster.jpg', '/backdrop.jpg')"
        )
        conn.execute("UPDATE files SET title_id = 1, season = 1, episode = 1, matched = 'sure'")
        conn.execute("INSERT INTO settings (key, value) VALUES ('artwork', 'true')")
    return tmp_path / "Anime" / "TV" / "Trigun (1998)"


@pytest.fixture
def pictures() -> FakeWeb:
    return FakeWeb(
        answers={
            POSTER: Reply(200, {"content-type": "image/jpeg"}, b"a poster"),
            BACKDROP: Reply(200, {"content-type": "image/jpeg"}, b"a background"),
        }
    )


def test_the_poster_and_background_go_next_to_the_show_once(
    conn: sqlite3.Connection, show: Path, pictures: FakeWeb
):
    assert write_artwork(conn, pictures, now=NOW) == 2
    assert write_artwork(conn, pictures, now=NOW) == 0  # there already: nothing asked again

    assert (show / "poster.jpg").read_bytes() == b"a poster"
    assert (show / "fanart.jpg").read_bytes() == b"a background"
    assert pictures.paths() == [POSTER, BACKDROP]


def test_nothing_is_written_unless_the_owner_wants_it(
    conn: sqlite3.Connection, show: Path, pictures: FakeWeb
):
    with conn:
        conn.execute("UPDATE settings SET value = 'false' WHERE key = 'artwork'")

    assert write_artwork(conn, pictures, now=NOW) == 0
    assert not (show / "poster.jpg").exists()


def test_a_picture_already_there_is_never_overwritten(
    conn: sqlite3.Connection, show: Path, pictures: FakeWeb
):
    (show / "poster.jpg").write_bytes(b"the owner's own poster")

    write_artwork(conn, pictures, now=NOW)

    assert (show / "poster.jpg").read_bytes() == b"the owner's own poster"
    assert (show / "fanart.jpg").read_bytes() == b"a background"


def test_offline_the_pictures_wait_for_next_time(conn: sqlite3.Connection, show: Path):
    assert write_artwork(conn, FakeWeb(offline=True), now=NOW) == 0

    assert not (show / "poster.jpg").exists()
    assert conn.execute("SELECT COUNT(*) FROM artwork_files").fetchone()[0] == 0


def test_only_kuras_own_unchanged_pictures_are_taken_away(
    conn: sqlite3.Connection, show: Path, pictures: FakeWeb
):
    write_artwork(conn, pictures, now=NOW)
    (show / "fanart.jpg").write_bytes(b"the owner put another background in its place")

    assert forget_artwork(conn) == 1

    assert not (show / "poster.jpg").exists()
    assert (show / "fanart.jpg").read_bytes() == b"the owner put another background in its place"
    assert conn.execute("SELECT COUNT(*) FROM artwork_files").fetchone()[0] == 0


def test_a_folder_shared_with_another_anime_gets_no_pictures(
    conn: sqlite3.Connection, show: Path, pictures: FakeWeb
):
    library(conn, show.parent.parent, ["TV/Trigun (1998)/Season 01/Cowboy Bebop - 01.mkv"])
    with conn:
        conn.execute("INSERT INTO titles (id, kind, name) VALUES (2, 'series', 'Cowboy Bebop')")
        conn.execute("UPDATE files SET title_id = 2 WHERE path LIKE '%Cowboy Bebop - 01.mkv'")

    assert write_artwork(conn, pictures, now=NOW) == 0
