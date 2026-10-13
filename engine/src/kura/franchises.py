"""The rest of each franchise: every series, film, OVA and special AniList ties by story to the
library's titles, the library's or not (kura/core/franchise.py), so a franchise's page can show
what the library is missing of it.

Kura asks AniList about them a few at a time while it's open, at the watcher's look-arounds
(kura/watch.py): the entries it hasn't asked about yet first, a few of each franchise in turn,
nearest the library's first, then each again weekly, or daily while it airs or is still to come,
so a new series or film (Dragon Ball Super: Beerus) turns up by itself.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import zip_longest

from kura import titles
from kura.anilist import AniList
from kura.core.catalog import Anime
from kura.core.franchise import (
    Entry,
    Kept,
    franchises,
    missing,
    nearest,
    own_links,
    story_neighbours,
)
from kura.identify import write_links
from kura.web import WebError

EACH_LOOK = 3  # entries asked about at each look-around: about 12 a minute, of AniList's 30
AIRING_EVERY = timedelta(days=1)  # an entry airing or still to come, or one AniList didn't give
FINISHED_EVERY = timedelta(days=7)
_CHANGING = ("RELEASING", "NOT_YET_RELEASED", "HIATUS")


@dataclass(frozen=True)
class Rest:
    """What AniList ties to a franchise that the library has no part of."""

    titles: list[Entry]  # oldest first
    looking: bool  # some of the franchise is still to be looked up


def look_up(
    conn: sqlite3.Connection, anilist: AniList, now: datetime, count: int = EACH_LOOK
) -> int:
    """Asks AniList about the next few entries of the library's franchises, and keeps what it
    says. Returns how many it asked about. Offline or out of requests, it raises WebError and
    the rest wait; an entry AniList won't answer waits a day while the others go on."""
    asked = 0
    for number in next_to_ask(conn, now, count):
        try:
            entry = anilist.entry(number, fresh=True)
        except WebError as error:
            if error.status is None or error.status == 429:
                raise
            _put_off(conn, number, now)
        else:
            save(conn, number, entry, now)
        asked += 1
    return asked


def next_to_ask(conn: sqlite3.Connection, now: datetime, count: int) -> list[int]:
    """The entries of the library's franchises to ask AniList about next: the ones not asked
    about yet, a few of each franchise in turn and nearest the library's first, then the ones
    due again, longest waiting first."""
    known = {
        row["id"]: row
        for row in conn.execute("SELECT id, name, status, checked_at FROM anilist_entries")
    }
    links = titles.links(conn)
    neighbours = story_neighbours(links)
    held = titles.entries(conn)
    everywhere = set[int]().union(*held.values())
    unasked: list[list[int]] = []
    due: list[tuple[str, int]] = []
    for group in franchises(held, own_links(links, everywhere)):
        own = set[int]().union(*(held[title_id] for title_id in group))
        waiting: list[int] = []
        for number in nearest(own, neighbours, others=everywhere - own):
            row = known.get(number)
            if row is None:
                waiting.append(number)
            elif _due(row, now):
                due.append((row["checked_at"], number))
        unasked.append(waiting)
    in_turn = [number for turn in zip_longest(*unasked) for number in turn if number is not None]
    return list(dict.fromkeys([*in_turn, *(number for _, number in sorted(due))]))[:count]


def save(conn: sqlite3.Connection, number: int, entry: Anime | None, now: datetime) -> None:
    """Keeps what AniList says of an entry and how it ties to others, or that AniList no longer
    has it (None). An entry gone keeps the links it had: they still tie the library's titles."""
    if entry is not None and entry.id != number:
        entry = None  # AniList answered about another: as good as gone
    with conn:
        conn.execute(
            """INSERT OR REPLACE INTO anilist_entries
               (id, name, names, format, status, started, episodes, cover, checked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                number,
                entry.title if entry else None,
                json.dumps(entry.titles, ensure_ascii=False) if entry else None,
                entry.format if entry else None,
                entry.status if entry else None,
                entry.start.isoformat() if entry and entry.start else None,
                entry.episodes if entry else None,
                entry.cover if entry else None,
                now.isoformat(),
            ),
        )
        if entry is not None:
            write_links(conn, entry)


def rest(conn: sqlite3.Connection, franchise: titles.Franchise) -> Rest:
    """What AniList ties to the franchise that the library has no part of, as far as Kura has
    looked it up."""
    links = titles.links(conn)
    held = titles.entries(conn)
    everywhere = set[int]().union(*held.values())
    own = set[int]().union(*(held.get(title.id, set()) for title in franchise.titles))
    reach = nearest(own, story_neighbours(links), others=everywhere - own)
    marks = ", ".join("?" * len(reach))
    rows = {
        row["id"]: row
        for row in conn.execute(
            f"SELECT * FROM anilist_entries WHERE id IN ({marks})",  # noqa: S608 - only placeholders go in
            reach,
        )
    }
    kept = [
        Kept(frozenset(held.get(title.id, set())), show, _videos_in(conn, title.id))
        for title in franchise.titles
        if (show := titles.show_of(conn, title.id)) is not None
    ]
    known = [entry for number in reach if number in rows if (entry := _entry(rows[number]))]
    return Rest(
        missing(known, _matched(conn), kept, links),
        looking=any(number not in rows for number in reach),
    )


def _put_off(conn: sqlite3.Connection, number: int, now: datetime) -> None:
    """AniList wouldn't answer about an entry: what Kura knew of it stays, and it's asked about
    again when due (tomorrow, for one Kura never had an answer about)."""
    with conn:
        conn.execute(
            """INSERT INTO anilist_entries (id, checked_at) VALUES (?, ?)
               ON CONFLICT (id) DO UPDATE SET checked_at = excluded.checked_at""",
            (number, now.isoformat()),
        )


def _due(row: sqlite3.Row, now: datetime) -> bool:
    changing = row["status"] in _CHANGING or row["name"] is None
    every = AIRING_EVERY if changing else FINISHED_EVERY
    return now - datetime.fromisoformat(row["checked_at"]) >= every


def _matched(conn: sqlite3.Connection) -> set[int]:
    """The AniList entries the library's videos are matched to."""
    return {
        row["anilist_id"]
        for row in conn.execute(
            """SELECT DISTINCT anilist_id FROM files
               WHERE gone_at IS NULL AND title_id IS NOT NULL AND anilist_id IS NOT NULL"""
        )
    }


def _entry(row: sqlite3.Row) -> Entry | None:
    """An entry as Kura kept it, or None while AniList gives nothing for it."""
    if row["name"] is None:
        return None
    return Entry(
        id=row["id"],
        name=row["name"],
        names=tuple(json.loads(row["names"] or "[]")),
        format=row["format"],
        status=row["status"],
        start=date.fromisoformat(row["started"]) if row["started"] else None,
        episodes=row["episodes"],
        cover=row["cover"],
    )


def _videos_in(conn: sqlite3.Connection, title_id: int) -> frozenset[tuple[int, int]]:
    """Each episode of a title the library holds a video of, as (season, episode)."""
    return frozenset(
        (season, number)
        for season, first, last in titles.held(conn, title_id)
        for number in range(first, (last or first) + 1)
    )
