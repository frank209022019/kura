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

from kura.artwork_files import forget_artwork
from kura.changes import (
    SavedChange,
    apply_plan,
    remove_emptied,
    save_plan,
    tally,
    undo_plan,
)
from kura.convert import label_of
from kura.core.copies import Copy
from kura.core.extensions import is_video
from kura.core.library import QUARANTINE_FOLDER
from kura.core.media import MediaInfo, media_from_ffprobe
from kura.core.names import film_part
from kura.core.plan import (
    KEPT_BOTH,
    Change,
    ChangeKind,
    EpisodeOf,
    Identity,
    MovieOf,
    PlacedFile,
    Plan,
    copy_key,
    plan_set_aside,
    plan_tidy,
    sidecars_of,
)
from kura.core.report import GAP_ANALYSIS_FILE
from kura.preferences import names_kept
from kura.reports import write_reports

type Category = Literal["rename", "mixed", "duplicate"]

# TMDB's name for an episode it has no title for: no title, in a file's name.
_PLACEHOLDER = re.compile(r"^Episode \d+$")


# What the file at a taken name does in the same tidy-up: stays, leaves, or arrives there.
type Goes = Literal["stays", "leaves", "arrives"]


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
class Proposed:
    """A change Kura proposes, with what the tidy-up screen shows of it."""

    change: Change
    root: Path  # the library folder it's in
    category: Category  # a rename in place, a move out of a folder of several anime, or a copy
    title_id: int
    title: str
    video: Path  # the video the change is of: itself, or the one subtitles go with
    # A name another file had, so it gets "(2)": the file there (one in the library, or another
    # video going there; None when Kura doesn't know it), this one, to compare, and what the one
    # there does in the same tidy-up.
    compared: tuple[CopyFacts | None, CopyFacts, Goes] | None = None


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


class ConvertingError(Exception):
    """A video being converted can't be deleted till it's done. The message says which."""


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
    files = {
        row["path"].casefold(): row
        for row in conn.execute("SELECT path, probe, problem FROM files WHERE gone_at IS NULL")
    }
    taken = [row["path"] for row in files.values()]
    plan = plan_tidy(
        [video.placed for video in videos],
        PureWindowsPath(),  # every video names its own library folder
        day=day,
        taken=taken + _set_aside({video.placed.copy.path.anchor for video in videos}, day),
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
    going = {
        str(c.target).casefold(): _owner(c, of) for c in plan.changes if c.kind is ChangeKind.MOVE
    }
    leaving = {str(c.source).casefold() for c in plan.changes}  # what moves or is set aside
    folders: dict[str, dict[str, str]] = {}
    proposed: list[Proposed] = []
    for change in plan.changes:
        video = _owner(change, of)
        if video.id in linked:
            continue
        compared = None
        if change.reason.endswith(KEPT_BOTH):
            there, goes = _there(change, files, going, leaving)
            compared = (there, _facts(video.placed.copy), goes)
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
        proposed.append(
            Proposed(
                change,
                root,
                category,
                video.title_id,
                video.title,
                Path(video.placed.copy.path),
                compared,
            )
        )
    left = [(Path(video.placed.copy.path), _LINKED) for video in videos if video.id in linked]
    return Proposal(
        tuple(proposed),
        tuple(skipped) + tuple((Path(path), reason) for path, reason in plan.skipped) + tuple(left),
        _duplicates(videos, plan),
    )


_LINKED = "Its new folder is a link to another place, which scans skip"

# The kind of job busy with a video ('convert' or 'subtitles'), if one is: being made, putting
# its result in place, or made and waiting for another app to let go of the video.
_BUSY = """(SELECT j.kind FROM jobs AS j
            WHERE j.file_id = f.id
              AND (j.state IN ('running', 'replacing')
                   OR (j.state = 'queued' AND j.retry_at IS NOT NULL))
            ORDER BY j.kind = 'subtitles' LIMIT 1)"""


def _owner(change: Change, of: dict[str, _Video]) -> _Video:
    """The video a change is of: the one it moves, or the one its subtitles go with."""
    return of[str(change.of or change.source).casefold()]


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
        video = _owner(change, of)
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


def _set_aside(drives: Iterable[str], day: date) -> list[str]:
    """What the quarantine folders hold already today, on these drives: a copy set aside now
    never takes the name of one set aside earlier."""
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
    # Subtitles go only with their video: one the owner left out keeps its subtitles with it.
    left_out = {key for key in now_proposed if key not in wanted}
    chosen = [
        p
        for p in proposal.changes
        if str(p.change.source).casefold() in wanted and str(p.video).casefold() not in left_out
    ]
    plan_id = save_plan(conn, Plan(tuple(p.change for p in chosen)), _plan_title(chosen), now=now)
    outcome = apply_plan(conn, plan_id, now=now)
    _clear_behind(conn, [change.source for change in outcome.changed])
    write_reports(conn, now=now)
    return Tidied(plan_id, *tally(outcome.changed), outcome.problems)


def delete(conn: sqlite3.Connection, file_ids: Iterable[int], *, now: datetime) -> Tidied:
    """Deletes the videos the owner chose, the way Kura deletes: each goes to the quarantine on
    its own drive with the subtitles named after it, journaled so History can put it back till
    the quarantine is cleared out. Folders it empties go, as after a tidy-up. A video waiting to
    be converted leaves the queue; one being converted, or getting English subtitles, stays
    (ConvertingError), and so does everything else asked for."""
    ids = list(dict.fromkeys(file_ids))
    marks = ", ".join("?" * len(ids))
    rows = conn.execute(
        f"""SELECT f.id, f.path, f.season, f.episode, t.name AS title, {_BUSY} AS busy
            FROM files AS f LEFT JOIN titles AS t ON t.id = f.title_id
            WHERE f.id IN ({marks}) AND f.gone_at IS NULL
            ORDER BY f.path""",  # noqa: S608 - only placeholders go in
        ids,
    ).fetchall()
    if not rows:
        return Tidied(None, 0, 0, ())
    if busy := [row for row in rows if row["busy"]]:
        doing = (
            "is getting English subtitles"
            if busy[0]["busy"] == "subtitles"
            else "is being converted"
        )
        raise ConvertingError(
            f"{label_of(busy[0])} {doing}. Skip it in the queue, or delete it once it's done."
        )
    listings: dict[Path, list[str]] = {}
    videos: list[tuple[PurePath, str, Sequence[PurePath]]] = []
    going = {row["path"].casefold() for row in rows}
    claimed: set[str] = set()  # subtitles two copies share go once, with the first
    for row in rows:
        path = Path(row["path"])
        if path.parent not in listings:
            listings[path.parent] = _listing(path.parent)
        listing = listings[path.parent]
        sidecars = [
            sidecar
            for sidecar in sidecars_of(path, listing)
            if str(sidecar).casefold() not in claimed
            and not _shared_with_staying(path, sidecar, listing, going)
        ]
        claimed.update(str(sidecar).casefold() for sidecar in sidecars)
        videos.append((path, label_of(row), sidecars))
    day = now.date()
    taken = _set_aside({video.anchor for video, _, _ in videos}, day)
    plan = plan_set_aside(videos, day=day, taken=taken)
    plan_id = save_plan(conn, plan, _deleted_title(rows), now=now)
    with conn:  # out of the queue's reach while they move: none starts converting meanwhile
        waiting = conn.execute(
            f"""UPDATE jobs SET state = 'skipped'
                WHERE state = 'queued' AND file_id IN ({marks})
                RETURNING id, file_id""",  # noqa: S608 - only placeholders go in
            ids,
        ).fetchall()
    outcome = apply_plan(conn, plan_id, now=now)
    deleted = {str(change.source) for change in outcome.changed}
    gone = {row["id"] for row in rows if str(Path(row["path"])) in deleted}
    with conn:  # a video gone leaves the queue; one that stayed waits in it again
        for job in waiting:
            if job["file_id"] in gone:
                conn.execute("DELETE FROM jobs WHERE id = ?", (job["id"],))
            else:
                conn.execute("UPDATE jobs SET state = 'queued' WHERE id = ?", (job["id"],))
    _clear_behind(conn, [change.source for change in outcome.changed])
    write_reports(conn, now=now)
    return Tidied(plan_id, *tally(outcome.changed), outcome.problems)


def _shared_with_staying(
    video: Path, sidecar: PurePath, listing: list[str], going: set[str]
) -> bool:
    """Whether another copy of the video beside it (the same name, another kind of file) stays,
    and the subtitles fit it as well: they stay with it."""
    return any(
        is_video(name)
        and PurePath(name).stem.casefold() == video.stem.casefold()
        and str(video.parent / name).casefold() not in going
        and sidecar in sidecars_of(video.parent / name, listing)
        for name in listing
    )


def undo(conn: sqlite3.Connection, plan_id: int, *, now: datetime) -> Tidied:
    """Puts back what a tidy-up moved, newest first, but a video being converted (or its result
    waiting beside it) stays, with its subtitles. Asked again, it puts back what couldn't go back
    the first time."""
    busy = {
        row["path"].casefold(): row["kind"]
        for row in conn.execute(
            """SELECT f.path, j.kind FROM jobs AS j JOIN files AS f ON f.id = j.file_id
               WHERE j.state IN ('running', 'replacing')
                  OR (j.state = 'queued' AND j.retry_at IS NOT NULL)"""
        )
    }

    def held(change: SavedChange) -> str | None:
        kind = busy.get(str(change.target).casefold())
        if kind == "subtitles":
            return "Its English subtitles are being made: put it back once they're done."
        if kind is not None:
            return "It's being converted: put it back once it's done."
        return None

    outcome = undo_plan(conn, plan_id, now=now, held=held)
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
        f"""SELECT f.id, f.path, f.probe, f.problem, f.season, f.episode, f.episode_end,
                  t.id AS title_id, t.name, t.year, t.kind, t.tmdb_type, d.path AS root,
                  {_BUSY} AS busy
           FROM files AS f
           JOIN titles AS t ON t.id = f.title_id
           JOIN folders AS d ON d.id = f.folder_id
           WHERE f.gone_at IS NULL AND f.matched = 'sure'
           ORDER BY f.path"""  # noqa: S608 - only Kura's own SQL goes in
    ).fetchall()
    parted = _films_in_parts(rows)
    listings: dict[str, list[str]] = {}
    connected: dict[str, bool] = {}
    videos: list[_Video] = []
    skipped: list[tuple[Path, str]] = []
    converting: set[tuple[object, ...]] = set()  # what the videos being converted are
    for row in rows:
        if row["root"] not in connected:
            connected[row["root"]] = Path(row["root"]).is_dir()
        if not connected[row["root"]]:
            skipped.append((Path(row["path"]), "Its library folder isn't connected"))
            continue
        identity = _identity(row, names, parted)
        if row["busy"] == "subtitles":  # they're written beside it, under its name as it is
            skipped.append((Path(row["path"]), "Its English subtitles are being made"))
            continue
        if row["busy"]:
            skipped.append((Path(row["path"]), "It's being converted"))
            if identity is not None:
                converting.add(copy_key(identity))
            continue
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
    # Copies of a video being converted wait for it: its result may take the name they'd be
    # filed under, and once it's in place the next tidy-up chooses between them.
    held = {video.id for video in videos if copy_key(video.placed.identity) in converting}
    skipped += [
        (Path(video.placed.copy.path), "A copy of it is being converted")
        for video in videos
        if video.id in held
    ]
    return [video for video in videos if video.id not in held], skipped


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


def _there(
    change: Change, files: dict[str, sqlite3.Row], going: dict[str, _Video], leaving: set[str]
) -> tuple[CopyFacts | None, Goes]:
    """The file at the name a change wanted, which it gets "(2)" beside: one in the library
    (which stays, or leaves in the same tidy-up), or another video filed there in it."""
    target = PureWindowsPath(change.target)
    wanted = str(target.with_name(_NUMBERED.sub("", target.stem) + target.suffix)).casefold()
    if (row := files.get(wanted)) is not None:
        path = PureWindowsPath(row["path"])
        facts = _facts(Copy(path, _media(row["probe"]), broken=row["problem"] is not None))
        return facts, "leaves" if wanted in leaving else "stays"
    if (video := going.get(wanted)) is not None:
        return _facts(video.placed.copy), "arrives"
    return None, "stays"


_NUMBERED = re.compile(r" \(\d+\)$")  # the "(2)" a name gets beside a file that has it


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
    """ "Renamed 26 Cowboy Bebop files", or "Tidied 30 files: Cowboy Bebop, Death Note
    and 2 more", as History lists it."""
    count = len(chosen)
    titles = list(dict.fromkeys(p.title for p in chosen))
    files = "file" if count == 1 else "files"
    if len(titles) == 1 and all(p.category == "rename" for p in chosen):
        return f"Renamed {count} {titles[0]} {files}"
    named = titles[:2]
    more = len(titles) - len(named)
    listed = f"{', '.join(named)} and {more} more" if more else " and ".join(named)
    return f"Tidied {count} {files}: {listed}"


def _deleted_title(rows: Sequence[sqlite3.Row]) -> str:
    """ "Deleted Trigun · S01E03", "Deleted 26 Trigun files", or "Deleted 30 files: Trigun,
    Cowboy Bebop and 2 more", as History lists it."""
    if len(rows) == 1:
        return f"Deleted {label_of(rows[0])}"
    titles = list(dict.fromkeys(row["title"] for row in rows if row["title"]))
    if len(titles) == 1 and all(row["title"] for row in rows):
        return f"Deleted {len(rows)} {titles[0]} files"
    if not titles:
        return f"Deleted {len(rows)} files"
    named = titles[:2]
    more = len(titles) - len(named)
    listed = f"{', '.join(named)} and {more} more" if more else " and ".join(named)
    return f"Deleted {len(rows)} files: {listed}"


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
    empty = [folder for folder in folders if not _holds_videos(folder)]
    for folder in sorted(empty, key=lambda f: len(f.parts), reverse=True):
        (folder / GAP_ANALYSIS_FILE).unlink(missing_ok=True)
    forget_artwork(conn, empty)  # the pictures Kura put next to a show that's gone from here
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
