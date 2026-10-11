"""Tidying up: the plan that files the library the way Plex reads it, and carrying it out.

kura/core/plan.py decides where every identified video goes. This module gathers what it needs
from the library (each title's name, year and episode titles, the copies of each episode, the
subtitles beside each video, the paths in use), says which changes rename files in place and
which move them out of a folder holding several anime, and applies the ones the owner keeps,
exactly as they were reviewed, journaled and undoable (kura/changes.py). Each video's record
moves with it, so it keeps what it was identified as; folders a tidy-up empties go, with the gap
analysis Kura had written in them, and the reports are written again where the shows are now.
"""

import json
import os
import re
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path, PurePath, PureWindowsPath
from typing import Literal

from kura.changes import (
    SavedChange,
    apply_plan,
    remove_emptied,
    save_plan,
    tally,
    undo_plan,
)
from kura.core.copies import Copy
from kura.core.extensions import is_video
from kura.core.library import QUARANTINE_FOLDER
from kura.core.media import MediaInfo, media_from_ffprobe
from kura.core.names import film_part
from kura.core.plan import (
    Change,
    ChangeKind,
    EpisodeOf,
    Identity,
    MovieOf,
    PlacedFile,
    Plan,
    copy_key,
    plan_tidy,
    sidecars_of,
)
from kura.core.report import GAP_ANALYSIS_FILE
from kura.preferences import names_kept
from kura.reports import write_reports

type Category = Literal["rename", "mixed", "duplicate"]

# TMDB's name for an episode it has no title for: no title, in a file's name.
_PLACEHOLDER = re.compile(r"^Episode \d+$")


@dataclass(frozen=True)
class Proposed:
    """A change Kura proposes, with what the tidy-up screen shows of it."""

    change: Change
    root: Path  # the library folder it's in
    category: Category  # a rename in place, a move out of a folder of several anime, or a copy
    title_id: int
    title: str


@dataclass(frozen=True)
class CopyFacts:
    """What decides between two copies of one episode, as the screen compares them."""

    path: Path
    height: int | None
    codec: str | None
    audio: tuple[str, ...]  # languages
    subtitles: int  # tracks that can be switched off
    size: int
    plays: bool


@dataclass(frozen=True)
class Duplicate:
    """Copies of one episode or movie: the one Kura keeps, and the ones it sets aside."""

    label: str
    keep: CopyFacts
    drop: tuple[CopyFacts, ...]
    reason: str


@dataclass(frozen=True)
class Proposal:
    changes: tuple[Proposed, ...]
    skipped: tuple[tuple[Path, str], ...]  # videos left where they are, and why
    duplicates: tuple[Duplicate, ...]


@dataclass(frozen=True)
class Reviewed:
    """A change as the owner saw it on the tidy-up screen."""

    source: str
    kind: ChangeKind
    target: str


class ProposalChangedError(Exception):
    """A change the owner reviewed isn't what Kura proposes now (a scan or a new match changed
    it), so nothing was made."""


@dataclass(frozen=True)
class Tidied:
    """What applying or undoing a tidy-up did."""

    plan_id: int | None  # None when nothing was asked for
    moved: int  # videos and subtitles filed, or put back
    quarantined: int  # copies set aside, or put back (a copy's subtitles go with it uncounted)
    problems: tuple[SavedChange, ...]  # changes that couldn't be made, each saying why


@dataclass(frozen=True)
class _Video:
    id: int
    title_id: int
    title: str
    placed: PlacedFile


def propose(conn: sqlite3.Connection, *, day: date, keep: Iterable[str] = ()) -> Proposal:
    """The changes that would file every identified video for Plex. Nothing changes on disk.
    `keep` holds the copies the owner chose to keep over others of the same episode."""
    videos, skipped = _videos(conn)
    taken = [row["path"] for row in conn.execute("SELECT path FROM files WHERE gone_at IS NULL")]
    plan = plan_tidy(
        [video.placed for video in videos],
        PureWindowsPath(),  # every video names its own library folder
        day=day,
        taken=taken + _set_aside(videos, day),
        keep=[PureWindowsPath(path) for path in keep],
        keep_names=names_kept(conn),
    )
    of: dict[str, _Video] = {}
    for video in videos:
        of[str(video.placed.copy.path).casefold()] = video
        for sidecar in video.placed.sidecars:
            of[str(sidecar).casefold()] = video
    linked = _into_links(plan, of)
    mixed = _mixed_folders(conn)
    folders: dict[str, dict[str, str]] = {}
    proposed: list[Proposed] = []
    for change in plan.changes:
        video = of[str(change.source).casefold()]
        if video.id in linked:
            continue
        category: Category = (
            "duplicate"
            if change.kind is ChangeKind.QUARANTINE
            else "mixed"
            if str(change.source.parent).casefold() in mixed
            else "rename"
        )
        root = Path(video.placed.root or "")
        if change.kind is ChangeKind.MOVE:
            change = replace(change, target=_as_spelled(change.target, root, folders))
        proposed.append(Proposed(change, root, category, video.title_id, video.title))
    left = [(Path(video.placed.copy.path), _LINKED) for video in videos if video.id in linked]
    return Proposal(
        tuple(proposed),
        tuple(skipped) + tuple((Path(path), reason) for path, reason in plan.skipped) + tuple(left),
        _duplicates(videos, plan),
    )


_LINKED = "Its new folder is a link to another place, which scans skip"


def _into_links(plan: Plan, of: dict[str, _Video]) -> set[int]:
    """The videos the plan would move into a link or junction inside their library folder. Scans
    don't follow links (they can lead anywhere), so a video filed there would seem to have gone."""
    checked: dict[Path, bool] = {}

    def linked(folder: Path, root: Path) -> bool:
        if folder == root or not folder.is_relative_to(root):
            return False
        if folder not in checked:
            checked[folder] = (
                folder.is_junction() or folder.is_symlink() or linked(folder.parent, root)
            )
        return checked[folder]

    found: set[int] = set()
    for change in plan.changes:
        video = of[str(change.source).casefold()]
        root = Path(video.placed.root or "")
        if change.kind is ChangeKind.MOVE and linked(Path(change.target).parent, root):
            found.add(video.id)
    return found


def _as_spelled(target: PurePath, root: Path, folders: dict[str, dict[str, str]]) -> PurePath:
    """A new place, with each folder on the way that's there already spelled as it is on disk
    ("cowboy bebop (1998)", say): Windows would put the file in it anyway, and the library's
    record then names the file exactly as the disk does. `folders` keeps what was looked at."""
    try:
        inside = PureWindowsPath(target).relative_to(root)
    except ValueError:
        return target
    folder = PureWindowsPath(root)
    for name in inside.parts[:-1]:
        key = str(folder).casefold()
        if key not in folders:
            folders[key] = _folders_in(Path(folder))
        folder /= folders[key].get(name.casefold(), name)
    return folder / inside.name


def _folders_in(folder: Path) -> dict[str, str]:
    """The folders in a folder, by their names in lower case."""
    try:
        with os.scandir(folder) as entries:
            return {entry.name.casefold(): entry.name for entry in entries if entry.is_dir()}
    except OSError:
        return {}  # not there yet, or can't be read


def _set_aside(videos: Sequence[_Video], day: date) -> list[str]:
    """What the quarantine folders hold already today, on the drives the videos are on: a copy
    set aside now never takes the name of one set aside earlier."""
    drives = {video.placed.copy.path.anchor for video in videos}
    return [
        str(path)
        for drive in sorted(drives)
        for path in _paths(Path(drive) / QUARANTINE_FOLDER / day.isoformat())
    ]


def apply(
    conn: sqlite3.Connection,
    reviewed: Iterable[Reviewed],
    *,
    now: datetime,
    keep: Iterable[str] = (),
) -> Tidied:
    """Makes these changes (of videos, and the subtitles that go with them) exactly as the owner
    reviewed them; anything else in the library stays as it is. Kura proposes them again first,
    and makes none (ProposalChangedError) if any isn't proposed as it was."""
    wanted = {change.source.casefold(): change for change in reviewed}
    if not wanted:
        return Tidied(None, 0, 0, ())
    proposal = propose(conn, day=now.date(), keep=keep)
    now_proposed = {str(p.change.source).casefold(): p.change for p in proposal.changes}
    for source, change in wanted.items():
        found = now_proposed.get(source)
        if found is None or (found.kind, str(found.target)) != (change.kind, change.target):
            raise ProposalChangedError
    chosen = [p for p in proposal.changes if str(p.change.source).casefold() in wanted]
    plan_id = save_plan(conn, Plan(tuple(p.change for p in chosen)), _plan_title(chosen), now=now)
    outcome = apply_plan(conn, plan_id, now=now)
    _clear_behind(conn, [change.source for change in outcome.changed])
    write_reports(conn, now=now)
    return Tidied(plan_id, *tally(outcome.changed), outcome.problems)


def undo(conn: sqlite3.Connection, plan_id: int, *, now: datetime) -> Tidied:
    """Puts back what a tidy-up moved, newest first. Asked again, it puts back what couldn't go
    back the first time."""
    outcome = undo_plan(conn, plan_id, now=now)
    _clear_behind(conn, [change.target for change in outcome.changed])
    write_reports(conn, now=now)
    return Tidied(plan_id, *tally(outcome.changed), outcome.problems)


def _videos(conn: sqlite3.Connection) -> tuple[list[_Video], list[tuple[Path, str]]]:
    """Every identified video with what it is, and the ones Kura can't file, with why."""
    names: dict[tuple[int, int, int], str] = {
        (row["title_id"], row["season"], row["number"]): row["name"]
        for row in conn.execute("SELECT * FROM episodes WHERE name IS NOT NULL")
        if not _PLACEHOLDER.match(row["name"])
    }
    rows = conn.execute(
        """SELECT f.id, f.path, f.probe, f.problem, f.season, f.episode, f.episode_end,
                  t.id AS title_id, t.name, t.year, t.kind, t.tmdb_type, d.path AS root,
                  EXISTS (SELECT 1 FROM jobs AS j
                          WHERE j.file_id = f.id AND j.state IN ('running', 'replacing'))
                      AS converting
           FROM files AS f
           JOIN titles AS t ON t.id = f.title_id
           JOIN folders AS d ON d.id = f.folder_id
           WHERE f.gone_at IS NULL AND f.matched = 'sure'
           ORDER BY f.path"""
    ).fetchall()
    parted = _films_in_parts(rows)
    listings: dict[str, list[str]] = {}
    connected: dict[str, bool] = {}
    videos: list[_Video] = []
    skipped: list[tuple[Path, str]] = []
    for row in rows:
        if row["root"] not in connected:
            connected[row["root"]] = Path(row["root"]).is_dir()
        if not connected[row["root"]]:
            skipped.append((Path(row["path"]), "Its library folder isn't connected"))
            continue
        if row["converting"]:
            skipped.append((Path(row["path"]), "It's being converted"))
            continue
        identity = _identity(row, names, parted)
        if identity is None:
            skipped.append((Path(row["path"]), "Kura doesn't know which episode it is"))
            continue
        path = PureWindowsPath(row["path"])
        folder = str(path.parent)
        if folder not in listings:
            listings[folder] = _listing(Path(folder))
        media = _media(row["probe"])
        placed = PlacedFile(
            Copy(path, media, broken=row["problem"] is not None),
            identity,
            sidecars_of(path, listings[folder]),
            root=PureWindowsPath(row["root"]),
        )
        videos.append(_Video(row["id"], row["title_id"], row["name"], placed))
    return videos, skipped


def _identity(
    row: sqlite3.Row, names: dict[tuple[int, int, int], str], parted: set[int]
) -> Identity | None:
    if _is_movie(row):
        part = _part(row) if row["title_id"] in parted else None
        return MovieOf(row["name"], row["year"], part=part, title_id=row["title_id"])
    if row["season"] is None or row["episode"] is None:
        return None  # a special or extra Kura couldn't number
    return EpisodeOf(
        row["name"],
        row["year"],
        season=row["season"],
        episode=row["episode"],
        last_episode=row["episode_end"],
        title=names.get((row["title_id"], row["season"], row["episode"])),
        title_id=row["title_id"],
    )


def _is_movie(row: sqlite3.Row) -> bool:
    return row["kind"] == "movie" or row["tmdb_type"] == "movie"


def _part(row: sqlite3.Row) -> int | None:
    return film_part(PureWindowsPath(row["path"]).stem)


def _films_in_parts(rows: Iterable[sqlite3.Row]) -> set[int]:
    """The films whose files are its parts (CD1, CD2): two part numbers at least. One file named
    "Part 2" is a whole film, named so."""
    parts: dict[int, set[int]] = {}
    for row in rows:
        if _is_movie(row) and (part := _part(row)) is not None:
            parts.setdefault(row["title_id"], set()).add(part)
    return {title for title, numbers in parts.items() if len(numbers) > 1}


def _mixed_folders(conn: sqlite3.Connection) -> set[str]:
    """Folders holding videos of more than one anime, in lower case."""
    seen: dict[str, set[int]] = {}
    for row in conn.execute(
        "SELECT path, title_id FROM files WHERE gone_at IS NULL AND title_id IS NOT NULL"
    ):
        seen.setdefault(str(PureWindowsPath(row["path"]).parent).casefold(), set()).add(
            row["title_id"]
        )
    return {folder for folder, titles in seen.items() if len(titles) > 1}


def _duplicates(videos: Sequence[_Video], plan: Plan) -> tuple[Duplicate, ...]:
    """The copies the plan sets aside, each beside the one it keeps."""
    set_aside = {
        str(c.source).casefold(): c for c in plan.changes if c.kind is ChangeKind.QUARANTINE
    }
    groups: dict[tuple[object, ...], list[_Video]] = {}
    for video in videos:
        groups.setdefault(copy_key(video.placed.identity), []).append(video)
    found: list[Duplicate] = []
    for group in groups.values():
        dropped = [v for v in group if str(v.placed.copy.path).casefold() in set_aside]
        kept = [v for v in group if str(v.placed.copy.path).casefold() not in set_aside]
        if not dropped or len(kept) != 1:
            continue
        change = set_aside[str(dropped[0].placed.copy.path).casefold()]
        found.append(
            Duplicate(
                label=change.label.removesuffix(" · duplicate"),
                keep=_facts(kept[0].placed.copy),
                drop=tuple(_facts(v.placed.copy) for v in dropped),
                reason=change.reason,
            )
        )
    return tuple(found)


def _facts(copy: Copy) -> CopyFacts:
    media = copy.media
    video = media.video if media else None
    return CopyFacts(
        path=Path(copy.path),
        height=video.height if video else None,
        codec=video.codec if video else None,
        audio=tuple(track.language or "unknown" for track in media.audio) if media else (),
        subtitles=len(media.subtitles) if media else 0,
        size=(media.size or 0) if media else 0,
        plays=not copy.broken and video is not None,
    )


def _plan_title(chosen: Sequence[Proposed]) -> str:
    """ "Renamed 26 Cowboy Bebop files for Plex", or "Tidied 30 files: Cowboy Bebop, Death Note
    and 2 more", as History lists it."""
    count = len(chosen)
    titles = list(dict.fromkeys(p.title for p in chosen))
    files = "file" if count == 1 else "files"
    if len(titles) == 1 and all(p.category == "rename" for p in chosen):
        return f"Renamed {count} {titles[0]} {files} for Plex"
    named = titles[:2]
    more = len(titles) - len(named)
    listed = f"{', '.join(named)} and {more} more" if more else " and ".join(named)
    return f"Tidied {count} {files}: {listed}"


def _clear_behind(conn: sqlite3.Connection, left: Sequence[Path]) -> None:
    """The folders files left: a gap analysis in one that holds no video any more is out of date
    (it's written again where the show is now), and a folder left empty goes."""
    roots = [Path(row["path"]) for row in conn.execute("SELECT path FROM folders")]
    folders: set[Path] = set()
    for path in left:
        folder = path.parent
        while any(folder != root and folder.is_relative_to(root) for root in roots):
            folders.add(folder)
            folder = folder.parent
    for folder in sorted(folders, key=lambda f: len(f.parts), reverse=True):
        report = folder / GAP_ANALYSIS_FILE
        if report.is_file() and not _holds_videos(folder):
            report.unlink(missing_ok=True)
    remove_emptied(conn, folders)


def _holds_videos(folder: Path) -> bool:
    try:
        return any(is_video(name) for _, _, names in os.walk(folder) for name in names)
    except OSError:
        return True  # can't tell: leave it


def _listing(folder: Path) -> list[str]:
    return [path.name for path in _paths(folder)]


def _paths(folder: Path) -> list[Path]:
    try:
        return list(folder.iterdir())
    except OSError:
        return []  # not there, or can't be read


def _media(probe: str | None) -> MediaInfo | None:
    return media_from_ffprobe(json.loads(probe)) if probe else None
