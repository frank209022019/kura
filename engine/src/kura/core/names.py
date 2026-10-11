"""Reading anime file names: the show, the season and episode, and what kind of file it is.

anitopy knows fansub and scene naming. Kura adds rules for what it gets wrong, and for
what only the folders know, such as the "Season 03" folder above a bare "05.mkv".
Names are hints: matching against the anime databases confirms them.
"""

import re
import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath

import anitopy


class Kind(StrEnum):
    EPISODE = "episode"
    SPECIAL = "special"  # OVA, OAD, ONA and season 0
    MOVIE = "movie"
    EXTRA = "extra"  # creditless openings and endings, previews, menus
    DVD = "dvd"  # raw DVD files (VTS_01_1.VOB): unknown until matched


@dataclass(frozen=True)
class ParsedName:
    kind: Kind
    title: str | None = None  # from the file name
    folder_title: str | None = None  # from the show's folder
    season: int | None = None  # from the file name
    folder_season: int | None = None  # from a "Season 03" or "Specials" folder
    part: int | None = None  # "Season 3 Part 2": a part numbered from 1 again
    episode: int | None = None  # within its season, or absolute when there is none
    episode_end: int | None = None  # the last episode, when a file holds several
    episode_title: str | None = None
    year: int | None = None
    group: str | None = None
    height: int | None = None
    version: int | None = None
    is_copy: bool = False  # "(copy)", " - Copy", or Kura's own " (2)"

    @property
    def best_title(self) -> str | None:
        return self.title or self.folder_title


def parse_name(path: PurePath) -> ParsedName:
    folder_title, folder_year, folder_season = _folder_context(path)
    if _DVD_FILE.match(path.name):
        return ParsedName(Kind.DVD, folder_title=folder_title, folder_season=folder_season)

    stem, is_copy = _without_copy_marker(path.stem)
    stem = _DISC.sub("", stem)  # "Akira (1988) CD2" is Akira's second part, not an episode 2
    found = _anitopy(stem + path.suffix)

    types = {value.casefold() for value in _all(found, "anime_type")}
    episodes = [_number(value) for value in _all(found, "episode_number")]
    numbers = [number for number in episodes if number is not None]
    title = _clean_title(_first(found, "anime_title"), drop=types | _release_words(found))
    if title and title.isdigit() and not numbers:
        numbers, title = [int(title)], None  # "05.mkv": the name is the episode
    if numbers or _episode_words(found):
        title = _clean_title(title, drop=_EPISODE_WORDS)  # "Cowboy Bebop - Session 05"

    season = _number(_first(found, "anime_season"))
    episode = numbers[0] if numbers else None
    episode_title, part = _title_and_part(stem, _first(found, "episode_title"))
    return ParsedName(
        kind=_kind(types, season if season is not None else folder_season, episode),
        title=title,
        folder_title=folder_title,
        season=season,
        folder_season=folder_season,
        part=part,
        episode=episode,
        episode_end=numbers[-1] if len(numbers) > 1 else None,
        episode_title=_episode_title(episode_title),
        year=_number(_first(found, "anime_year")) or folder_year,
        group=_first(found, "release_group"),
        height=_height(_first(found, "video_resolution")),
        version=_number(_first(found, "release_version")),
        is_copy=is_copy,
    )


def _anitopy(name: str) -> dict[str, str | list[str]]:
    """What anitopy reads in a name. It trips over a few names, such as a bare "Episode.mkv"
    (a keyword with nothing after it): those are read from their folders alone."""
    with _anitopy_lock:
        try:
            return anitopy.parse(name) or {}
        except AttributeError, IndexError, TypeError, ValueError:
            return {}


# anitopy keeps its working state in module globals, so only one thread may use it at a time.
_anitopy_lock = threading.Lock()

_DVD_FILE = re.compile(r"^(?:VTS_\d{2}_\d|VIDEO_TS)\.(?:VOB|IFO|BUP)$", re.IGNORECASE)
_COPY_MARKER = re.compile(
    r"\s*(?:\(copy\)|-\s*copy(?:\s*\(\d+\))?|\((?:[2-9]|[1-9]\d)\))\s*$", re.IGNORECASE
)
_SEASON_FOLDER = re.compile(r"^(?:season|series|s)[\s._-]*0*(\d{1,3})$", re.IGNORECASE)
_SPECIALS_FOLDER = re.compile(r"^specials?$", re.IGNORECASE)
_FILM_PART = re.compile(r"(?:^|[\s._-])(?:cd|dis[ck]|dvd|part|pt)[\s._-]?(\d{1,2})$", re.IGNORECASE)
_DISC = re.compile(r"[\s._-]*\b(?:cd|dis[ck]|dvd)[\s._-]?\d{1,2}$", re.IGNORECASE)
# "S3 Part 2", "Season 3 Part 2": anitopy drops the part, which numbers its episodes from 1 again.
_PART = re.compile(r"\b(?:s\d{1,2}|season\s*\d{1,2})\s*[-:]?\s*part\s*(\d)\b", re.IGNORECASE)
_PART_ALONE = re.compile(r"part\s*(\d)", re.IGNORECASE)
_TITLE_AND_YEAR = re.compile(r"^(?P<title>.+?)\s*\((?P<year>(?:19|20)\d{2})\)$")
_CODEC_WORDS = re.compile(r"\b(?:x26[45]|h\.?26[45]|hevc|avc|xvid|divx)\b", re.IGNORECASE)
_EPISODE_WORDS = frozenset({"session", "episode", "ep", "eps"})

_EXTRA_TYPES = frozenset(
    {"ncop", "nced", "op", "ed", "opening", "ending", "pv", "preview", "menu", "cm", "trailer"}
)
_SPECIAL_TYPES = frozenset({"ova", "oad", "ona", "sp", "special", "specials"})
_MOVIE_TYPES = frozenset({"movie", "gekijouban", "film"})

# Folders that say where files are kept, not which show they are.
_GENERAL_FOLDERS = frozenset(
    {
        "anime",
        "animes",
        "tv",
        "tv shows",
        "shows",
        "series",
        "movies",
        "films",
        "downloads",
        "download",
        "completed",
        "complete",
        "torrents",
        "incoming",
        "unsorted",
        "videos",
        "video",
        "media",
        "library",
        "new folder",
        "extras",
        "extra",
        "bonus",
        "featurettes",
        "misc",
        "other",
        "others",
        "temp",
        "tmp",
    }
)


def _folder_context(path: PurePath) -> tuple[str | None, int | None, int | None]:
    """The show folder's title and year, and the season folder's number."""
    folder = path.parent
    season = season_of_folder(folder.name)
    if season is not None:
        folder = folder.parent
    name = folder.name  # empty at the top of a drive
    if not name or name.casefold() in _GENERAL_FOLDERS or season_of_folder(name) is not None:
        return None, None, season
    if match := _TITLE_AND_YEAR.match(name):
        return match["title"], int(match["year"]), season
    return name, None, season


def _title_and_part(stem: str, episode_title: str | None) -> tuple[str | None, int | None]:
    """The episode title and the part number. anitopy takes "S3 Part 2 - 03" to have the episode
    title "Part 2"; a real title with "part" in it ("Part of It") is no part."""
    if episode_title and (alone := _PART_ALONE.fullmatch(episode_title.strip())):
        return None, int(alone[1])
    before = stem[: stem.find(episode_title)] if episode_title and episode_title in stem else stem
    found = _PART.search(before)
    return episode_title, int(found[1]) if found else None


def film_part(stem: str) -> int | None:
    """Which part of a film in several files this is, from the end of its name: "CD1", "cd2",
    "pt1", "Part 2", "disc 2". None for a film in one file."""
    if found := _FILM_PART.search(_without_copy_marker(stem)[0]):
        return int(found[1])
    return None


def season_of_folder(folder: str) -> int | None:
    """The season a folder's name gives: "Season 02", "S02" or "Season_02" is 2, "Specials" is
    0. None for any other folder."""
    if _SPECIALS_FOLDER.match(folder):
        return 0
    if match := _SEASON_FOLDER.match(folder):
        return int(match[1])
    return None


def _without_copy_marker(stem: str) -> tuple[str, bool]:
    cleaned = _COPY_MARKER.sub("", stem)
    return cleaned, cleaned != stem


def _clean_title(title: str | None, drop: set[str] | frozenset[str]) -> str | None:
    """Removes trailing words that describe the file rather than name the show."""
    if title is None:
        return None
    words = title.split()
    dropped = False
    while words and words[-1].strip(" -:").casefold() in drop:
        words.pop()
        dropped = True
    if dropped and words and words[-1].casefold() == "the":
        words.pop()  # "Cowboy Bebop - The Movie": the article goes with the word it named
    cleaned = " ".join(words).strip(" -:")
    return cleaned or None


def _release_words(found: dict[str, str | list[str]]) -> set[str]:
    return {value.casefold() for value in _all(found, "release_information")}


def _episode_words(found: dict[str, str | list[str]]) -> bool:
    return any(value.casefold() in _EPISODE_WORDS for value in _all(found, "episode_prefix"))


def _kind(types: set[str], season: int | None, episode: int | None) -> Kind:
    if types & _EXTRA_TYPES:
        return Kind.EXTRA
    if types & _SPECIAL_TYPES or season == 0:
        return Kind.SPECIAL
    if types & _MOVIE_TYPES or episode is None:
        return Kind.MOVIE
    return Kind.EPISODE


def _episode_title(title: str | None) -> str | None:
    if title is None or _CODEC_WORDS.search(title):
        return None  # scene names leave codec and group tags where the title would be
    return title


def _height(resolution: str | None) -> int | None:
    if resolution is None:
        return None
    if resolution.casefold() == "4k":
        return 2160
    if match := re.search(r"\d{3,4}x(\d{3,4})", resolution) or re.search(
        r"(\d{3,4})[pi]?$", resolution
    ):
        return int(match[1])
    return None


def _number(value: str | None) -> int | None:
    return int(value) if value is not None and value.isdigit() else None


def _all(found: dict[str, str | list[str]], key: str) -> list[str]:
    value = found.get(key)
    if value is None:
        return []
    return [value] if isinstance(value, str) else value


def _first(found: dict[str, str | list[str]], key: str) -> str | None:
    values = _all(found, key)
    return values[0].strip() if values else None
