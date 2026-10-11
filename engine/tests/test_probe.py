"""Running ffprobe on one file, and saying why when it can't read it."""

import sys
from pathlib import Path

import pytest

from kura.core.media import media_from_ffprobe
from kura.probe import ProbeError, probe

FAKE = [sys.executable, str(Path(__file__).with_name("fake_ffprobe.py"))]


def test_a_readable_file_gives_ffprobes_report(tmp_path: Path):
    episode = tmp_path / "Dragon Ball - 003 - The Nimbus Cloud of Roshi.mkv"

    report = probe(FAKE, episode)

    media = media_from_ffprobe(report)
    assert media.video is not None
    assert (media.video.codec, media.video.width, media.video.height) == ("hevc", 720, 540)
    assert media.duration == pytest.approx(1244.2, abs=0.01)


def test_a_damaged_file_says_what_ffprobe_found(tmp_path: Path):
    with pytest.raises(ProbeError) as raised:
        probe(FAKE, tmp_path / "broken episode.mkv")

    assert str(raised.value) == (
        "Kura couldn't read it (Invalid data found when processing input). "
        "It may be damaged, or not a video."
    )


def test_a_file_ffprobe_hangs_on_is_given_up_on(tmp_path: Path):
    with pytest.raises(ProbeError, match="spent more than 1 seconds on it"):
        probe(FAKE, tmp_path / "stuck.mkv", timeout=1)


def test_a_missing_ffprobe_is_named(tmp_path: Path):
    with pytest.raises(ProbeError, match="ffprobe couldn't start"):
        probe(tmp_path / "ffprobe.exe", tmp_path / "episode.mkv")
