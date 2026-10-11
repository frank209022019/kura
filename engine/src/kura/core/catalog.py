"""What the anime catalogues say: AniList's entries, and TMDB's shows, episodes and films.

Parsed here from their JSON answers, as plain values; asking them is kura/anilist.py's and
kura/tmdb.py's job. AniList knows anime best (every title and nickname, how series, films and
specials connect); TMDB knows the shape Plex shows (seasons, episode titles, air dates) and has
the artwork.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Literal

from kura.core import fields
from kura.core.fields import Json


class TitleKind(StrEnum):
    """What a title is, in the words Kura shows: a TV series, a movie, an OVA or a special."""

    SERIES = "series"
    MOVIE = "movie"
    OVA = "ova"
    SPECIAL = "special"


# AniList's formats as Kura's kinds. A web series (ONA) or short is still a series.
_KINDS = {
    "TV": TitleKind.SERIES,
    "TV_SHORT": TitleKind.SERIES,
    "ONA": TitleKind.SERIES,
    "MOVIE": TitleKind.MOVIE,
    "OVA": TitleKind.OVA,
    "SPECIAL": TitleKind.SPECIAL,
    "MUSIC": TitleKind.SPECIAL,
}


@dataclass(frozen=True)
class Related:
    """Another AniList entry an entry links to: its sequel, prequel, film or side story."""

    id: int
    relation: str  # SEQUEL, PREQUEL, SIDE_STORY, PARENT, SPIN_OFF, ALTERNATIVE, …
    kind: TitleKind | None
    title: str
    start: date | None


@dataclass(frozen=True)
class Anime:
    """One AniList entry: a season (each is its own entry there), a film, an OVA or a special."""

    id: int
    title: str  # the English title when there is one, else the romaji one
    titles: tuple[str, ...]  # every name it goes by: English, romaji, native, then nicknames
    kind: TitleKind | None  # None while AniList doesn't know yet (not released)
    episodes: int | None  # None while it's airing and the end isn't known
    minutes: int | None  # an episode's length, or the film's
    start: date | None
    end: date | None
    airing: bool
    next_episode: int | None  # the next one to air, while it airs
    cover: str | None  # the cover's web address
    related: tuple[Related, ...]

    @property
    def year(self) -> int | None:
        return self.start.year if self.start else None


@dataclass(frozen=True)
class Hit:
    """One TMDB search result."""

    id: int
    media: Literal["tv", "movie"]
    title: str
    original_title: str
    first_aired: date | None  # a show's first episode, or a film's release
    animation: bool
    japanese: bool
    popularity: float

    @property
    def year(self) -> int | None:
        return self.first_aired.year if self.first_aired else None


@dataclass(frozen=True)
class Episode:
    season: int  # 0 holds the specials
    number: int
    title: str | None
    aired: date | None
    minutes: int | None


@dataclass(frozen=True)
class Show:
    """A TMDB TV show with every episode of every season, specials (season 0) included."""

    id: int
    title: str
    original_title: str
    first_aired: date | None
    airing: bool  # more episodes are coming
    poster: str | None  # a path on TMDB's image server
    episodes: tuple[Episode, ...]  # in season order, then episode order

    @property
    def year(self) -> int | None:
        return self.first_aired.year if self.first_aired else None

    def season(self, number: int) -> tuple[Episode, ...]:
        return tuple(episode for episode in self.episodes if episode.season == number)

    @property
    def seasons(self) -> tuple[int, ...]:
        """The numbered seasons, without the specials."""
        return tuple(sorted({e.season for e in self.episodes if e.season > 0}))


@dataclass(frozen=True)
class Film:
    id: int
    title: str
    original_title: str
    released: date | None
    minutes: int | None
    poster: str | None

    @property
    def year(self) -> int | None:
        return self.released.year if self.released else None


def anime_list(answer: Json) -> list[Anime]:
    """The entries in AniList's answer to a search (`Page.media`)."""
    page = fields.mapping(fields.mapping(answer, "data"), "Page")
    return [entry for media in fields.mappings(page, "media") if (entry := anime(media))]


def anime(media: Json) -> Anime | None:
    """One AniList entry (`Media`), or None when it isn't an anime entry Kura can use."""
    number = fields.whole(media, "id")
    if number is None:
        return None
    names = fields.mapping(media, "title")
    english, romaji, native = (fields.text(names, key) for key in ("english", "romaji", "native"))
    titles = _distinct([english, romaji, native, *fields.texts(media, "synonyms")])
    if not titles:
        return None
    status = fields.text(media, "status")
    upcoming = fields.mapping(media, "nextAiringEpisode")
    return Anime(
        id=number,
        title=english or romaji or titles[0],
        titles=titles,
        kind=_kind(fields.text(media, "format")),
        episodes=fields.whole(media, "episodes"),
        minutes=fields.whole(media, "duration"),
        start=_fuzzy_date(fields.mapping(media, "startDate")),
        end=_fuzzy_date(fields.mapping(media, "endDate")),
        airing=status in ("RELEASING", "NOT_YET_RELEASED"),
        next_episode=fields.whole(upcoming, "episode"),
        cover=fields.text(fields.mapping(media, "coverImage"), "large"),
        related=tuple(_related(fields.mapping(media, "relations"))),
    )


def hits(answer: Json, media: Literal["tv", "movie"]) -> list[Hit]:
    """TMDB's search results, from /search/tv or /search/movie."""
    found: list[Hit] = []
    for result in fields.mappings(answer, "results"):
        number = fields.whole(result, "id")
        title = fields.text(result, "name" if media == "tv" else "title")
        if number is None or not title:
            continue
        original = fields.text(result, "original_name" if media == "tv" else "original_title")
        aired = fields.text(result, "first_air_date" if media == "tv" else "release_date")
        countries = fields.texts(result, "origin_country")
        found.append(
            Hit(
                id=number,
                media=media,
                title=title,
                original_title=original or title,
                first_aired=fields.day(aired),
                animation=_ANIMATION in fields.numbers(result, "genre_ids"),
                japanese=fields.text(result, "original_language") == "ja" or "JP" in countries,
                popularity=fields.decimal(result, "popularity") or 0.0,
            )
        )
    return found


def show(details: Json) -> Show | None:
    """A TMDB show from /tv/{id}, with its seasons appended (`append_to_response=season/1,…`)."""
    number = fields.whole(details, "id")
    title = fields.text(details, "name")
    if number is None or not title:
        return None
    episodes: list[Episode] = []
    for key in details:
        if key.startswith("season/"):  # each season appended to the answer
            episodes.extend(_episodes(fields.mapping(details, key)))
    episodes.sort(key=lambda episode: (episode.season, episode.number))
    status = fields.text(details, "status")
    return Show(
        id=number,
        title=title,
        original_title=fields.text(details, "original_name") or title,
        first_aired=fields.day(fields.text(details, "first_air_date")),
        airing=bool(details.get("in_production")) or status in _AIRING,
        poster=fields.text(details, "poster_path"),
        episodes=tuple(episodes),
    )


def season_numbers(details: Json) -> list[int]:
    """The seasons a TMDB show lists, specials (0) included, from /tv/{id} alone."""
    seasons = fields.mappings(details, "seasons")
    return sorted({n for s in seasons if (n := fields.whole(s, "season_number")) is not None})


def film(details: Json) -> Film | None:
    """A TMDB film from /movie/{id}."""
    number = fields.whole(details, "id")
    title = fields.text(details, "title")
    if number is None or not title:
        return None
    return Film(
        id=number,
        title=title,
        original_title=fields.text(details, "original_title") or title,
        released=fields.day(fields.text(details, "release_date")),
        minutes=fields.whole(details, "runtime") or None,
        poster=fields.text(details, "poster_path"),
    )


_ANIMATION = 16  # TMDB's genre number for animation
_AIRING = frozenset({"Returning Series", "In Production", "Planned", "Pilot"})


def _episodes(season: Json) -> list[Episode]:
    found: list[Episode] = []
    for item in fields.mappings(season, "episodes"):
        number = fields.whole(item, "episode_number")
        season_number = fields.whole(item, "season_number")
        if number is None or season_number is None:
            continue
        found.append(
            Episode(
                season=season_number,
                number=number,
                title=fields.text(item, "name") or None,
                aired=fields.day(fields.text(item, "air_date")),
                minutes=fields.whole(item, "runtime") or None,
            )
        )
    return found


def _related(relations: Json) -> list[Related]:
    found: list[Related] = []
    for edge in fields.mappings(relations, "edges"):
        node = fields.mapping(edge, "node")
        number = fields.whole(node, "id")
        if number is None or fields.text(node, "type") not in (None, "ANIME"):
            continue  # the manga and novels it adapts aren't on anyone's shelf
        names = fields.mapping(node, "title")
        title = fields.text(names, "english") or fields.text(names, "romaji")
        if not title:
            continue
        found.append(
            Related(
                id=number,
                relation=fields.text(edge, "relationType") or "OTHER",
                kind=_kind(fields.text(node, "format")),
                title=title,
                start=_fuzzy_date(fields.mapping(node, "startDate")),
            )
        )
    return found


def _kind(format_: str | None) -> TitleKind | None:
    return _KINDS.get(format_) if format_ else None


def _fuzzy_date(parts: Json) -> date | None:
    """AniList's {year, month, day}, where month and day may be unknown: the first day it can be."""
    year = fields.whole(parts, "year")
    if year is None:
        return None
    try:
        return date(year, fields.whole(parts, "month") or 1, fields.whole(parts, "day") or 1)
    except ValueError:
        return None


def _distinct(names: list[str | None]) -> tuple[str, ...]:
    seen: set[str] = set()
    kept: list[str] = []
    for name in names:
        if name and name.strip() and name.casefold() not in seen:
            seen.add(name.casefold())
            kept.append(name.strip())
    return tuple(kept)
