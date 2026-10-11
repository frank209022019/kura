"""The library's titles as the screens and reports see them: each anime or film with its kind,
release date and files, and for a series, its seasons and what's missing (kura/core/gaps.py).
"""

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from kura.core.catalog import Episode, Show, TitleKind
from kura.core.franchise import Link
from kura.core.franchise import franchises as group_franchises
from kura.core.gaps import Gaps, find_gaps
from kura.core.media import MediaInfo, media_from_ffprobe
from kura.core.standard import Decision, Method, Standard, decide

type Order = Literal["released", "name", "added", "missing"]
type State = Literal["ready", "to convert", "broken", "missing", "upcoming"]


@dataclass(frozen=True)
class Franchise:
    """Titles AniList ties together by story (kura/core/franchise.py). A title on its own is a
    franchise of one."""

    id: int  # its lead's: the first series to air, or else the first title
    name: str  # its lead's
    titles: tuple[Title, ...]  # in the order asked for

    @property
    def released(self) -> date | None:
        dated = [t.released for t in self.titles if t.released]
        return min(dated) if dated else None


@dataclass(frozen=True)
class EpisodeStatus:
    """One episode of a title and how it stands: at the standard (ready), still to convert,
    broken (it couldn't be read), missing, or still to air. Status by shape on screen."""

    episode: Episode
    state: State
    file_id: int | None
    problem: str | None  # why a broken file couldn't be read
    media: MediaInfo | None
    decision: Decision | None  # what converting it to the standard takes


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


def franchises(conn: sqlite3.Connection, today: date, order: Order = "released") -> list[Franchise]:
    """Every franchise the library holds a video of, in the order asked for, each with its titles
    in that order too."""
    found = titles(conn, today, "released")  # so a franchise's first series leads it
    entries: dict[int, set[int]] = {t.id: {t.anilist_id} if t.anilist_id else set() for t in found}
    for row in conn.execute(
        """SELECT DISTINCT title_id, anilist_id FROM files
           WHERE gone_at IS NULL AND title_id IS NOT NULL AND anilist_id IS NOT NULL"""
    ):
        entries.setdefault(row["title_id"], set()).add(row["anilist_id"])
    links = [
        Link(row["anilist_id"], row["related_id"], row["relation"])
        for row in conn.execute("SELECT * FROM anilist_links")
    ]
    by_id = {t.id: t for t in found}
    grouped = group_franchises({t.id: entries[t.id] for t in found}, links)
    made = [_franchise([by_id[title_id] for title_id in group], order) for group in grouped]
    return sort_franchises(made, order)


def franchise_of(
    conn: sqlite3.Connection, title_id: int, today: date, order: Order = "released"
) -> Franchise | None:
    """The franchise a title belongs to, found by any of its titles."""
    return next(
        (f for f in franchises(conn, today, order) if any(t.id == title_id for t in f.titles)),
        None,
    )


def sort_franchises(found: Sequence[Franchise], order: Order) -> list[Franchise]:
    """As titles sort (sort_titles): by first release, name, newest added or most missing."""
    by_name = sorted(found, key=lambda f: f.name.casefold())
    match order:
        case "released":
            return sorted(by_name, key=lambda f: (f.released is None, f.released or date.max))
        case "name":
            return by_name
        case "added":
            return sorted(by_name, key=lambda f: max(t.added or "" for t in f.titles), reverse=True)
        case "missing":
            return sorted(
                by_name,
                key=lambda f: sum(len(t.gaps.missing) for t in f.titles if t.gaps),
                reverse=True,
            )


def _franchise(members: list[Title], order: Order) -> Franchise:
    lead = next((t for t in members if t.kind is TitleKind.SERIES), members[0])
    return Franchise(lead.id, lead.name, tuple(sort_titles(members, order)))


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
        # AniList's list holds only the episodes aired so far, undated (save_anilist_title):
        # none of them is still to come.
        airing=bool(row["airing"]) and row["tmdb_id"] is not None,
        poster=row["poster"],
        episodes=episodes,
    )


def episode_statuses(
    conn: sqlite3.Connection, title_id: int, show: Show, standard: Standard, today: date
) -> list[EpisodeStatus]:
    """Every episode of the show, specials (season 0) included, with how it stands."""
    covering: dict[tuple[int, int], sqlite3.Row] = {}
    for file in conn.execute(
        """SELECT id, season, episode, episode_end, problem, probe FROM files
           WHERE title_id = ? AND gone_at IS NULL AND season IS NOT NULL
             AND episode IS NOT NULL
           ORDER BY problem IS NOT NULL, id""",  # a copy that plays counts first
        (title_id,),
    ):
        for number in range(file["episode"], (file["episode_end"] or file["episode"]) + 1):
            covering.setdefault((file["season"], number), file)
    gaps = find_gaps(show, held(conn, title_id), today)
    upcoming = set(gaps.upcoming)
    found: list[EpisodeStatus] = []
    for episode in show.episodes:
        file = covering.get((episode.season, episode.number))
        if file is None:
            state: State = "upcoming" if episode in upcoming else "missing"
            found.append(EpisodeStatus(episode, state, None, None, None, None))
        elif file["problem"] or not file["probe"]:
            found.append(EpisodeStatus(episode, "broken", file["id"], file["problem"], None, None))
        else:
            media = media_from_ffprobe(json.loads(file["probe"]))
            decision = decide(media, standard)
            state = "ready" if decision.method is Method.RENAME else "to convert"
            found.append(EpisodeStatus(episode, state, file["id"], None, media, decision))
    return found


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
