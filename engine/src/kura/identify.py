"""Identifying the library: which anime, and which episode, every video is.

The scan's third stage. Files are grouped and looked up on AniList; with the owner's TMDB key the
same show or film is found on TMDB, whose episode lists say where each file sits and what's
missing. kura/core/identify.py and kura/core/placing.py decide, this module asks the services and
keeps the answers. A file Kura isn't sure about waits for the owner, and files the owner placed
by hand (pinned) are never identified again.
"""

import json
import logging
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import PureWindowsPath

from kura import credentials
from kura.anilist import AniList
from kura.cache import Cache
from kura.config import DataPaths
from kura.core.catalog import Anime, Film, Hit, Show, TitleKind
from kura.core.identify import SURE, FileFacts, Group, Guess, base_title, group_files, guesses
from kura.core.identify import pick_hit as pick_tmdb
from kura.core.names import Kind, parse_name
from kura.core.placing import How, Placement, place
from kura.titles import show_of
from kura.tmdb import Tmdb
from kura.web import Send, WebError

log = logging.getLogger(__name__)

AIRING_EVERY = timedelta(hours=1)  # how often a show still airing has its episode list refreshed
FINISHED_EVERY = timedelta(days=7)  # and a finished one
_SHOWN_GUESSES = 3  # how many guesses the review screen offers


@dataclass(frozen=True)
class Identified:
    sure: int  # files placed without asking
    unsure: int  # files waiting for the owner
    note: str | None  # what couldn't be done this time, in words


class Identifier:
    def __init__(
        self,
        paths: DataPaths,
        transport: Send,
        *,
        now: Callable[[], datetime],
    ) -> None:
        self._paths = paths
        self._transport = transport
        self._now = now
        cache = Cache(paths.cache)
        self._anilist = AniList(transport, cache=cache)
        self._cache = cache

    def run(
        self,
        conn: sqlite3.Connection,
        *,
        stop: Callable[[], bool] = lambda: False,
        looking_at: Callable[[str], None] = lambda _: None,
    ) -> Identified | None:
        """Identifies every file still to identify. None when `stop` asked to stop."""
        files, others = _to_identify(conn)
        stamp = self._now().isoformat()
        _mark_unlookable(conn, others, stamp)
        tmdb = self._tmdb()

        found: list[tuple[Group, list[Guess]]] = []
        for group in group_files(files):
            if stop():
                return None
            looking_at(group.query)
            try:
                found.append((group, guesses(group, self._anilist.search(group.query))))
            except WebError as error:
                log.warning("AniList couldn't be asked about %s: %s", group.query, error)
                return Identified(0, 0, _waiting("AniList", error))

        sure = unsure = 0
        note: str | None = None
        # Series first, so the specials and OVAs after them find their show already there.
        found.sort(key=lambda item: _series_last(item[1]))
        for group, ranked in found:
            if stop():
                return None
            looking_at(group.query)
            try:
                placed, waiting = self._settle(conn, group, ranked, tmdb)
            except WebError as error:
                log.warning("TMDB couldn't be asked about %s: %s", group.query, error)
                note = _waiting("TMDB", error)
                break
            sure, unsure = sure + placed, unsure + waiting
        return Identified(sure, unsure, note)

    def choose(
        self, conn: sqlite3.Connection, file_ids: Sequence[int], anilist_id: int, as_kind: Kind
    ) -> int:
        """The owner's choice: these files are this AniList entry, as episodes, a film, or
        specials. It's pinned, so no rescan undoes it. Returns how many files it placed.

        Raises LookupError when AniList has no such entry, and WebError when a service can't be
        asked right now.
        """
        entry = self._anilist.entry(anilist_id)
        if entry is None:
            raise LookupError(f"AniList has no entry {anilist_id}.")
        title_id, show = self._title_for(conn, entry, self._tmdb())
        stamp = self._now().isoformat()
        chosen = _facts(conn, file_ids)
        with conn:
            for facts in chosen:
                parsed = replace(facts.parsed, kind=as_kind)
                where: Placement | None = None
                if as_kind is not Kind.MOVIE and entry.kind is not TitleKind.MOVIE:
                    if show is not None:
                        where = place(parsed, show, entry)
                    else:
                        where = _by_anilist_number(replace(facts, parsed=parsed), entry)
                special = as_kind is Kind.SPECIAL
                conn.execute(
                    """UPDATE files SET title_id = ?, anilist_id = ?, season = ?, episode = ?,
                              episode_end = ?, matched = 'sure', confidence = 100,
                              pinned = 1, identified_at = ?
                       WHERE id = ?""",
                    (
                        title_id,
                        entry.id,
                        where.season if where else (0 if special else None),
                        where.episode if where else None,
                        where.last if where else None,
                        stamp,
                        facts.id,
                    ),
                )
        return len(chosen)

    def ignore(self, conn: sqlite3.Connection, file_id: int) -> None:
        """The owner says it isn't anime: Kura leaves it out, and no rescan asks again."""
        with conn:
            conn.execute(
                """UPDATE files SET title_id = NULL, season = NULL, episode = NULL,
                          episode_end = NULL, matched = 'ignored', pinned = 1, identified_at = ?
                   WHERE id = ?""",
                (self._now().isoformat(), file_id),
            )

    def search(self, conn: sqlite3.Connection, file_id: int, text: str) -> list[Guess]:
        """AniList's entries for `text`, scored against one file, for the owner to pick from."""
        facts = _facts(conn, [file_id])
        if not facts or not text.strip():
            return []
        group = Group(
            text.strip(), facts[0].parsed.year, facts[0].parsed.kind is Kind.MOVIE, tuple(facts)
        )
        return guesses(group, self._anilist.search(text.strip()))

    def _tmdb(self) -> Tmdb | None:
        key = credentials.load(self._paths, "tmdb")
        return Tmdb(key, self._transport, cache=self._cache) if key else None

    def _settle(
        self,
        conn: sqlite3.Connection,
        group: Group,
        ranked: list[Guess],
        tmdb: Tmdb | None,
    ) -> tuple[int, int]:
        """Matches one group's files, or leaves them for the owner. Returns (sure, unsure)."""
        stamp = self._now().isoformat()
        best = ranked[0] if ranked else None
        if best is None or best.confidence < SURE:
            _mark_unsure(conn, group.files, ranked, stamp)
            return 0, len(group.files)

        entry = best.anime
        title_id, show = self._title_for(conn, entry, tmdb)
        placements: dict[int, Placement | None] = {}
        for facts in group.files:
            if entry.kind is TitleKind.MOVIE or (show is None and facts.parsed.kind is Kind.MOVIE):
                placements[facts.id] = None  # a film is the whole title
            elif show is not None:
                placements[facts.id] = place(facts.parsed, show, entry)
            else:
                placements[facts.id] = _by_anilist_number(facts, entry)
        clashing = _clashes(group.files, placements)

        sure = unsure = 0
        with conn:
            for facts in group.files:
                where = placements[facts.id]
                film = entry.kind is TitleKind.MOVIE
                if facts.id in clashing or (where is None and not film):
                    _mark_unsure(conn, [facts], ranked, stamp, commit=False)
                    unsure += 1
                    continue
                conn.execute(
                    """UPDATE files SET title_id = ?, anilist_id = ?, season = ?, episode = ?,
                              episode_end = ?, matched = 'sure', confidence = ?, guesses = ?,
                              identified_at = ?
                       WHERE id = ? AND pinned = 0""",
                    (
                        title_id,
                        entry.id,
                        where.season if where else None,
                        where.episode if where else None,
                        where.last if where else None,
                        best.confidence,
                        _guesses_json(ranked),
                        stamp,
                        facts.id,
                    ),
                )
                sure += 1
        return sure, unsure

    def _title_for(
        self, conn: sqlite3.Connection, entry: Anime, tmdb: Tmdb | None
    ) -> tuple[int, Show | None]:
        """The library's title for an AniList entry, made or refreshed, with its TMDB show."""
        if tmdb is not None:
            if entry.kind in (TitleKind.OVA, TitleKind.SPECIAL):
                parent = _parent_show(conn, entry)
                if parent is not None:
                    return parent  # the show's specials hold it, in season 0
            media = "movie" if entry.kind is TitleKind.MOVIE else "tv"
            hit = _find(tmdb, entry, media)
            if hit is None and media == "tv" and entry.kind is not TitleKind.SERIES:
                hit = _find(tmdb, entry, "movie")  # a one-off OVA is often a film on TMDB
            if hit is not None:
                return self._tmdb_title(conn, entry, hit, tmdb)
        return self._anilist_title(conn, entry), None

    def _anilist_title(self, conn: sqlite3.Connection, entry: Anime) -> int:
        """The title of an entry Kura knows only from AniList. A list the library already has
        stays until it's due; a show still airing is asked about afresh, since a search answer
        can be days old."""
        row = conn.execute(
            "SELECT * FROM titles WHERE anilist_id = ? AND tmdb_id IS NULL", (entry.id,)
        ).fetchone()
        if row is not None and not due(row, self._now()):
            return row["id"]
        if entry.airing:
            entry = self._anilist.entry(entry.id, fresh=True) or entry
        return save_anilist_title(conn, entry, self._now())

    def _tmdb_title(
        self, conn: sqlite3.Connection, entry: Anime, hit: Hit, tmdb: Tmdb
    ) -> tuple[int, Show | None]:
        row = conn.execute(
            "SELECT * FROM titles WHERE tmdb_type = ? AND tmdb_id = ?", (hit.media, hit.id)
        ).fetchone()
        kind = _kind_for(entry, hit)
        if hit.media == "movie":
            film = tmdb.film(hit.id)
            if film is None:
                return self._anilist_title(conn, entry), None
            return _save_film(conn, row, film, entry, self._now()), None
        if row is not None and not due(row, self._now()):
            return row["id"], show_of(conn, row["id"])
        found = tmdb.show(hit.id)
        if found is None:
            return self._anilist_title(conn, entry), None
        return save_show(conn, found, kind, entry.id, self._now()), found


def save_show(
    conn: sqlite3.Connection,
    show: Show,
    kind: TitleKind,
    anilist_id: int | None,
    now: datetime,
) -> int:
    """Stores a TMDB show and its whole episode list. A title's kind is never narrowed: a show
    first found as a series stays one when its OVAs turn up."""
    with conn:
        row = conn.execute(
            """INSERT INTO titles (kind, name, year, released, tmdb_type, tmdb_id, anilist_id,
                                   airing, poster, checked_at)
               VALUES (?, ?, ?, ?, 'tv', ?, ?, ?, ?, ?)
               ON CONFLICT (tmdb_type, tmdb_id) DO UPDATE SET
                   name = excluded.name, year = excluded.year, released = excluded.released,
                   airing = excluded.airing, poster = excluded.poster,
                   checked_at = excluded.checked_at,
                   anilist_id = COALESCE(titles.anilist_id, excluded.anilist_id),
                   kind = CASE WHEN titles.kind = 'series' THEN 'series' ELSE excluded.kind END
               RETURNING id""",
            (
                kind.value,
                show.title,
                show.year,
                show.first_aired.isoformat() if show.first_aired else None,
                show.id,
                anilist_id,
                int(show.airing),
                show.poster,
                now.isoformat(),
            ),
        ).fetchone()
        title_id: int = row["id"]
        conn.execute("DELETE FROM episodes WHERE title_id = ?", (title_id,))
        conn.executemany(
            "INSERT INTO episodes (title_id, season, number, name, aired, minutes)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    title_id,
                    e.season,
                    e.number,
                    e.title,
                    e.aired.isoformat() if e.aired else None,
                    e.minutes,
                )
                for e in show.episodes
            ],
        )
    return title_id


def _save_film(
    conn: sqlite3.Connection,
    row: sqlite3.Row | None,
    film: Film,
    entry: Anime,
    now: datetime,
) -> int:
    with conn:
        saved = conn.execute(
            """INSERT INTO titles (kind, name, year, released, tmdb_type, tmdb_id, anilist_id,
                                   poster, checked_at)
               VALUES ('movie', ?, ?, ?, 'movie', ?, ?, ?, ?)
               ON CONFLICT (tmdb_type, tmdb_id) DO UPDATE SET
                   name = excluded.name, year = excluded.year, released = excluded.released,
                   poster = excluded.poster, checked_at = excluded.checked_at
               RETURNING id""",
            (
                film.title,
                film.year,
                film.released.isoformat() if film.released else None,
                film.id,
                entry.id if row is None else row["anilist_id"],
                film.poster,
                now.isoformat(),
            ),
        ).fetchone()
    title_id: int = saved["id"]
    return title_id


def save_anilist_title(conn: sqlite3.Connection, entry: Anime, now: datetime) -> int:
    """A title known only from AniList (no TMDB key, or TMDB doesn't have it): its episodes are
    the ones aired so far, numbered 1 to N as AniList counts them. AniList doesn't date them."""
    kind = entry.kind or TitleKind.SERIES
    with conn:
        row = conn.execute(
            """INSERT INTO titles (kind, name, year, released, anilist_id, airing, poster,
                                   checked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (anilist_id) WHERE tmdb_id IS NULL DO UPDATE SET
                   name = excluded.name, year = excluded.year, released = excluded.released,
                   airing = excluded.airing, poster = excluded.poster,
                   checked_at = excluded.checked_at
               RETURNING id""",
            (
                kind.value,
                entry.title,
                entry.year,
                entry.start.isoformat() if entry.start else None,
                entry.id,
                int(entry.airing),
                entry.cover,
                now.isoformat(),
            ),
        ).fetchone()
        title_id: int = row["id"]
        aired = _aired(entry)
        if kind is not TitleKind.MOVIE and aired is not None:
            conn.execute("DELETE FROM episodes WHERE title_id = ?", (title_id,))
            conn.executemany(
                "INSERT INTO episodes (title_id, season, number) VALUES (?, 1, ?)",
                [(title_id, number) for number in range(1, aired + 1)],
            )
    return title_id


def _aired(entry: Anime) -> int | None:
    """How many of an entry's episodes have aired, or None when AniList can't say just now
    (the list Kura has stays as it is)."""
    if not entry.airing:
        return entry.episodes
    return entry.next_episode - 1 if entry.next_episode else None


def _parent_show(conn: sqlite3.Connection, entry: Anime) -> tuple[int, Show | None] | None:
    """The TMDB show an OVA or special belongs to, when the library has it: TMDB keeps them in
    the show's season 0."""
    for related in entry.related:
        if related.kind is not TitleKind.SERIES:
            continue
        row = conn.execute(
            "SELECT id FROM titles WHERE anilist_id = ? AND tmdb_type = 'tv'", (related.id,)
        ).fetchone()
        if row is not None:
            show = show_of(conn, row["id"])
            if show is not None and show.season(0):
                return row["id"], show
    return None


def _find(tmdb: Tmdb, entry: Anime, media: str) -> Hit | None:
    """The TMDB show or film for an entry, searched by its name without the season or part."""
    kind = "movie" if media == "movie" else "tv"
    tried: set[str] = set()
    for name in (entry.title, *entry.titles[:2]):
        query = base_title(name)
        if query.casefold() in tried:
            continue
        tried.add(query.casefold())
        year = entry.year if kind == "movie" else None
        picked = pick_tmdb(entry, tmdb.search(kind, query, year))
        if picked is not None:
            return picked[0]
    return None


def _kind_for(entry: Anime, hit: Hit) -> TitleKind:
    if hit.media == "movie":
        return TitleKind.MOVIE
    if entry.kind is TitleKind.OVA or entry.kind is TitleKind.SPECIAL:
        return entry.kind
    return TitleKind.SERIES


def due(row: sqlite3.Row, now: datetime) -> bool:
    """Whether a show's episode list is old enough to ask TMDB again."""
    checked = row["checked_at"]
    if checked is None:
        return True
    every = AIRING_EVERY if row["airing"] else FINISHED_EVERY
    return now - datetime.fromisoformat(checked) >= every


def _by_anilist_number(facts: FileFacts, entry: Anime) -> Placement | None:
    """Without TMDB, a file sits at its own number among the entry's episodes."""

    number = facts.parsed.episode
    if number is None or facts.parsed.kind is not Kind.EPISODE:
        return None
    if entry.episodes and not 1 <= number <= entry.episodes:
        return None
    return Placement(1, number, facts.parsed.episode_end, How.NUMBERED)


def _clashes(files: Sequence[FileFacts], placements: dict[int, Placement | None]) -> set[int]:
    """Files placed on the same episode though their own numbers differ: one of them is placed
    wrongly, so neither is trusted. Copies of one episode carry the same numbers, and stay."""
    by_spot: dict[tuple[int, int], list[FileFacts]] = defaultdict(list)
    for facts in files:
        where = placements.get(facts.id)
        if where is not None:
            by_spot[(where.season, where.episode)].append(facts)
    clashing: set[int] = set()
    for together in by_spot.values():
        numbers = {(f.parsed.season, f.parsed.episode, f.parsed.part) for f in together}
        if len(numbers) > 1:
            clashing.update(f.id for f in together)
    return clashing


def _facts(conn: sqlite3.Connection, file_ids: Sequence[int]) -> list[FileFacts]:
    """What Kura knows about these files, whatever their state."""
    marks = ",".join("?" * len(file_ids))
    rows = conn.execute(
        f"SELECT id, path, duration FROM files WHERE id IN ({marks}) AND gone_at IS NULL",  # noqa: S608 - only question marks
        tuple(file_ids),
    ).fetchall()
    return [
        FileFacts(
            row["id"],
            PureWindowsPath(row["path"]),
            parse_name(PureWindowsPath(row["path"])),
            row["duration"] / 60 if row["duration"] else None,
        )
        for row in rows
    ]


def _to_identify(conn: sqlite3.Connection) -> tuple[list[FileFacts], list[tuple[int, Kind]]]:
    """Files read and not yet identified (the owner's own choices excepted): the ones to look up,
    and the extras and disc files that can't be."""
    rows = conn.execute(
        """SELECT id, path, duration FROM files
           WHERE gone_at IS NULL AND probed_at IS NOT NULL AND identified_at IS NULL
             AND pinned = 0
           ORDER BY path"""
    ).fetchall()
    files: list[FileFacts] = []
    others: list[tuple[int, Kind]] = []
    for row in rows:
        path = PureWindowsPath(row["path"])
        parsed = parse_name(path)
        if parsed.kind in (Kind.EXTRA, Kind.DVD) or not parsed.best_title:
            others.append((row["id"], parsed.kind))
            continue
        minutes = row["duration"] / 60 if row["duration"] else None
        files.append(FileFacts(row["id"], path, parsed, minutes))
    return files, others


def _mark_unlookable(
    conn: sqlite3.Connection, others: Iterable[tuple[int, Kind]], stamp: str
) -> None:
    with conn:
        conn.executemany(
            "UPDATE files SET matched = ?, identified_at = ? WHERE id = ?",
            [
                ("extra" if kind is Kind.EXTRA else "none", stamp, file_id)
                for file_id, kind in others
            ],
        )


def _mark_unsure(
    conn: sqlite3.Connection,
    files: Iterable[FileFacts],
    ranked: list[Guess],
    stamp: str,
    *,
    commit: bool = True,
) -> None:
    state = "unsure" if ranked else "none"
    rows = [
        (state, ranked[0].confidence if ranked else None, _guesses_json(ranked), stamp, f.id)
        for f in files
    ]
    sql = """UPDATE files SET title_id = NULL, season = NULL, episode = NULL, episode_end = NULL,
                    matched = ?, confidence = ?, guesses = ?, identified_at = ?
             WHERE id = ? AND pinned = 0"""
    if commit:
        with conn:
            conn.executemany(sql, rows)
    else:
        conn.executemany(sql, rows)


def _guesses_json(ranked: list[Guess]) -> str:
    return json.dumps(
        [
            {
                "anilistId": guess.anime.id,
                "title": guess.anime.title,
                "kind": guess.anime.kind.value if guess.anime.kind else None,
                "year": guess.anime.year,
                "episodes": guess.anime.episodes,
                "minutes": guess.anime.minutes,
                "cover": guess.anime.cover,
                "confidence": guess.confidence,
                "reasons": list(guess.reasons),
            }
            for guess in ranked[:_SHOWN_GUESSES]
        ]
    )


def _series_last(ranked: list[Guess]) -> int:
    """Sort key: series first (0), everything else after (1)."""
    best = ranked[0].anime.kind if ranked else None
    return 0 if best is TitleKind.SERIES else 1


def _waiting(service: str, error: WebError) -> str:
    return f"Titles wait for the next scan: {service} couldn't be asked ({error})"
