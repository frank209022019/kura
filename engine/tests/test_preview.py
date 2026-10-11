"""See it first: a frame before converting and after, with ffmpeg and the AI model stood in for."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from kura.config import DataPaths
from kura.core.media import media_from_ffprobe
from kura.core.standard import CINEMA_1080, Method
from kura.preview import PreviewError, frame
from tests.converting import programs, report

pytestmark = pytest.mark.usefixtures("quarantine")


@pytest.fixture
def episode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("KURA_FAKE_SIZE", "8x6")
    path = tmp_path / "Trigun - 01.mkv"
    path.write_bytes(b"an SD episode")
    return path


SD = media_from_ffprobe(report(8, 6, codec="h264"))
HD = media_from_ffprobe(report(1280, 720, codec="h264"))


def test_before_is_the_original_frame(paths: DataPaths, episode: Path):
    commands: list[Sequence[str]] = []

    picture = frame(
        paths,
        programs({}, commands),
        episode,
        SD,
        CINEMA_1080,
        side="before",
        way=Method.BEST,
        point=1,
    )

    assert picture.suffix == ".png"
    [command] = commands
    assert command[command.index("-ss") + 1] == "720.00"  # halfway through 24 minutes
    assert "-vf" not in command


def test_after_the_ai_model_upscales_the_frame_and_it_is_kept(paths: DataPaths, episode: Path):
    commands: list[Sequence[str]] = []
    kit = programs({}, commands)

    first = frame(paths, kit, episode, SD, CINEMA_1080, side="after", way=Method.BEST, point=0)
    again = frame(paths, kit, episode, SD, CINEMA_1080, side="after", way=Method.BEST, point=0)

    assert first == again
    assert first.read_text() == f"converted {16 * 12 * 3 * 4} bytes of frames"  # doubled
    assert len(commands) == 2  # the frame out, the picture in: once


def test_after_a_lighter_way_uses_one_command(paths: DataPaths, episode: Path):
    commands: list[Sequence[str]] = []

    picture = frame(
        paths,
        programs({}, commands),
        episode,
        HD,
        CINEMA_1080,
        side="after",
        way=Method.BEST,
        point=2,
    )

    [command] = commands  # 720p gets the fast upscale, the most that suits it
    assert "libplacebo" in command[command.index("-vf") + 1]
    assert picture.read_bytes().startswith(b"png of ")


def test_a_frame_ffmpeg_cant_make_says_why(
    paths: DataPaths, episode: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KURA_FAKE_FAIL", "frame")

    with pytest.raises(PreviewError, match="Invalid data found when processing input"):
        frame(
            paths, programs({}), episode, SD, CINEMA_1080, side="before", way=Method.BEST, point=0
        )

    assert not list((paths.cache / "previews").glob("*.png"))


def test_a_file_without_a_picture_has_no_frame(paths: DataPaths, episode: Path):
    sound = media_from_ffprobe({"format": {"duration": "60"}, "streams": []})

    with pytest.raises(PreviewError):
        frame(
            paths,
            programs({}),
            episode,
            sound,
            CINEMA_1080,
            side="before",
            way=Method.BEST,
            point=0,
        )
