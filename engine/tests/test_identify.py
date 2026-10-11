"""Identifying the library, the scan's third stage, with AniList and TMDB stood in for."""

import itertools
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from kura import credentials
from kura.anilist import API as ANILIST
from kura.config import DataPaths
from kura.core.fields import Json
from kura.identify import Identified, Identifier
from kura.library import add_folder, find_files, folders, read_file, unread
from tests.fake_ffprobe import REPORT
from tests.fake_web import FakeWeb
from tests.services import SAVED, internet

NOW = datetime(2026, 10, 11, 9, 30, tzinfo=UTC)


def library(conn: sqlite3.Connection, root: Path, names: list[str], minutes: float = 24) -> None:
    """Puts these files in a library folder, found and read (each `minutes` long)."""
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(name.encode())
    add_folder(conn, root, now=NOW)
    [folder] = folders(conn)
    find_files(conn, folder, stamp=NOW.isoformat())
    format_ = cast("dict[str, object]", REPORT["format"])
    report: Json = {**REPORT, "format": {**format_, "duration": str(minutes * 60)}}
    for file_id, path in unread(conn):
        read_file(conn, file_id, path, lambda _: report, now=NOW)


def identify(paths: DataPaths, conn: sqlite3.Connection, web: FakeWeb) -> Identified:
    clock = itertools.count()
    identifier = Identifier(paths, web, now=lambda: NOW + timedelta(seconds=next(clock)))
    done = identifier.run(conn)
    assert done is not None
    return done


def placed(conn: sqlite3.Connection) -> dict[str, tuple[object, ...]]:
    rows = conn.execute(
        """SELECT f.path, f.matched, t.name, t.kind, f.season, f.episode
           FROM files f LEFT JOIN titles t ON t.id = f.title_id"""
    )
    return {Path(row["path"]).name: tuple(row)[1:] for row in rows}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "Anime"


def test_with_a_tmdb_key_every_episode_lands_in_tmdbs_seasons(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    library(
        conn,
        root,
        [
            "Dragon Ball Z (1989)/Dragon Ball Z - 001.mkv",
            "Dragon Ball Z (1989)/Dragon Ball Z - 150.mkv",
            "Downloads/[Group] DBZ - 291 [480p].mkv",
        ],
    )

    done = identify(paths, conn, internet())

    assert placed(conn) == {
        "Dragon Ball Z - 001.mkv": ("sure", "Dragon Ball Z", "series", 1, 1),
        "Dragon Ball Z - 150.mkv": ("sure", "Dragon Ball Z", "series", 5, 11),
        "[Group] DBZ - 291 [480p].mkv": ("sure", "Dragon Ball Z", "series", 9, 38),
    }
    title = conn.execute("SELECT * FROM titles").fetchone()
    assert (title["tmdb_type"], title["tmdb_id"], title["anilist_id"]) == ("tv", 12971, 813)
    assert (title["year"], title["released"]) == (1989, "1989-04-26")
    assert conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 291
    assert done.sure == 3


def test_a_film_is_its_own_title(paths: DataPaths, conn: sqlite3.Connection, root: Path):
    credentials.save(paths, "tmdb", "a-test-key")
    library(conn, root, ["Movies/Cowboy Bebop - The Movie (2001).mkv"], minutes=115)

    identify(paths, conn, internet())

    assert placed(conn) == {
        "Cowboy Bebop - The Movie (2001).mkv": (
            "sure",
            "Cowboy Bebop: The Movie",
            "movie",
            None,
            None,
        )
    }


def test_without_a_key_anilist_numbers_the_episodes(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    library(conn, root, ["Dragon Ball Z/Dragon Ball Z - 150.mkv"])
    web = internet(tmdb=False)

    identify(paths, conn, web)

    assert placed(conn) == {"Dragon Ball Z - 150.mkv": ("sure", "Dragon Ball Z", "series", 1, 150)}
    title = conn.execute("SELECT * FROM titles").fetchone()
    assert (title["tmdb_id"], title["anilist_id"]) == (None, 813)
    assert conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 291
    assert all(path.startswith("POST https://graphql") for path in web.paths())


def test_a_name_kura_cant_match_waits_for_the_owner(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    library(conn, root, ["Downloads/Mystery Show - 03.mkv"])

    identify(paths, conn, internet())

    row = conn.execute("SELECT matched, title_id, guesses FROM files").fetchone()
    assert (row["matched"], row["title_id"], json.loads(row["guesses"])) == ("none", None, [])


def test_extras_are_marked_and_never_looked_up(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    library(conn, root, ["Cowboy Bebop/Extras/NCOP01.mkv"])
    web = internet()

    identify(paths, conn, web)

    assert placed(conn) == {"NCOP01.mkv": ("extra", None, None, None, None)}
    assert web.asked == []


def test_offline_the_files_wait_for_the_next_scan(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    library(conn, root, ["Dragon Ball Z/Dragon Ball Z - 001.mkv"])
    web = internet()
    web.offline = True

    done = identify(paths, conn, web)

    assert "Titles wait for the next scan: AniList couldn't be asked" in str(done.note)
    row = conn.execute("SELECT matched, identified_at FROM files").fetchone()
    assert (row["matched"], row["identified_at"]) == (None, None)


def test_a_file_the_owner_placed_is_left_alone(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    library(conn, root, ["Dragon Ball Z/Dragon Ball Z - 001.mkv"])
    with conn:
        conn.execute("UPDATE files SET pinned = 1")
    web = internet()

    identify(paths, conn, web)

    assert web.asked == []
    assert conn.execute("SELECT matched FROM files").fetchone()[0] is None


def test_a_second_scan_asks_nobody_again(paths: DataPaths, conn: sqlite3.Connection, root: Path):
    credentials.save(paths, "tmdb", "a-test-key")
    library(conn, root, ["Dragon Ball Z/Dragon Ball Z - 001.mkv"])
    identify(paths, conn, internet())
    (root / "Dragon Ball Z" / "Dragon Ball Z - 002.mkv").write_bytes(b"new")
    [folder] = folders(conn)
    find_files(conn, folder, stamp=(NOW + timedelta(hours=1)).isoformat())
    for file_id, path in unread(conn):
        read_file(conn, file_id, path, lambda _: REPORT, now=NOW)
    web = internet()

    identify(paths, conn, web)

    assert placed(conn)["Dragon Ball Z - 002.mkv"] == ("sure", "Dragon Ball Z", "series", 1, 2)
    assert web.asked == []  # AniList's and TMDB's searches were kept; the episode list is fresh


def test_an_ova_goes_into_its_shows_specials_by_date(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    library(conn, root, ["Cowboy Bebop/Cowboy Bebop - 01.mkv"])
    identify(paths, conn, internet())

    entries = json.loads((SAVED / "cowboy-bebop.json").read_text(encoding="utf-8"))
    yoseatsume = next(
        m for m in entries["data"]["Page"]["media"] if m["id"] == 4037
    )  # first aired 26 June 1998
    web = internet()
    web.answers[f"POST {ANILIST}"] = lambda asked: {"data": {"Page": {"media": [yoseatsume]}}}
    (root / "Cowboy Bebop" / "Cowboy Bebop - Yoseatsume Blues - OVA.mkv").write_bytes(b"ova")
    [folder] = folders(conn)
    find_files(conn, folder, stamp=(NOW + timedelta(hours=1)).isoformat())
    for file_id, path in unread(conn):
        read_file(conn, file_id, path, lambda _: REPORT, now=NOW)

    identify(paths, conn, web)

    assert placed(conn)["Cowboy Bebop - Yoseatsume Blues - OVA.mkv"] == (
        "sure",
        "Cowboy Bebop",
        "series",
        0,
        2,
    )


def test_two_files_claiming_one_episode_with_different_numbers_wait_for_the_owner(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    library(
        conn,
        root,
        [
            "Dragon Ball Z/Dragon Ball Z - 040.mkv",  # straight through: season 2, episode 1
            "Dragon Ball Z/Season 02/Dragon Ball Z - 01.mkv",  # season 2, episode 1 by number
        ],
    )

    identify(paths, conn, internet())

    assert {row[0] for row in conn.execute("SELECT matched FROM files")} == {"unsure"}
