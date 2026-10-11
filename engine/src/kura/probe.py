"""Asking ffprobe what a video holds. kura/core/media.py makes sense of the answer."""

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from kura.core.media import Json

# Windows would otherwise flash a console window for each file, since the engine has none.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_ARGUMENTS = ("-v", "error", "-print_format", "json", "-show_format", "-show_streams")


class ProbeError(Exception):
    """ffprobe couldn't read a file. The message says why, in words."""


def probe(ffprobe: Path | Sequence[str], file: Path, timeout: float = 120) -> Json:
    """ffprobe's report on one file: its format, streams and chapters.

    `ffprobe` is the program, or a whole command that stands in for it in tests.
    """
    command = [str(ffprobe)] if isinstance(ffprobe, Path) else list(ffprobe)
    try:
        result = subprocess.run(  # noqa: S603 - Kura's own ffprobe, and a path, never a shell
            [*command, *_ARGUMENTS, "-show_chapters", str(file)],
            capture_output=True,
            timeout=timeout,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ProbeError(
            f"ffprobe spent more than {timeout:.0f} seconds on it without an answer, so Kura "
            "stopped it. The file may be damaged."
        ) from None
    except OSError as error:
        raise ProbeError(f"ffprobe couldn't start: {error.strerror or error}.") from error
    if result.returncode != 0:
        lines = result.stderr.decode("utf-8", "replace").strip().splitlines()
        reason = lines[-1] if lines else f"ffprobe stopped with code {result.returncode}"
        reason = reason.removeprefix(f"{file}: ").rstrip(".")
        raise ProbeError(f"Kura couldn't read it ({reason}). It may be damaged, or not a video.")
    try:
        report: Json = json.loads(result.stdout)
    except ValueError:
        raise ProbeError("ffprobe answered something Kura couldn't read.") from None
    return report
