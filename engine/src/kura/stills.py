"""Stills: three frames from a video, so the owner can recognise it on the review screen. ffmpeg
takes each once, at 15%, 50% and 80% of the way in, and they're kept in the data folder's cache.
"""

import hashlib
import logging
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from kura.config import DataPaths
from kura.core.convert import QUIET_INPUT

log = logging.getLogger(__name__)

POINTS = (0.15, 0.5, 0.8)  # how far into the video each still is taken
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_TIMEOUT = 30  # seconds for one frame; a damaged file can make ffmpeg hang

type Run = Callable[[Sequence[str]], None]


def _run(command: Sequence[str]) -> None:
    subprocess.run(  # noqa: S603 - Kura's own ffmpeg, a path and fixed arguments, no shell
        list(command),
        stdin=subprocess.DEVNULL,  # the engine's own input is the app's: see core/convert.py
        capture_output=True,
        timeout=_TIMEOUT,
        creationflags=_NO_WINDOW,
        check=True,
    )


def still(
    paths: DataPaths,
    ffmpeg: Path | None,
    video: Path,
    seconds: float | None,
    index: int,
    run: Run = _run,
) -> Path | None:
    """The still's picture, taken the first time it's asked for. None when there's no ffmpeg
    yet, the video's length isn't known, or ffmpeg couldn't take it."""
    if ffmpeg is None or not seconds or not 0 <= index < len(POINTS) or not video.is_file():
        return None
    stat = video.stat()
    key = f"{video}|{stat.st_size}|{stat.st_mtime_ns}|{index}"
    kept = paths.cache / "stills" / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.jpg"
    if kept.is_file():
        return kept
    kept.parent.mkdir(parents=True, exist_ok=True)
    partial = kept.with_name(f"{kept.stem}.partial.jpg")
    at = f"{seconds * POINTS[index]:.2f}"
    command = [
        str(ffmpeg),
        *QUIET_INPUT,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        at,
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-vf",
        "scale=360:-2",
        "-q:v",
        "5",
        "-y",
        str(partial),
    ]
    try:
        run(command)
        partial.replace(kept)
    except (OSError, subprocess.SubprocessError) as error:
        log.info("No still from %s at %s s: %s", video, at, error)
        partial.unlink(missing_ok=True)
        return None
    return kept
