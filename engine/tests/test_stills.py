"""Stills from a video for the review screen: taken once with ffmpeg, then kept."""

import subprocess
from collections.abc import Sequence
from pathlib import Path

from fastapi.testclient import TestClient

from kura.config import DataPaths
from kura.stills import still

FFMPEG = Path("C:/Kura/tools/ffmpeg/ffmpeg.exe")


class Frames:
    """Stands in for ffmpeg: writes a picture where it's told to, and counts the calls."""

    def __init__(self, fail: bool = False) -> None:
        self.commands: list[list[str]] = []
        self.fail = fail

    def __call__(self, command: Sequence[str]) -> None:
        self.commands.append(list(command))
        if self.fail:
            raise subprocess.CalledProcessError(1, list(command), stderr=b"Invalid data")
        Path(command[-1]).write_bytes(b"jpeg")


def video(tmp_path: Path) -> Path:
    file = tmp_path / "Downloads" / "[subs] ep03 final.mkv"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"a video")
    return file


def test_a_still_is_taken_at_its_point_then_kept(paths: DataPaths, tmp_path: Path):
    frames = Frames()
    file = video(tmp_path)

    first = still(paths, FFMPEG, file, 1450.0, 1, run=frames)
    again = still(paths, FFMPEG, file, 1450.0, 1, run=frames)

    assert first is not None
    assert first.read_bytes() == b"jpeg"
    assert again == first
    assert len(frames.commands) == 1
    command = frames.commands[0]
    assert command[:2] == [str(FFMPEG), "-nostdin"]  # no key reading: see core/convert.py
    assert command[command.index("-ss") + 1] == "725.00"  # halfway through 24:10


def test_no_ffmpeg_no_length_or_a_damaged_file_gives_no_still(paths: DataPaths, tmp_path: Path):
    file = video(tmp_path)

    assert still(paths, None, file, 1450.0, 0, run=Frames()) is None
    assert still(paths, FFMPEG, file, None, 0, run=Frames()) is None
    assert still(paths, FFMPEG, file, 1450.0, 5, run=Frames()) is None
    assert still(paths, FFMPEG, file, 1450.0, 0, run=Frames(fail=True)) is None
    assert not list((paths.cache / "stills").glob("*.partial.jpg"))


def test_the_review_screen_gets_no_still_before_ffmpeg_is_there(client: TestClient):
    assert client.get("/review/1/stills/0").status_code == 404
