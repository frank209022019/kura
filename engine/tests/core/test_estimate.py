"""Time and space estimates. The board figures are the design's numbers for a GTX 1660 Super."""

from fractions import Fraction

import pytest

from kura.core.estimate import Estimate, Speeds, estimate, total
from kura.core.media import Audio, MediaInfo, Video
from kura.core.standard import CINEMA_1080, COMPACT_720, Decision, Method

NTSC_FILM = Fraction(24000, 1001)


def episode(seconds: float = 1406.0, size: int = 240_000_000) -> MediaInfo:
    video = Video("h264", 720, 480, Fraction(4, 3), NTSC_FILM, 8, False)
    return MediaInfo("mkv", seconds, size, video, (Audio("aac", 2, "jpn", False),))


def test_the_convert_boards_35_sd_episodes_take_about_35_hours_and_16_gb():
    best = Decision(Method.BEST, 1440, 1080)
    season = total(estimate(episode(), best, CINEMA_1080) for _ in range(35))

    assert season.gpu_seconds / 3600 == pytest.approx(35, abs=1.5)
    assert season.output_bytes / 1e9 == pytest.approx(15.4, abs=0.5)


@pytest.mark.parametrize(
    ("method", "minutes_per_episode"),
    [(Method.BEST, 60), (Method.FAST, 12), (Method.REENCODE, 3)],
)
def test_each_method_takes_about_what_the_design_says(method: Method, minutes_per_episode: int):
    result = estimate(episode(seconds=1440.0), Decision(method, 1440, 1080), CINEMA_1080)

    assert result.gpu_seconds / 60 == pytest.approx(minutes_per_episode, rel=0.05)


def test_measured_speeds_replace_the_design_figures():
    measured = Speeds(best=19.2)

    result = estimate(
        episode(seconds=1440.0), Decision(Method.BEST, 1440, 1080), CINEMA_1080, measured
    )

    assert result.gpu_seconds / 60 == pytest.approx(30, rel=0.05)


def test_a_compact_720p_episode_is_about_250_mb():
    result = estimate(episode(seconds=1440.0), Decision(Method.BEST, 960, 720), COMPACT_720)

    assert result.output_bytes / 1e6 == pytest.approx(250, rel=0.01)


def test_renaming_and_remuxing_need_no_graphics_card_and_keep_the_size():
    for method in (Method.RENAME, Method.REMUX):
        result = estimate(episode(size=1_000_000), Decision(method, 1920, 1080), CINEMA_1080)

        assert result == Estimate(gpu_seconds=0.0, output_bytes=1_000_000)


def test_a_skipped_file_costs_nothing():
    assert estimate(episode(), Decision(Method.SKIP), CINEMA_1080) == Estimate(0.0, 0)


def test_an_unknown_frame_rate_counts_as_film():
    video = Video("h264", 720, 480, Fraction(4, 3), None, 8, False)
    unknown = MediaInfo("avi", 1440.0, 1, video)

    result = estimate(unknown, Decision(Method.REENCODE, 1440, 1080), CINEMA_1080)

    assert result.gpu_seconds / 60 == pytest.approx(3, rel=0.05)


def test_total_of_nothing_is_nothing():
    assert total([]) == Estimate(0.0, 0)
