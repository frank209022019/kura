"""The library's titles as the screens and reports see them: each anime or film with its kind,
release date and files, and for a series, its seasons and what's missing (kura/core/gaps.py).
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from kura.core.catalog import Episode, Show, TitleKind
from kura.core.gaps import Gaps, find_gaps

type Order = Literal["released", "name", "added", "missing"]


@dataclass(frozen=True)
class Title:
    id: int
    kind: TitleKind
    name: str
    year: int | None
    released: date | None  # the first episode, or the film's release
    airing: bool
    poster: str | None  # TMDB's image path, or AniList's cover address
    tmdb: str | None  # "tv/12971", "movie/11299"
    anilist_id: int | None
    files: int  # videos in the library
    added: str | None  # when the first of them was found
    gaps: Gaps | None  # None for a film, or a title without an episode list


def titles(conn: sqlite3.Connection, today: date, order: Order = "released") -> list[Title]:
    """Every title the library holds a video of, in the order asked for."""
    rows = conn.execute(
        """SELECT t.*, COUNT(f.id) AS files, MIN(f.found_at) AS added
           FROM titles AS t JOIN files AS f ON f.title_id = t.id AND f.gone_at IS NULL
           GROUP BY t.id"""
    ).fetchall()
    return sort_titles([_title(conn, row, today) for row in rows], order)


def title(conn: sqlite3.Connection, title_id: int, today: date) -> Title | None:
    row = conn.execute(
        """SELECT t.*, COUNT(f.id) AS files, MIN(f.found_at) AS added
           FROM titles AS t LEFT JOIN files AS f ON f.title_id = t.id AND f.gone_at IS NULL
           WHERE t.id = ? GROUP BY t.id""",
        (title_id,),
    ).fetchone()
    return _title(conn, row, today) if row is not None else None


def sort_titles(found: Sequence[Title], order: Order) -> list[Title]:
    """Release date (oldest first, undated last) is the default everywhere; then name, newest
    added first, or most missing first. Ties go by name."""
    by_name = sorted(found, key=lambda t: (t.name.casefold(), t.year or 0))
    match order:
        case "released":
            return sorted(by_name, key=lambda t: (t.released is None, t.released or date.max))
        case "name":
            return by_name
        case "added":
            return sorted(by_name, key=lambda t: t.added or "", reverse=True)
        case "missing":
            return sorted(by_name, key=lambda t: len(t.gaps.missing) if t.gaps else 0, reverse=True)


def show_of(conn: sqlite3.Connection, title_id: int) -> Show | None:
    """A title's episode list as a show, whether it came from TMDB or from AniList's count."""
    row = conn.execute("SELECT * FROM titles WHERE id = ?", (title_id,)).fetchone()
    if row is None or row["kind"] == "movie":
        return None
    episodes = tuple(
        Episode(e["season"], e["number"], e["name"], _day(e["aired"]), e["minutes"])
        for e in conn.execute(
            "SELECT * FROM episodes WHERE title_id = ? ORDER BY season, number", (title_id,)
        )
    )
    if not episodes:
        return None
    return Show(
        id=row["tmdb_id"] or 0,
        title=row["name"],
        original_title=row["name"],
        first_aired=_day(row["released"]),
        airing=bool(row["airing"]),
        poster=row["poster"],
        episodes=episodes,
    )


def held(conn: sqlite3.Connection, title_id: int) -> list[tuple[int, int, int | None]]:
    """Where each of a title's videos sits: (season, episode, last episode or None)."""
    rows = conn.execute(
        """SELECT season, episode, episode_end FROM files
           WHERE title_id = ? AND gone_at IS NULL AND season IS NOT NULL
             AND episode IS NOT NULL""",
        (title_id,),
    )
    return [(row["season"], row["episode"], row["episode_end"]) for row in rows]


def _title(conn: sqlite3.Connection, row: sqlite3.Row, today: date) -> Title:
    show = show_of(conn, row["id"])
    return Title(
        id=row["id"],
        kind=TitleKind(row["kind"]),
        name=row["name"],
        year=row["year"],
        released=_day(row["released"]),
        airing=bool(row["airing"]),
        poster=row["poster"],
        tmdb=f"{row['tmdb_type']}/{row['tmdb_id']}" if row["tmdb_id"] else None,
        anilist_id=row["anilist_id"],
        files=row["files"],
        added=row["added"],
        gaps=find_gaps(show, held(conn, row["id"]), today) if show else None,
    )


def _day(text: str | None) -> date | None:
    return date.fromisoformat(text[:10]) if text else None
