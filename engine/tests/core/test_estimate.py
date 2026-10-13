"""Time and space estimates, from speeds measured on the owner's GTX 1660 Super (2026-10-11).

The convert board's figures (35 SD episodes, about 35 hours and 16 GB) still hold.
"""

from fractions import Fraction

import pytest

from kura.core.estimate import Estimate, Speeds, estimate, total
from kura.core.media import Audio, MediaInfo, Video
from kura.core.standard import CINEMA_1080, COMPACT_720, Decision, Method

NTSC_FILM = Fraction(24000, 1001)


def episode(
    seconds: float = 1406.0, size: int = 240_000_000, width: int = 720, height: int = 480
) -> MediaInfo:
    video = Video("h264", width, height, Fraction(4, 3), NTSC_FILM, 8, False)
    return MediaInfo("mkv", seconds, size, video, (Audio("aac", 2, "jpn", False),))


def test_the_convert_boards_35_sd_episodes_take_about_35_hours_and_16_gb():
    best = Decision(Method.BEST, 1440, 1080)
    season = total(estimate(episode(), best, CINEMA_1080) for _ in range(35))

    assert season.gpu_seconds / 3600 == pytest.approx(35, abs=1.5)
    assert season.output_bytes / 1e9 == pytest.approx(15.4, abs=0.5)


@pytest.mark.parametrize(
    ("method", "width", "height", "minutes_per_episode"),
    [
        (Method.BEST, 720, 480, 62),  # Real-ESRGAN, SD to 1080p
        (Method.FAST, 1280, 720, 10.2),  # Anime4K, 720p to 1080p
        (Method.REENCODE, 1920, 1080, 3.3),  # NVENC, 1080p to 1080p
    ],
)
def test_each_method_takes_about_what_was_measured(
    method: Method, width: int, height: int, minutes_per_episode: float
):
    source = episode(seconds=1440.0, width=width, height=height)

    result = estimate(source, Decision(method, 1440, 1080), CINEMA_1080)

    assert result.gpu_seconds / 60 == pytest.approx(minutes_per_episode, rel=0.03)


def test_a_smaller_standard_saves_space_and_only_the_fast_upscales_time():
    source = episode(seconds=1440.0)
    made = {
        (method, standard.height): estimate(
            source, Decision(method, width, standard.height), standard
        )
        for method in (Method.BEST, Method.FAST, Method.REENCODE)
        for standard, width in ((CINEMA_1080, 1440), (COMPACT_720, 960))
    }

    fast = made[Method.FAST, 1080].gpu_seconds / made[Method.FAST, 720].gpu_seconds
    assert fast == pytest.approx(2.25)  # it works at the size it makes
    assert made[Method.BEST, 720].gpu_seconds == made[Method.BEST, 1080].gpu_seconds  # the source
    assert made[Method.REENCODE, 720].gpu_seconds == made[Method.REENCODE, 1080].gpu_seconds
    assert made[Method.BEST, 720].output_bytes < made[Method.BEST, 1080].output_bytes


def test_the_ai_model_takes_longer_the_more_pixels_the_source_has():
    best = Decision(Method.BEST, 1440, 1080)

    pal = estimate(episode(width=720, height=576), best, CINEMA_1080)
    small = estimate(episode(width=640, height=480), best, CINEMA_1080)

    assert pal.gpu_seconds / small.gpu_seconds == pytest.approx(720 * 576 / (640 * 480))


def test_a_measured_card_replaces_the_default_speeds():
    best = Decision(Method.BEST, 1440, 1080)
    twice_as_fast = Speeds(best=Speeds().best * 2)

    measured = estimate(episode(), best, CINEMA_1080, twice_as_fast)

    assert measured.gpu_seconds == pytest.approx(
        estimate(episode(), best, CINEMA_1080).gpu_seconds / 2
    )


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
    video = Video("h264", 1920, 1080, Fraction(16, 9), None, 8, False)
    unknown = MediaInfo("avi", 1440.0, 1, video)

    result = estimate(unknown, Decision(Method.REENCODE, 1920, 1080), CINEMA_1080)

    assert result.gpu_seconds / 60 == pytest.approx(3.3, rel=0.03)


def test_total_of_nothing_is_nothing():
    assert total([]) == Estimate(0.0, 0)
