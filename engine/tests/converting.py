"""What converting tests share: ffprobe's report on a result, and ffmpeg, ffprobe and the AI
model stood in for (tests/fake_ffmpeg.py)."""

import subprocess
import sys
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import cast

from kura.convert import Programs, start
from kura.core.fields import Json
from kura.upscale import Frame
from tests.fake_ffprobe import REPORT

FAKE_FFMPEG = [sys.executable, str(Path(__file__).parent / "fake_ffmpeg.py")]
SHADER = Path(__file__).parent / "fake.glsl"
BEST_TAG = "best to 1080p · Kura 0.1.0"


def report(width: int, height: int, *, codec: str = "hevc", tag: str | None = None) -> Json:
    """ffprobe's report on a 24-minute file like REPORT (Japanese sound), at this size."""
    made = cast("dict[str, object]", deepcopy(REPORT))
    streams = cast("list[dict[str, object]]", made["streams"])
    streams[0].update(
        {"width": width, "height": height, "codec_name": codec, "pix_fmt": "yuv420p10le"}
    )
    streams[0].pop("display_aspect_ratio", None)
    format_ = {**cast("dict[str, object]", made["format"]), "duration": "1440.0"}
    made["format"] = {**format_, "tags": {"KURA": tag}} if tag else format_
    return made


def doubled(frame: Frame) -> Frame:
    return frame.repeat(2, axis=2).repeat(2, axis=3)


def programs(converted: Json, commands: list[Sequence[str]] | None = None) -> Programs:
    """ffmpeg and ffprobe stand-ins; ffprobe reports `converted` for the result."""

    def read(path: Path) -> Json:
        return converted

    def started(
        command: Sequence[str],
        *,
        stdin: int | None = None,
        stdout: int | None = None,
        stderr: int | None = None,
    ) -> subprocess.Popen[bytes]:
        if commands is not None:
            commands.append(command)
        return start(command, stdin=stdin, stdout=stdout, stderr=stderr)

    return Programs(FAKE_FFMPEG, read, lambda _width, _height: doubled, SHADER, start=started)
