"""Working out which anime each video is: grouping files that look like the same anime, scoring
AniList's entries against them, and picking the same show or film on TMDB.

Every guess gets a confidence from 0 to 100 and the reasons for it, in the words the review screen
shows. Kura accepts a guess on its own only when it's sure; the rest wait for the owner.
"""

import re
import statistics
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import PurePath

from kura.core.catalog import Anime, Hit, TitleKind
from kura.core.names import Kind, ParsedName, film_part

SURE = 75  # a guess at least this confident is taken without asking
WORTH_SHOWING = 15  # guesses below this aren't shown on the review screen


@dataclass(frozen=True)
class FileFacts:
    """What Kura knows about one video before identifying it."""

    id: int
    path: PurePath
    parsed: ParsedName
    minutes: float | None  # its length, once ffprobe has read it


@dataclass(frozen=True)
class Group:
    """Files that look like the same anime, looked up together."""

    query: str  # the name to search for: "Dragon Ball Z"
    year: int | None
    movie: bool  # every file looks like a film
    files: tuple[FileFacts, ...]

    @property
    def longest_episode(self) -> int | None:
        numbers = [f.parsed.episode_end or f.parsed.episode for f in self.files]
        known = [n for n in numbers if n is not None]
        return max(known) if known else None

    @property
    def minutes(self) -> float | None:
        lengths = [f.minutes for f in self.files if f.minutes]
        if not lengths:
            return None
        parts = {film_part(f.path.stem) for f in self.files} - {None}
        if self.movie and len(parts) > 1:
            return sum(lengths)  # a film in parts (CD1, CD2) is as long as they are together
        return statistics.median(lengths)


@dataclass(frozen=True)
class Guess:
    anime: Anime
    confidence: int  # 0 to 100
    reasons: tuple[str, ...]  # "Title matches", "1989 fits", …


def group_files(files: Iterable[FileFacts]) -> list[Group]:
    """Files that look like the same anime, by their title (from the name or the folder), by
    whether they're films, and by part: "Season 3 Part 2" numbers its episodes from 1 again, so
    it is looked up on its own. Files without any title can't be looked up, so they're left out."""
    grouped: dict[tuple[str, str | None, bool], list[FileFacts]] = {}
    names: dict[tuple[str, str | None, bool], Counter[str]] = {}
    for facts in files:
        title = facts.parsed.best_title
        if not title or facts.parsed.kind in (Kind.EXTRA, Kind.DVD):
            continue
        key = (normalize(title), _part_words(facts.parsed), facts.parsed.kind is Kind.MOVIE)
        grouped.setdefault(key, []).append(facts)
        names.setdefault(key, Counter())[title] += 1
    groups: list[Group] = []
    for key, members in grouped.items():
        years = Counter(f.parsed.year for f in members if f.parsed.year)
        title = names[key].most_common(1)[0][0]  # the spelling most files use
        groups.append(
            Group(
                query=f"{title} {key[1]}" if key[1] else title,
                year=years.most_common(1)[0][0] if years else None,
                movie=key[2],
                files=tuple(members),
            )
        )
    return sorted(groups, key=lambda group: (group.query.casefold(), group.movie))


def _part_words(parsed: ParsedName) -> str | None:
    """ "Season 3 Part 2" for a file from a later part, else None."""
    if parsed.part is None or parsed.part < 2:
        return None
    season = parsed.season if parsed.season is not None else parsed.folder_season
    return f"Season {season} Part {parsed.part}" if season else f"Part {parsed.part}"


def guesses(group: Group, entries: Sequence[Anime]) -> list[Guess]:
    """AniList's entries as guesses for a group, most confident first."""
    found = [_guess(group, entry, rank) for rank, entry in enumerate(entries)]
    found.sort(key=lambda guess: guess.confidence, reverse=True)
    return [guess for guess in found if guess.confidence >= WORTH_SHOWING]


def _guess(group: Group, entry: Anime, rank: int) -> Guess:
    name = max(similarity(group.query, title) for title in entry.titles)
    score = name * 70
    reasons: list[str] = ["Title matches" if name >= 0.95 else f"Title {round(name * 100)}% alike"]

    if group.year and entry.year:
        if group.year == entry.year:
            score += 15
            reasons.append(f"{entry.year} fits")
        elif abs(group.year - entry.year) == 1:
            score += 5
        else:
            score -= 25
            reasons.append(f"From {entry.year}, not {group.year}")

    score += _kind_fit(group, entry, reasons)

    longest = group.longest_episode
    if longest is not None and entry.episodes and not group.movie:
        if longest <= entry.episodes:
            score += 10
            reasons.append(
                f"{_episodes(entry.episodes)} {'fits' if entry.episodes == 1 else 'fit'}"
            )
        elif not entry.airing:
            score -= 20
            reasons.append(f"Only {_episodes(entry.episodes)}, files go up to {longest}")

    minutes = group.minutes
    if minutes and entry.minutes:
        if abs(minutes - entry.minutes) <= max(3, entry.minutes * 0.25):
            score += 5
            reasons.append(f"{round(minutes)} min fits")
        else:
            score -= 15
            reasons.append(f"{round(minutes)} min, not {entry.minutes}")

    if rank == 0:
        score += 5  # AniList ranked it first
    return Guess(entry, max(0, min(100, round(score))), tuple(reasons))


def _kind_fit(group: Group, entry: Anime, reasons: list[str]) -> float:
    if entry.kind is None:
        return -10
    if group.movie:
        if entry.kind is TitleKind.MOVIE:
            reasons.append("A film, like the file")
            return 10
        return -30 if entry.kind is TitleKind.SERIES else -10
    if entry.kind is TitleKind.MOVIE:
        return -40
    specials = all(f.parsed.kind is Kind.SPECIAL for f in group.files)
    if entry.kind in (TitleKind.OVA, TitleKind.SPECIAL):
        return 10 if specials else -10
    return -5 if specials else 5


def pick_hit(entry: Anime, found: Sequence[Hit]) -> tuple[Hit, int] | None:
    """The TMDB show or film that is `entry`, and how sure Kura is, or None when none fits.

    A later season or part on AniList is the same show on TMDB, so names are compared without
    "Season 3 Part 2", and the show may have started before the entry did.
    """
    names = {base_title(title) for title in entry.titles} | set(entry.titles)
    best: tuple[Hit, int] | None = None
    for rank, hit in enumerate(found):
        name = max(
            similarity(own, theirs) for own in names for theirs in (hit.title, hit.original_title)
        )
        score = name * 70
        if entry.year and hit.year:
            if hit.year == entry.year:
                score += 15
            elif hit.year < entry.year and hit.media == "tv":
                score += 5  # the show began with an earlier season
            elif abs(hit.year - entry.year) > 1:
                score -= 20
        score += 8 if hit.animation else -15
        score += 7 if hit.japanese else -5
        score += 5 if rank == 0 else 0
        confidence = max(0, min(100, round(score)))
        if best is None or confidence > best[1]:
            best = (hit, confidence)
    return best if best and best[1] >= _TMDB_SURE else None


_TMDB_SURE = 60

# "Season 3 Part 2", "2nd Season", "Part 2", "Cour 2", "The Final Season", "Final Chapters".
_SEASON_WORDS = re.compile(
    r"[\s:\-]*(?:\b(?:season|series)\s*\d+\b.*|\b\d+(?:st|nd|rd|th)\s+season\b.*|\bpart\s*\d+\b.*"
    r"|\bcour\s*\d+\b.*|\b(?:the\s+)?final\s+(?:season|chapters?)\b.*)$",
    re.IGNORECASE,
)


def base_title(title: str) -> str:
    """The show's name without the season or part: "Attack on Titan Season 3 Part 2" is
    "Attack on Titan"."""
    stripped = _SEASON_WORDS.sub("", title).strip(" :-")
    return stripped or title


def normalize(text: str) -> str:
    """A name reduced to what matters for comparing: letters and digits in lower case."""
    folded = unicodedata.normalize("NFKC", text).casefold().replace("&", " and ")
    folded = re.sub(r"['\u2019`]", "", folded)  # apostrophes, straight or curly: "Heaven's"
    return " ".join(re.sub(r"[^\w]+", " ", folded).split())


def similarity(a: str, b: str) -> float:
    """How alike two names are, from 0 to 1. One name's words all inside the other's count too:
    "Bebop" is in "Cowboy Bebop", though less than the full name."""
    left, right = normalize(a), normalize(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    ratio = SequenceMatcher(None, left, right).ratio()
    words_left, words_right = set(left.split()), set(right.split())
    shorter, longer = sorted((words_left, words_right), key=len)
    contained = 0.9 * len(shorter) / len(longer) if shorter <= longer else 0.0
    return max(ratio, contained)


def _episodes(count: int) -> str:
    return f"{count} episode" if count == 1 else f"{count} episodes"
