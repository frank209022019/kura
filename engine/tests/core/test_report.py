"""The gap analysis file. The expected text is the one shown on the design's title board."""

from datetime import date, datetime
from fractions import Fraction
from pathlib import PureWindowsPath

import pytest

from kura.core.episodes import EpisodeNumber, all_episodes
from kura.core.estimate import Estimate, estimate, total
from kura.core.media import MediaInfo, Video
from kura.core.report import (
    EpisodeState,
    GapAnalysis,
    SpecialState,
    Status,
    conversion_summary,
    describe_gpu_time,
    describe_size,
    gap_analysis_markdown,
)
from kura.core.standard import CINEMA_1080, COMPACT_720, Decision, Method

DRAGON_BALL_Z = (39, 35, 33, 32, 26, 29, 25, 34, 38)
SD_EPISODE = MediaInfo(
    "mkv",
    1440.0,
    240_000_000,
    Video("h264", 720, 480, Fraction(4, 3), Fraction(24000, 1001), 8, False),
)

# The board says 11.7 GPU days, from the speed the design assumed; the speed measured on the
# GTX 1660 Super on 2026-10-11 gives 12.1.
BOARD_TEXT = """\
# Dragon Ball Z (1989) — gap analysis
_Updated 10 Oct 2026, 14:20 · library D:\\Anime_

## Summary
- Present: **287 of 291** episodes (99%)
- Missing: **4** · Broken: **1** · At standard: **4**

## Missing
| Episode | Absolute | Folder    |
|---------|----------|-----------|
| S04E11  | 118      | Season 04 |
| S04E12  | 119      | Season 04 |
| S07E13  | 207      | Season 07 |
| S09E01  | 254      | Season 09 |

## Broken
- S05E24 (163): stops decoding at 12:41, replace it

## To convert
- 281 episodes · SD 480p → 1080p HEVC 10-bit
- About 12.1 GPU days and 130 GB
"""


def board_status(number: EpisodeNumber) -> EpisodeState:
    """The design's sample: 4 converted, 1 converting, 1 broken, 4 missing, the rest to convert."""
    if number.absolute in {118, 119, 207, 254}:
        return EpisodeState(number, Status.MISSING)
    if number.absolute == 163:
        return EpisodeState(number, Status.BROKEN, "stops decoding at 12:41")
    if number.absolute <= 4:
        return EpisodeState(number, Status.READY)
    if number.absolute == 5:
        return EpisodeState(number, Status.CONVERTING)
    return EpisodeState(number, Status.TO_CONVERT)


def test_the_dragon_ball_z_report_matches_the_design():
    best = Decision(Method.BEST, 1440, 1080)
    analysis = GapAnalysis(
        show="Dragon Ball Z (1989)",
        library=PureWindowsPath(r"D:\Anime"),
        updated=datetime(2026, 10, 10, 14, 20),
        episodes=tuple(board_status(number) for number in all_episodes(DRAGON_BALL_Z)),
        conversion=conversion_summary([480], CINEMA_1080),
        to_convert=total(estimate(SD_EPISODE, best, CINEMA_1080) for _ in range(281)),
    )

    assert gap_analysis_markdown(analysis) == BOARD_TEXT


def test_a_complete_show_with_nothing_to_do_says_so_briefly():
    analysis = GapAnalysis(
        show="Cowboy Bebop (1998)",
        library=PureWindowsPath(r"D:\Anime"),
        updated=datetime(2026, 10, 10, 9, 5),
        episodes=tuple(EpisodeState(number, Status.READY) for number in all_episodes((26,))),
    )

    assert gap_analysis_markdown(analysis) == (
        "# Cowboy Bebop (1998) — gap analysis\n"
        "_Updated 10 Oct 2026, 09:05 · library D:\\Anime_\n"
        "\n"
        "## Summary\n"
        "- Present: **26 of 26** episodes (100%)\n"
        "- Missing: **0** · Broken: **0** · At standard: **26**\n"
    )


def test_specials_and_ovas_the_library_lacks_are_listed_apart():
    analysis = GapAnalysis(
        show="Cowboy Bebop (1998)",
        library=PureWindowsPath(r"D:\Anime"),
        updated=datetime(2026, 10, 10, 9, 5),
        episodes=tuple(EpisodeState(number, Status.READY) for number in all_episodes((26,))),
        specials=(
            SpecialState(2, "Yoseatsume Blues", date(1998, 6, 26)),
            SpecialState(3, None, None),
        ),
    )

    text = gap_analysis_markdown(analysis)

    assert "- Missing: **0** · Broken: **0** · At standard: **26**\n" in text
    assert text.endswith(
        "\n"
        "## Specials and OVAs not in the library\n"
        "- S00E02 · Yoseatsume Blues · 26 Jun 1998\n"
        "- S00E03\n"
    )


@pytest.mark.parametrize(
    ("size", "text"),
    [
        (412_000_000, "412 MB"),
        (8_200_000_000, "8.2 GB"),
        (15_380_000_000, "15 GB"),
        (126_450_000_000, "130 GB"),
        (1_300_000_000_000, "1.3 TB"),
    ],
)
def test_sizes_read_like_the_boards(size: int, text: str):
    assert describe_size(size) == text


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (1_010_580, "11.7 GPU days"),
        (126_000, "35 GPU hours"),
        (5_400, "1.5 GPU hours"),
        (720, "12 GPU minutes"),
    ],
)
def test_gpu_times_read_like_the_boards(seconds: float, text: str):
    assert describe_gpu_time(seconds) == text


def test_mixed_sources_are_listed_from_small_to_large():
    assert conversion_summary([720, 480, 576, 480], CINEMA_1080) == (
        "SD 480p and 576p, 720p → 1080p HEVC 10-bit"
    )
    assert conversion_summary([1080], COMPACT_720) == "1080p → 720p HEVC 10-bit"


def test_a_report_never_divides_by_zero():
    analysis = GapAnalysis("Empty", PureWindowsPath(r"D:\Anime"), datetime(2026, 1, 1), ())

    assert "- Present: **0 of 0** episodes (0%)" in gap_analysis_markdown(analysis)


def test_estimates_default_to_nothing():
    analysis = GapAnalysis("Empty", PureWindowsPath(r"D:\Anime"), datetime(2026, 1, 1), ())

    assert analysis.to_convert == Estimate(0.0, 0)
