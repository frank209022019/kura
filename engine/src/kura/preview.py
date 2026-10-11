"""See it first: one frame of a video before converting and after, made the way the owner picked,
for the Convert screen's comparison.

The frames are taken at the stills' three points (kura/stills.py) and kept in the data folder's
cache as PNG, so nothing is lost on the way and a second look is instant. The after is made the
way the conversion would make it (kura/core/convert.py builds the commands): the AI model on one
raw frame between two ffmpegs, or one ffmpeg command for the other methods.
"""

import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Literal

import numpy as np

from kura.config import DataPaths
from kura.convert import Programs, lighter
from kura.core.convert import (
    Recipe,
    frame_command,
    from_frame_command,
    preview_command,
    recipe,
    still_command,
)
from kura.core.media import MediaInfo
from kura.core.standard import Method, Standard, decide
from kura.stills import POINTS
from kura.upscale import UpscaleError

type Side = Literal["before", "after"]

_TIMEOUT = 120  # seconds for one frame, the AI model's included


class PreviewError(Exception):
    """The frame couldn't be made. The message says why, in words."""


def frame(
    paths: DataPaths,
    programs: Programs,
    source: Path,
    media: MediaInfo,
    standard: Standard,
    *,
    side: Side,
    way: Method,
    point: int,
) -> Path:
    """The picture of one side of the comparison, made the first time it's asked for: the
    original as it is (`before`), or as `way` makes it (`after`; never more than suits it).
    Raises PreviewError when it can't be made."""
    video = media.video
    if video is None or not media.duration or not 0 <= point < len(POINTS):
        raise PreviewError("There's no picture to show from this file.")
    decision = decide(media, standard)
    made = recipe(source, media, replace(decision, method=lighter(decision.method, way)), tag="")
    at = media.duration * POINTS[point]
    stat = source.stat()
    what = side if side == "before" else f"{made.method}-{made.width}x{made.height}"
    key = f"{source}|{stat.st_size}|{stat.st_mtime_ns}|{point}|{what}"
    kept = paths.cache / "previews" / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.png"
    if kept.is_file():
        return kept
    kept.parent.mkdir(parents=True, exist_ok=True)
    partial = kept.with_name(f"{kept.stem}.partial.png")
    try:
        if side == "before":
            _run(
                programs, still_command(programs.ffmpeg, source, partial, at=at, deinterlace=False)
            )
        elif made.method is Method.BEST:
            _with_model(programs, source, partial, made, (video.width, video.height), at)
        else:
            _run(
                programs,
                preview_command(
                    programs.ffmpeg, source, partial, made, at=at, shader=programs.shader
                ),
            )
        partial.replace(kept)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return kept


def _with_model(
    programs: Programs,
    source: Path,
    out: Path,
    made: Recipe,
    size: tuple[int, int],
    at: float,
) -> None:
    width, height = size
    raw = _run(programs, frame_command(programs.ffmpeg, source, made, at=at))
    if len(raw) < width * height * 3 * 4:
        raise PreviewError("ffmpeg couldn't take a frame from it.")
    picture = np.frombuffer(raw[: width * height * 3 * 4], np.float32).reshape(1, 3, height, width)
    try:
        upscale = programs.model(width, height)
        upscaled = upscale(picture)
    except UpscaleError as error:
        raise PreviewError(str(error)) from error
    big = (upscaled.shape[3], upscaled.shape[2])
    _run(
        programs,
        from_frame_command(programs.ffmpeg, out, made, upscaled=big),
        given=upscaled.tobytes(),
    )


def _run(programs: Programs, command: list[str], *, given: bytes | None = None) -> bytes:
    """Runs ffmpeg, with `given` on its standard input; returns what it wrote to its output."""
    process = programs.start(
        command,
        stdin=subprocess.PIPE if given is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        out, err = process.communicate(given, timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise PreviewError("ffmpeg took too long over one frame, so Kura stopped it.") from None
    if process.returncode != 0:
        said = err.decode("utf-8", "replace").strip().splitlines()
        raise PreviewError(f"ffmpeg couldn't make the frame: {said[-1] if said else 'it stopped'}.")
    return out
