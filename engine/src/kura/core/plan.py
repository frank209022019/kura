"""Tidying up: where every identified file should go, as a list of proposed changes.

Nothing moves here. A plan is shown for review first, then applied, logged and undoable
(see kura/changes.py). Duplicates go to a quarantine folder on the same drive, never straight
to deletion, and no file is ever overwritten.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import PurePath

from kura.core.copies import Copy, choose_copy
from kura.core.extensions import is_subtitle, is_video
from kura.core.naming import PathTooLongError, episode_path, movie_path, unique_path

QUARANTINE_FOLDER = "Kura quarantine"


@dataclass(frozen=True)
class EpisodeOf:
    show: str
    year: int | None
    season: int
    episode: int
    last_episode: int | None = None
    title: str | None = None


@dataclass(frozen=True)
class MovieOf:
    title: str
    year: int | None


type Identity = EpisodeOf | MovieOf


@dataclass(frozen=True)
class PlacedFile:
    """A file and what it was identified as."""

    copy: Copy
    identity: Identity
    sidecars: tuple[PurePath, ...] = ()  # subtitles beside it, named after it (see sidecars_of)
    root: PurePath | None = None  # its library folder, which it's filed under (else plan_tidy's)


def sidecars_of(video: PurePath, names: Iterable[str]) -> tuple[PurePath, ...]:
    """The subtitle files among `names` (a folder's contents) named after `video`.

    `Episode 1.en.srt` belongs to `Episode 1.mkv`, and `Episode 10.en.srt` doesn't. When two
    videos' names both fit (`Show - 12` and `Show - 12.5`), the longer one gets it.
    """
    listed = list(names)
    own = video.stem.casefold()
    stems = {own} | {PurePath(name).stem.casefold() for name in listed if is_video(name)}
    found: list[PurePath] = []
    for name in listed:
        if not is_subtitle(name):
            continue
        fits = [stem for stem in stems if name.casefold().startswith(stem + ".")]
        if fits and max(fits, key=len) == own:
            found.append(video.parent / name)
    return tuple(sorted(found, key=lambda path: path.name.casefold()))


class ChangeKind(StrEnum):
    MOVE = "move"  # rename or move into the library's layout
    QUARANTINE = "quarantine"  # set aside, kept for a while, then deleted


@dataclass(frozen=True)
class Change:
    kind: ChangeKind
    source: PurePath
    target: PurePath
    label: str  # "Death Note · S01E07", "Cowboy Bebop: The Movie"
    reason: str


@dataclass(frozen=True)
class Plan:
    changes: tuple[Change, ...]
    skipped: tuple[tuple[PurePath, str], ...] = ()  # files left where they are, and why


def plan_tidy(
    files: Sequence[PlacedFile],
    library: PurePath,
    *,
    day: date,
    taken: Iterable[str] = (),
    keep: Iterable[PurePath] = (),
) -> Plan:
    """The changes that put `files` in Plex's layout under their library folder (`library`, unless
    a file names its own).

    `taken` holds the paths already in use on disk. Every file's current path counts as taken
    too, so a new name never lands on a file that is still there. `keep` holds copies the owner
    chose to keep over the others of the same episode or movie.
    """
    chosen = {str(path).casefold() for path in keep}
    used = {path.casefold() for path in taken} | {str(f.copy.path).casefold() for f in files}
    groups: dict[tuple[object, ...], list[PlacedFile]] = {}
    for placed in files:  # copies of the same episode or movie, whatever their format
        groups.setdefault(_same(placed.identity), []).append(placed)

    quarantines: list[Change] = []
    moves: list[Change] = []
    skipped: list[tuple[PurePath, str]] = []
    for group in groups.values():
        kept = group[0]
        if len(group) > 1:
            choice = choose_copy([placed.copy for placed in group])
            kept = next(placed for placed in group if placed.copy is choice.keep)
            why = _lowercase_first(choice.reason)
            if owners := [p for p in group if str(p.copy.path).casefold() in chosen]:
                kept, why = owners[0], "you chose it"
            reason = f"Kept {kept.copy.path.name} instead: {why}"
            for dropped in group:
                if dropped is not kept:
                    place = unique_path(_quarantine_place(dropped.copy.path, day), used)
                    used.add(str(place).casefold())
                    label = f"{_label(dropped.identity)} · duplicate"
                    quarantines.append(
                        Change(ChangeKind.QUARANTINE, dropped.copy.path, place, label, reason)
                    )
                    quarantines.extend(
                        _with_it(dropped, place, used, ChangeKind.QUARANTINE, reason)
                    )
        try:
            target = _target(kept, kept.root or library)
        except PathTooLongError:
            skipped.append((kept.copy.path, "The new name would be too long for Windows"))
            continue
        if move := _move(kept, target, used):
            moves.append(move)
            moves.extend(_with_it(kept, move.target, used, ChangeKind.MOVE, "Follows its video"))
    moves.sort(key=lambda change: str(change.target).casefold())
    return Plan(tuple(quarantines + moves), tuple(skipped))


def _move(placed: PlacedFile, target: PurePath, used: set[str]) -> Change | None:
    source = placed.copy.path
    if str(source) == str(target):
        return None  # already exactly right
    if str(source).casefold() == str(target).casefold():
        place = target  # only the case changes: the name is its own
    else:
        place = unique_path(target, used)
        used.add(str(place).casefold())
    reason = "Named for Plex"
    if place != target:
        reason += ". A file with this name is already there; both are kept"
    return Change(ChangeKind.MOVE, source, place, _label(placed.identity), reason)


def _with_it(
    placed: PlacedFile, place: PurePath, used: set[str], kind: ChangeKind, reason: str
) -> list[Change]:
    """Moves for a file's subtitles, renamed to match where the file itself goes."""
    changes: list[Change] = []
    for sidecar in placed.sidecars:
        tail = sidecar.name[len(placed.copy.path.stem) :]  # ".en.srt"
        target = place.with_name(place.stem + tail)
        if str(sidecar) == str(target):
            continue  # already right
        if str(sidecar).casefold() == str(target).casefold():
            spot = target  # only the case changes: the name is its own
        else:
            spot = unique_path(target, used)
            used.add(str(spot).casefold())
        label = f"{_label(placed.identity)} · subtitles"
        changes.append(Change(kind, sidecar, spot, label, reason))
    return changes


def _target(placed: PlacedFile, library: PurePath) -> PurePath:
    extension = placed.copy.path.suffix.lower()
    match placed.identity:
        case EpisodeOf() as episode:
            return episode_path(
                library,
                episode.show,
                episode.year,
                season=episode.season,
                episode=episode.episode,
                last_episode=episode.last_episode,
                title=episode.title,
                extension=extension,
            )
        case MovieOf() as movie:
            return movie_path(library, movie.title, movie.year, extension=extension)


def _same(identity: Identity) -> tuple[object, ...]:
    """What makes two files copies of each other: the same episode, or the same movie."""
    match identity:
        case EpisodeOf() as episode:
            return (
                "episode",
                episode.show.casefold(),
                episode.year,
                episode.season,
                episode.episode,
            )
        case MovieOf() as movie:
            return ("movie", movie.title.casefold(), movie.year)


def _quarantine_place(source: PurePath, day: date) -> PurePath:
    r"""D:\Kura quarantine\2026-10-10\name.mkv: on the file's own drive, so moving is instant."""
    return type(source)(source.anchor) / QUARANTINE_FOLDER / day.isoformat() / source.name


def _label(identity: Identity) -> str:
    match identity:
        case EpisodeOf() as episode:
            code = f"S{episode.season:02d}E{episode.episode:02d}"
            if episode.last_episode is not None:
                code += f"-E{episode.last_episode:02d}"
            return f"{episode.show} · {code}"
        case MovieOf() as movie:
            return movie.title


def _lowercase_first(text: str) -> str:
    return text[:1].lower() + text[1:]
