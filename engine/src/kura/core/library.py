"""The library's folders and files: what counts as a video, where a scan never looks, how folders
may sit together, and how long a scan has left. Pure rules; kura/library.py does the looking.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Literal

from kura.core.plan import QUARANTINE_FOLDER

VIDEO_EXTENSIONS = frozenset(
    {
        ".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ogm", ".divx",
        ".ts", ".m2ts", ".mts", ".mpg", ".mpeg", ".vob", ".rm", ".rmvb", ".3gp",
    }
)  # fmt: skip

# Kura's own quarantine, and the folders Windows keeps on every drive.
_SKIPPED = frozenset(
    name.casefold()
    for name in (QUARANTINE_FOLDER, "$RECYCLE.BIN", "RECYCLER", "System Volume Information")
)
_MIN_FILES_FOR_PACE = 5


def is_video(name: str) -> bool:
    """A video by its extension, in any case. Subtitles, reports and pictures aren't."""
    return PureWindowsPath(name).suffix.casefold() in VIDEO_EXTENSIONS


def skipped_folder(name: str) -> bool:
    """Folders a scan never looks into: Kura's quarantine, Windows' own, and hidden ones."""
    folded = name.casefold()
    return folded in _SKIPPED or folded.startswith(".")


@dataclass(frozen=True)
class Covered:
    """The new folder is already in the library, or inside a folder that is."""

    by: PureWindowsPath


@dataclass(frozen=True)
class Holds:
    """The new folder holds folders already in the library, which it takes in."""

    folders: tuple[PureWindowsPath, ...]


def fits(new: PureWindowsPath, existing: Iterable[PureWindowsPath]) -> Covered | Holds | None:
    """How a new library folder sits beside the ones already there. None: on its own."""
    folders = list(existing)
    for folder in folders:
        if new == folder or new.is_relative_to(folder):
            return Covered(folder)
    held = tuple(folder for folder in folders if folder.is_relative_to(new))
    return Holds(held) if held else None


type Picture = Literal["sd", "720p", "1080p", "larger", "unknown"]


def picture_size(width: int | None, height: int | None) -> Picture:
    """The picture's size class, by height or, for wide films, by width: 1920x800 is 1080p."""
    if not width or not height:
        return "unknown"
    lines = max(height, width * 9 / 16)
    if lines <= 576:
        return "sd"
    if lines <= 800:
        return "720p"
    if lines <= 1200:
        return "1080p"
    return "larger"


def time_left(done: int, total: int, elapsed: float) -> float | None:
    """Seconds left at the pace so far, or None until there's enough of a pace to go by."""
    if done >= total:
        return 0.0
    if done < _MIN_FILES_FOR_PACE:
        return None
    return (total - done) * elapsed / done
