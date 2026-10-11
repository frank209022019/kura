"""Where a file sits in a TMDB show: which season and episode, numbered the way Plex shows them.

Releases number episodes in three ways, and all of them land in TMDB's seasons:

- by season: "S02E05", or "05" in a "Season 02" folder;
- straight through: "Dragon Ball Z - 150" is the 150th episode, wherever TMDB's seasons break;
- per AniList entry: "Attack on Titan Season 3 Part 2 - 03" is the third episode of a part that
  TMDB folds into its season 3, found by the part's first air date.

Specials and OVAs go to season 0 by the date they first aired. Anything Kura can't place surely is
left for the owner to review.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from kura.core.catalog import Anime, Episode, Show, TitleKind
from kura.core.names import Kind, ParsedName

_SAME_DAY = timedelta(days=3)  # air dates differ by time zone and listing, never by much more


class How(StrEnum):
    NUMBERED = "numbered"  # by its season and episode numbers
    STRAIGHT = "straight"  # its number counted through every season
    BY_DATE = "by date"  # from its AniList entry's first air date


@dataclass(frozen=True)
class Placement:
    season: int
    episode: int
    last: int | None  # the last episode, for a file that holds several
    how: How


def place(parsed: ParsedName, show: Show, entry: Anime | None = None) -> Placement | None:
    """The file's season and episode in `show`, or None when Kura can't tell surely.

    `entry` is the AniList entry the file matched, which may be one part of the show.
    """
    number = parsed.episode
    if parsed.kind is Kind.SPECIAL or parsed.season == 0 or parsed.folder_season == 0:
        return _special(parsed, show, entry)
    if number is None or parsed.kind is not Kind.EPISODE:
        return None
    numbered = show_episodes(show)
    season = parsed.season if parsed.season is not None else parsed.folder_season

    start = _start_of(entry, numbered)
    if (
        start is not None
        and start > 0
        and entry
        and entry.episodes
        and 1 <= number <= entry.episodes
    ):
        # A later part with its own numbering: count on from its first episode.
        return _from(numbered, start + number - 1, parsed, How.BY_DATE)
    if season is not None:
        in_season = [e for e in numbered if e.season == season]
        if 1 <= number <= len(in_season):
            last = parsed.episode_end
            if last is not None and not number < last <= len(in_season):
                last = None
            return Placement(season, number, last, How.NUMBERED)
    # Counted straight through, from the show's first episode.
    return _from(numbered, number - 1, parsed, How.STRAIGHT)


def show_episodes(show: Show) -> list[Episode]:
    """The show's numbered episodes, season 1 onwards, in order: what straight-through numbers
    count along."""
    return [episode for episode in show.episodes if episode.season > 0]


def _from(numbered: list[Episode], index: int, parsed: ParsedName, how: How) -> Placement | None:
    if not 0 <= index < len(numbered):
        return None
    first = numbered[index]
    last = None
    if parsed.episode is not None and parsed.episode_end is not None:
        end = index + parsed.episode_end - parsed.episode
        # Several episodes in one file stay in one season, as Plex names them.
        if index < end < len(numbered) and numbered[end].season == first.season:
            last = numbered[end].number
    return Placement(first.season, first.number, last, how)


def _start_of(entry: Anime | None, numbered: list[Episode]) -> int | None:
    """Where an AniList entry begins among the show's episodes, by its first air date."""
    if entry is None or entry.start is None or entry.kind not in (TitleKind.SERIES, None):
        return None
    for index, episode in enumerate(numbered):
        if episode.aired is not None and _same_day(episode.aired, entry.start):
            return index
    return None


def lists_special(show: Show, day: date) -> bool:
    """Whether the show's specials (season 0) hold one that first aired on this day."""
    return any(
        episode.aired is not None and _same_day(episode.aired, day) for episode in show.season(0)
    )


def _special(parsed: ParsedName, show: Show, entry: Anime | None) -> Placement | None:
    specials = show.season(0)
    if not specials:
        return None
    number = parsed.episode or 1
    known = any(episode.number == number for episode in specials)
    if parsed.season == 0 and known:
        return Placement(0, number, None, How.NUMBERED)  # named the Plex way: "S00E03"
    # An OVA or special entry is the special that first aired on its day. A series' first day
    # says nothing about which of its specials a file is.
    if entry is not None and entry.start is not None and entry.kind not in (TitleKind.SERIES, None):
        for index, episode in enumerate(specials):
            if episode.aired is not None and _same_day(episode.aired, entry.start):
                at = index + number - 1
                if 0 <= at < len(specials):
                    return Placement(0, specials[at].number, None, How.BY_DATE)
    if parsed.folder_season == 0 and known:
        return Placement(0, number, None, How.NUMBERED)  # "03" in a "Specials" folder
    return None


def _same_day(a: date, b: date) -> bool:
    return abs(a - b) <= _SAME_DAY
