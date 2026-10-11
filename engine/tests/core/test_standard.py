"""What each file needs to reach the library standard."""

from fractions import Fraction

import pytest

from kura.core.media import Audio, MediaInfo, Video
from kura.core.standard import CINEMA_1080, COMPACT_720, Method, Standard, decide, deinterlaced

AAC = Audio("aac", 2, "jpn", lossless=False)
FLAC = Audio("flac", 2, "jpn", lossless=True)
FOUR_THREE = Fraction(4, 3)
WIDE = Fraction(16, 9)


def media(
    width: int,
    height: int,
    *,
    codec: str = "h264",
    bit_depth: int = 8,
    aspect: Fraction = WIDE,
    container: str = "mkv",
    audio: tuple[Audio, ...] = (AAC,),
    interlaced: bool | None = False,
) -> MediaInfo:
    video = Video(codec, width, height, aspect, Fraction(24000, 1001), bit_depth, interlaced)
    return MediaInfo(container, 1440.0, 200_000_000, video, audio)


class TestCinema1080:
    def test_sd_gets_the_ai_model_and_stays_4_by_3(self):
        decision = decide(media(720, 480, aspect=FOUR_THREE), CINEMA_1080)

        assert decision.method == Method.BEST
        assert (decision.width, decision.height) == (1440, 1080)

    def test_interlaced_sd_is_deinterlaced_first(self):
        decision = decide(media(720, 576, aspect=FOUR_THREE, interlaced=True), CINEMA_1080)

        assert (decision.method, decision.deinterlace) == (Method.BEST, True)

    def test_720p_gets_the_fast_upscale(self):
        decision = decide(media(1280, 720), CINEMA_1080)

        assert decision.method == Method.FAST
        assert (decision.width, decision.height) == (1920, 1080)

    def test_1080p_in_another_codec_is_re_encoded_at_its_size(self):
        decision = decide(media(1920, 1080), CINEMA_1080)

        assert decision.method == Method.REENCODE
        assert (decision.width, decision.height) == (1920, 1080)

    def test_8_bit_hevc_is_re_encoded_too(self):
        decision = decide(media(1920, 1080, codec="hevc", bit_depth=8), CINEMA_1080)

        assert decision.method == Method.REENCODE

    def test_a_file_exactly_at_the_standard_is_only_renamed(self):
        decision = decide(media(1920, 1080, codec="hevc", bit_depth=10), CINEMA_1080)

        assert decision.method == Method.RENAME
        assert decision.reasons == ("Already 1080p HEVC 10-bit in MKV: only renamed",)

    def test_lossless_sound_becomes_aac_without_touching_the_picture(self):
        decision = decide(
            media(1920, 1080, codec="hevc", bit_depth=10, audio=(FLAC, AAC)), CINEMA_1080
        )

        assert decision.method == Method.REMUX
        assert "Lossless FLAC sound becomes AAC" in decision.reasons

    def test_the_right_picture_in_another_container_is_moved_to_mkv(self):
        decision = decide(
            media(1920, 1080, codec="hevc", bit_depth=10, container="mp4"), CINEMA_1080
        )

        assert decision.method == Method.REMUX
        assert "MP4 becomes MKV" in decision.reasons

    def test_a_letterboxed_movie_keeps_its_shape(self):
        decision = decide(media(1920, 800, aspect=Fraction(12, 5)), CINEMA_1080)

        assert decision.method == Method.REENCODE
        assert (decision.width, decision.height) == (1920, 800)

    def test_4k_is_brought_down_to_1080p(self):
        decision = decide(media(3840, 2160, codec="hevc", bit_depth=10), CINEMA_1080)

        assert decision.method == Method.REENCODE
        assert (decision.width, decision.height) == (1920, 1080)

    def test_an_interlaced_picture_at_the_standard_is_made_anew_not_copied(self):
        decision = decide(
            media(1920, 1080, codec="hevc", bit_depth=10, container="mp4", interlaced=True),
            CINEMA_1080,
        )

        assert (decision.method, decision.deinterlace) == (Method.REENCODE, True)
        assert decision.reasons == ("Interlaced: deinterlaced first", "MP4 becomes MKV")


def test_a_picture_found_interlaced_later_is_deinterlaced_and_made_anew():
    remux = decide(
        media(1920, 1080, codec="hevc", bit_depth=10, container="mp4", interlaced=None),
        CINEMA_1080,
    )
    sd = decide(media(720, 480, aspect=FOUR_THREE, interlaced=None), CINEMA_1080)

    assert remux.method == Method.REMUX
    assert (deinterlaced(remux).method, deinterlaced(remux).deinterlace) == (Method.REENCODE, True)
    assert deinterlaced(remux).reasons == ("Interlaced: deinterlaced first", "MP4 becomes MKV")
    assert (deinterlaced(sd).method, deinterlaced(sd).deinterlace) == (Method.BEST, True)


class TestChoices:
    def test_without_ai_sd_is_scaled_up_plainly(self):
        no_ai = Standard("No AI 1080p", 1080, ai_for_sd=False)

        assert decide(media(720, 480, aspect=FOUR_THREE), no_ai).method == Method.REENCODE

    def test_without_the_fast_upscale_720p_is_scaled_up_plainly(self):
        no_fast = Standard("Plain 1080p", 1080, fast_for_hd=False)

        assert decide(media(1280, 720), no_fast).method == Method.REENCODE


class TestCompact720:
    def test_720p_goes_to_720p_too(self):
        decision = decide(media(1280, 720), COMPACT_720)

        assert decision.method == Method.REENCODE
        assert (decision.width, decision.height) == (1280, 720)

    def test_1080p_is_brought_down(self):
        decision = decide(media(1920, 1080, codec="hevc", bit_depth=10), COMPACT_720)

        assert (decision.method, decision.width, decision.height) == (Method.REENCODE, 1280, 720)

    def test_sd_is_upscaled_to_720p(self):
        decision = decide(media(640, 480, aspect=FOUR_THREE), COMPACT_720)

        assert (decision.method, decision.width, decision.height) == (Method.BEST, 960, 720)

    def test_a_720p_file_at_the_standard_is_only_renamed(self):
        decision = decide(media(1280, 720, codec="hevc", bit_depth=10), COMPACT_720)

        assert decision.method == Method.RENAME


def test_a_file_without_a_picture_is_skipped():
    decision = decide(MediaInfo("mkv", 1440.0, 1000, None, (AAC,)), CINEMA_1080)

    assert decision.method == Method.SKIP
    assert decision.reasons == ("No picture to convert",)


@pytest.mark.parametrize(
    ("width", "height", "aspect", "expected"),
    [
        (720, 480, Fraction(4, 3), (1440, 1080)),
        (720, 480, Fraction(16, 9), (1920, 1080)),  # anamorphic widescreen DVD
        (1440, 1080, Fraction(4, 3), (1440, 1080)),
        (1920, 1036, Fraction(480, 259), (1920, 1036)),
    ],
)
def test_output_sizes_keep_the_shape_on_screen(
    width: int, height: int, aspect: Fraction, expected: tuple[int, int]
):
    decision = decide(media(width, height, aspect=aspect), CINEMA_1080)

    assert (decision.width, decision.height) == expected
