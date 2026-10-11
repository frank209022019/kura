"""The library folders, and the videos in them, as the database keeps them.

A scan (kura/scan.py) fills this in: `find_files` walks a folder and records each video with its
size and time, then `read_file` saves what ffprobe says about each one still to read. Files never
change here: this only looks.
"""

import json
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath

from kura.core.library import Covered, Holds, fits, is_video, skipped_folder
from kura.core.media import Json, media_from_ffprobe
from kura.probe import ProbeError

_COMMIT_EVERY = 200  # files recorded between commits while walking a folder


class FolderError(Exception):
    """A folder that can't go in the library, with a sentence saying why."""


@dataclass(frozen=True)
class Folder:
    id: int
    path: Path
    added_at: str


@dataclass(frozen=True)
class Found:
    """What walking one folder found."""

    files: int  # videos found
    added: int  # new to the library
    changed: int  # a different size or time from before, so read again
    gone: int  # no longer there
    problems: tuple[str, ...]  # folders inside that couldn't be opened


def folders(conn: sqlite3.Connection) -> list[Folder]:
    rows = conn.execute("SELECT id, path, added_at FROM folders ORDER BY path").fetchall()
    return [Folder(row["id"], Path(row["path"]), row["added_at"]) for row in rows]


def add_folder(conn: sqlite3.Connection, path: Path, *, now: datetime) -> Folder:
    """Adds a folder to the library. A folder that holds library folders takes them in."""
    path = Path(os.path.normpath(path.absolute()))
    if not path.is_dir():
        raise FolderError(
            f"{path} isn't there. Check the drive is connected and the folder exists."
        )
    existing = {PureWindowsPath(folder.path): folder for folder in folders(conn)}
    match fits(PureWindowsPath(path), existing):
        case Covered(by=by) if PureWindowsPath(path) == by:
            raise FolderError(f"{existing[by].path} is already in your library.")
        case Covered(by=by):
            raise FolderError(f"{path} is already in your library, as part of {existing[by].path}.")
        case Holds(folders=held):
            absorbed = [existing[inner].id for inner in held]
        case None:
            absorbed = []
    with conn:
        folder_id: int = conn.execute(
            "INSERT INTO folders (path, added_at) VALUES (?, ?) RETURNING id",
            (str(path), now.isoformat()),
        ).fetchone()[0]
        for inner in absorbed:
            conn.execute("UPDATE files SET folder_id = ? WHERE folder_id = ?", (folder_id, inner))
            conn.execute("DELETE FROM folders WHERE id = ?", (inner,))
    return Folder(folder_id, path, now.isoformat())


def remove_folder(conn: sqlite3.Connection, folder_id: int) -> bool:
    """Forgets a folder and what Kura knew about its files. The files themselves stay put."""
    with conn:
        removed = conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,)).rowcount
    return removed > 0


def find_files(
    conn: sqlite3.Connection,
    folder: Folder,
    *,
    stamp: str,
    on_file: Callable[[Path], None] = lambda _: None,
    stop: Callable[[], bool] = lambda: False,
) -> Found | None:
    """Walks a library folder and records every video in it.

    `stamp` names the scan; files it doesn't see are marked gone. Returns None, changing nothing,
    when the folder isn't there (its drive unplugged, say), or when `stop` asks to stop.
    """
    if not folder.path.is_dir():
        return None
    files = added = changed = 0
    problems: list[str] = []
    waiting = [folder.path]
    while waiting:
        current = waiting.pop()
        try:
            with os.scandir(current) as entries:
                listed = sorted(entries, key=lambda entry: entry.name.casefold(), reverse=True)
        except OSError as error:
            problems.append(f"Kura couldn't look in {current}: {error.strerror or error}.")
            continue
        for entry in listed:
            if entry.is_dir(follow_symlinks=False):
                if not skipped_folder(entry.name):
                    waiting.append(Path(entry.path))
            elif entry.is_file(follow_symlinks=False) and is_video(entry.name):
                if stop():
                    conn.commit()
                    return None
                path = Path(entry.path)
                on_file(path)
                stat = entry.stat(follow_symlinks=False)
                outcome = _record(conn, folder.id, path, stat.st_size, stat.st_mtime_ns, stamp)
                files += 1
                added += outcome == "added"
                changed += outcome == "changed"
                if files % _COMMIT_EVERY == 0:
                    conn.commit()
    with conn:
        gone = conn.execute(
            "UPDATE files SET gone_at = ? WHERE folder_id = ? AND gone_at IS NULL AND seen_at <> ?",
            (stamp, folder.id, stamp),
        ).rowcount
    return Found(files, added, changed, gone, tuple(problems))


def unread(conn: sqlite3.Connection) -> list[tuple[int, Path]]:
    """Files still to read with ffprobe, in path order."""
    rows = conn.execute(
        "SELECT id, path FROM files WHERE probed_at IS NULL AND gone_at IS NULL ORDER BY path"
    ).fetchall()
    return [(row["id"], Path(row["path"])) for row in rows]


def read_file(
    conn: sqlite3.Connection,
    file_id: int,
    path: Path,
    read: Callable[[Path], Json],
    *,
    now: datetime,
) -> str | None:
    """Reads one file and saves what it holds. Returns why it couldn't be read, or None."""
    try:
        report = read(path)
    except ProbeError as error:
        with conn:
            conn.execute(
                "UPDATE files SET probed_at = ?, problem = ? WHERE id = ?",
                (now.isoformat(), str(error), file_id),
            )
        return str(error)
    media = media_from_ffprobe(report)
    video = media.video
    with conn:
        conn.execute(
            """UPDATE files
               SET probed_at = ?, probe = ?, problem = NULL,
                   duration = ?, width = ?, height = ?, codec = ?
               WHERE id = ?""",
            (
                now.isoformat(),
                json.dumps(report, separators=(",", ":")),
                media.duration,
                video.width if video else None,
                video.height if video else None,
                video.codec if video else None,
                file_id,
            ),
        )
    return None


def _record(
    conn: sqlite3.Connection, folder_id: int, path: Path, size: int, modified: int, stamp: str
) -> str:
    """Saves one found file. Returns "added", "changed" or "same"."""
    before = conn.execute(
        "SELECT size, modified FROM files WHERE path = ?", (str(path),)
    ).fetchone()
    if before is None:
        conn.execute(
            """INSERT INTO files (folder_id, path, size, modified, found_at, seen_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (folder_id, str(path), size, modified, stamp, stamp),
        )
        return "added"
    if (before["size"], before["modified"]) == (size, modified):
        conn.execute(
            "UPDATE files SET folder_id = ?, seen_at = ?, gone_at = NULL WHERE path = ?",
            (folder_id, stamp, str(path)),
        )
        return "same"
    conn.execute(
        """UPDATE files
           SET folder_id = ?, size = ?, modified = ?, seen_at = ?, gone_at = NULL,
               probed_at = NULL, probe = NULL, problem = NULL,
               duration = NULL, width = NULL, height = NULL, codec = NULL
           WHERE path = ?""",
        (folder_id, size, modified, stamp, str(path)),
    )
    return "changed"
