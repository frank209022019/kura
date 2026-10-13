"""The rest of each franchise: what AniList ties to the library's titles, looked up a few entries
at a time and kept current, and what the library has no part of."""

import sqlite3
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import pytest

from kura import credentials, franchises, titles
from kura.anilist import API as ANILIST
from kura.anilist import AniList
from kura.config import DataPaths
from kura.core.catalog import Anime, TitleKind
from kura.web import Service
from tests.fake_web import Asked, FakeWeb, reply
from tests.services import internet
from tests.shelf import NOW, identify, library

# Cowboy Bebop's entries on AniList: the series, its film and two specials.
BEBOP, BEBOP_MOVIE, YOSEATSUME_BLUES, EINS_SUMMER_VACATION = 1, 5, 4037, 17205
ONE_PIECE = 21


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "Anime"


@pytest.fixture
def bebop(paths: DataPaths, conn: sqlite3.Connection, root: Path) -> sqlite3.Connection:
    """Cowboy Bebop's first episode and its film, found on AniList and TMDB."""
    credentials.save(paths, "tmdb", "a-test-key")
    library(conn, root, ["Cowboy Bebop/Cowboy Bebop - 01.mkv"])
    library(conn, root, ["Movies/Cowboy Bebop - The Movie (2001).mkv"], minutes=115)
    identify(paths, conn, internet())
    return conn


def asked_about(web: FakeWeb) -> list[int]:
    """The entries AniList was asked about, in order."""
    found: list[int] = []
    for request in web.asked:
        variables = cast("dict[str, object]", request.payload.get("variables", {}))
        if "id" in variables:
            found.append(cast("int", variables["id"]))
    return found


def look_up_everything(conn: sqlite3.Connection, anilist: AniList) -> None:
    while franchises.look_up(conn, anilist, NOW):
        pass


def rest_of_bebop(conn: sqlite3.Connection) -> franchises.Rest:
    [title_id] = [
        row["id"] for row in conn.execute("SELECT id FROM titles WHERE name = 'Cowboy Bebop'")
    ]
    franchise = titles.franchise_of(conn, title_id, NOW.date())
    assert franchise is not None
    return franchises.rest(conn, franchise)


def test_a_franchise_is_looked_up_a_few_entries_at_a_time_the_librarys_own_first(
    bebop: sqlite3.Connection,
):
    web = internet()
    anilist = AniList(web)

    assert franchises.look_up(bebop, anilist, NOW, count=2) == 2
    assert asked_about(web) == [BEBOP, BEBOP_MOVIE]
    look_up_everything(bebop, anilist)

    assert asked_about(web) == [BEBOP, BEBOP_MOVIE, YOSEATSUME_BLUES, EINS_SUMMER_VACATION]
    kept = {row["id"]: row for row in bebop.execute("SELECT * FROM anilist_entries")}
    assert kept[YOSEATSUME_BLUES]["name"] == "Cowboy Bebop: Yoseatsume Blues"
    assert (kept[YOSEATSUME_BLUES]["format"], kept[YOSEATSUME_BLUES]["status"]) == (
        "SPECIAL",
        "FINISHED",
    )
    assert kept[YOSEATSUME_BLUES]["started"] == "1998-06-26"
    links = bebop.execute(
        "SELECT relation FROM anilist_links WHERE anilist_id = ? AND related_id = ?",
        (YOSEATSUME_BLUES, BEBOP),
    ).fetchone()
    assert links["relation"] == "PARENT"  # how the library's own entries reach it


def test_each_entry_is_asked_about_again_weekly_or_daily_while_it_airs(
    bebop: sqlite3.Connection,
):
    look_up_everything(bebop, AniList(internet()))
    with bebop:
        bebop.execute(
            "UPDATE anilist_entries SET status = 'RELEASING' WHERE id = ?", (EINS_SUMMER_VACATION,)
        )

    assert franchises.next_to_ask(bebop, NOW + timedelta(hours=23), 6) == []
    assert franchises.next_to_ask(bebop, NOW + timedelta(days=1), 6) == [EINS_SUMMER_VACATION]
    assert sorted(franchises.next_to_ask(bebop, NOW + timedelta(days=7), 6)) == [
        BEBOP,
        BEBOP_MOVIE,
        YOSEATSUME_BLUES,
        EINS_SUMMER_VACATION,
    ]


def test_what_the_library_has_no_part_of_once_its_looked_up(bebop: sqlite3.Connection):
    before = rest_of_bebop(bebop)
    assert (before.titles, before.looking) == ([], True)  # its specials are only names so far

    look_up_everything(bebop, AniList(internet()))
    after = rest_of_bebop(bebop)

    assert not after.looking
    assert [(entry.name, entry.kind, entry.start) for entry in after.titles] == [
        ("Cowboy Bebop: Yoseatsume Blues", TitleKind.SPECIAL, date(1998, 6, 26)),
        ("Ein's Summer Vacation", TitleKind.SPECIAL, date(2012, 12, 21)),
    ]


def test_a_special_the_library_has_among_its_shows_specials_isnt_missing(
    paths: DataPaths, bebop: sqlite3.Connection, root: Path
):
    # TMDB lists Yoseatsume Blues as the show's second special, aired the same day.
    library(bebop, root, ["Cowboy Bebop/Specials/Cowboy Bebop - S00E02.mkv"])
    identify(paths, bebop, internet())

    look_up_everything(bebop, AniList(internet()))

    assert [entry.name for entry in rest_of_bebop(bebop).titles] == ["Ein's Summer Vacation"]


def test_an_entry_anilist_no_longer_has_is_left_out_and_asked_about_again_the_next_day(
    bebop: sqlite3.Connection,
):
    class Without(AniList):
        def entry(self, anime_id: int, *, fresh: bool = False) -> Anime | None:
            found = super().entry(anime_id, fresh=fresh)
            return None if anime_id == EINS_SUMMER_VACATION else found

    look_up_everything(bebop, Without(internet()))

    assert [entry.name for entry in rest_of_bebop(bebop).titles] == [
        "Cowboy Bebop: Yoseatsume Blues"
    ]
    assert not rest_of_bebop(bebop).looking
    assert franchises.next_to_ask(bebop, NOW + timedelta(hours=23), 6) == []
    assert franchises.next_to_ask(bebop, NOW + timedelta(days=1), 6) == [EINS_SUMMER_VACATION]


def test_an_entry_anilist_wont_answer_waits_a_day_while_the_rest_go_on(
    bebop: sqlite3.Connection,
):
    def refusing(asked: Asked) -> object:
        variables = cast("dict[str, object]", asked.payload["variables"])
        if variables.get("id") == YOSEATSUME_BLUES:
            return reply({"errors": [{"message": "Internal Server Error"}]}, 500)
        return answer(asked)

    web = internet()
    answer = cast("Callable[[Asked], object]", web.answers[f"POST {ANILIST}"])
    web.answers[f"POST {ANILIST}"] = refusing
    anilist = AniList(web, Service("AniList", web, sleep=lambda _: None))  # no waits between tries
    look_up_everything(bebop, anilist)

    assert sorted(set(asked_about(web))) == [
        BEBOP,
        BEBOP_MOVIE,
        YOSEATSUME_BLUES,
        EINS_SUMMER_VACATION,
    ]
    assert [entry.name for entry in rest_of_bebop(bebop).titles] == ["Ein's Summer Vacation"]
    assert not rest_of_bebop(bebop).looking  # nothing waits forever on the one that failed
    assert franchises.next_to_ask(bebop, NOW + timedelta(days=1), 6) == [YOSEATSUME_BLUES]


def test_whats_looked_up_past_the_library_ties_none_of_its_franchises_together(
    paths: DataPaths, bebop: sqlite3.Connection, root: Path
):
    # A crossover AniList ties by story to one of Cowboy Bebop's specials and to One Piece.
    library(bebop, root, ["One Piece/One Piece - 1000.mkv"])
    identify(paths, bebop, internet())
    look_up_everything(bebop, AniList(internet()))
    crossover = 999
    with bebop:
        bebop.execute(
            "INSERT INTO anilist_links VALUES (?, ?, 'SPIN_OFF'), (?, ?, 'PARENT')",
            (YOSEATSUME_BLUES, crossover, crossover, ONE_PIECE),
        )
        bebop.execute(
            "INSERT INTO anilist_entries (id, name, names, format, status, checked_at)"
            " VALUES (?, 'A Crossover Special', '[]', 'SPECIAL', 'FINISHED', ?)",
            (crossover, NOW.isoformat()),
        )

    shelf = [[t.name for t in f.titles] for f in titles.franchises(bebop, NOW.date())]
    assert ["ONE PIECE"] in shelf
    names = [entry.name for entry in rest_of_bebop(bebop).titles]
    assert "A Crossover Special" in names
    assert not [name for name in names if "ONE PIECE" in name.upper()]  # One Piece isn't Bebop's
