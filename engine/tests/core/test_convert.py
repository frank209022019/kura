"""Converting one file: what it becomes, the ffmpeg commands that make it, and checking it."""

from dataclasses import replace
from fractions import Fraction
from pathlib import PureWindowsPath

from kura.core.convert import (
    AudioPlan,
    check,
    decoder_command,
    encoder_command,
    interlace_command,
    interlaced,
    one_command,
    recipe,
)
from kura.core.media import Audio, MediaInfo, Subtitle, Video
from kura.core.standard import CINEMA_1080, Decision, Method, decide

SOURCE = PureWindowsPath(
    r"D:\Anime\TV\Dragon Ball Z (1989)\Season 01\Dragon Ball Z (1989) - S01E05.mkv"
)
WORK = PureWindowsPath(
    r"D:\Anime\TV\Dragon Ball Z (1989)\Season 01\Dragon Ball Z (1989) - S01E05.kura-converting"
)
FFMPEG = "ffmpeg.exe"
FF = [FFMPEG]  # the command that runs it
TAG = "best · Kura 0.1.0 · 2026-10-11"


def sd() -> MediaInfo:
    """A DVD episode: 720x480 shown at 4:3, Japanese and English sound, styled subtitles, fonts."""
    video = Video("mpeg2video", 720, 480, Fraction(4, 3), Fraction(24000, 1001), 8, False)
    return MediaInfo(
        "mkv",
        1440.0,
        240_000_000,
        video,
        (Audio("ac3", 2, "jpn", False), Audio("ac3", 2, "eng", False)),
        (Subtitle("ass", "eng", True, False),),
        fonts=2,
        chapters=4,
    )


def test_an_sd_episode_gets_the_ai_model_and_keeps_its_sound_subtitles_and_fonts():
    media = sd()

    made = recipe(SOURCE, media, decide(media, CINEMA_1080), tag=TAG)

    assert (made.method, made.width, made.height, made.deinterlace) == (
        Method.BEST,
        1440,
        1080,
        False,
    )
    assert made.audio == (AudioPlan(0, None), AudioPlan(1, None))  # copied as they are
    assert made.subtitles == ("copy",)
    assert (made.fonts, made.output.name) == (True, "Dragon Ball Z (1989) - S01E05.mkv")


def test_lossless_sound_becomes_aac_and_mp4_text_subtitles_become_srt():
    media = replace(
        sd(),
        container="mp4",
        audio=(Audio("flac", 2, "jpn", True), Audio("truehd", 6, "eng", True)),
        subtitles=(Subtitle("mov_text", "eng", True, False),),
        fonts=0,
    )
    source = SOURCE.with_suffix(".mp4")

    made = recipe(source, media, decide(media, CINEMA_1080), tag=TAG)

    assert made.audio == (AudioPlan(0, 192), AudioPlan(1, 576))  # 96 kb/s a channel
    assert made.subtitles == ("srt",)
    assert made.output == SOURCE  # an MKV beside it


def test_a_720p_episode_is_upscaled_with_anime4k_in_one_command():
    media = replace(
        sd(), video=Video("h264", 1280, 720, Fraction(16, 9), Fraction(24000, 1001), 8, False)
    )
    made = recipe(SOURCE, media, decide(media, CINEMA_1080), tag=TAG)

    command = one_command(FF, SOURCE, WORK, made, shader=PureWindowsPath(r"C:\Kura\modeA_hq.glsl"))

    assert made.method is Method.FAST
    assert command[:8] == [
        FFMPEG,
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-init_hw_device",
        "vulkan=vk",
        "-filter_hw_device",
    ]
    filters = command[command.index("-vf") + 1]
    assert filters == (
        "hwupload,libplacebo=w=1920:h=1080:format=p010le:"
        "custom_shader_path='C\\:/Kura/modeA_hq.glsl',hwdownload,format=p010le,setsar=1"
    )
    assert command[command.index("-c:v") + 1] == "hevc_nvenc"
    assert [part for part in command if part in ("-map", "0:V:0", "0:a?", "0:s?", "0:t?")] == [
        "-map",
        "0:V:0",
        "-map",
        "0:a?",
        "-map",
        "0:s?",
        "-map",
        "0:t?",
    ]
    assert command[-3:] == ["-f", "matroska", str(WORK)]


def test_an_interlaced_picture_is_deinterlaced_before_anything_else():
    media = replace(
        sd(), video=Video("h264", 1920, 1080, Fraction(16, 9), Fraction(30000, 1001), 8, True)
    )
    made = recipe(SOURCE, media, decide(media, CINEMA_1080), tag=TAG)

    command = one_command(FF, SOURCE, WORK, made, shader=None)

    assert made.method is Method.REENCODE
    assert command[command.index("-vf") + 1] == (
        "bwdif=mode=send_frame,scale=1920:1080:flags=lanczos,setsar=1,format=p010le"
    )


def test_a_remux_copies_the_picture():
    media = replace(
        sd(),
        container="mp4",
        video=Video("hevc", 1920, 1080, Fraction(16, 9), Fraction(24000, 1001), 10, False),
        subtitles=(),
        fonts=0,
    )
    made = recipe(SOURCE.with_suffix(".mp4"), media, decide(media, CINEMA_1080), tag=TAG)

    command = one_command(FF, SOURCE.with_suffix(".mp4"), WORK, made, shader=None)

    assert made.method is Method.REMUX
    assert "-vf" not in command
    assert command[command.index("-c:v") + 1] == "copy"


def test_the_ai_model_reads_raw_frames_and_the_encoder_takes_them_with_the_sound():
    made = recipe(SOURCE, sd(), Decision(Method.BEST, 1440, 1080), tag=TAG)

    decoder = decoder_command(FF, SOURCE, made)
    encoder = encoder_command(FF, SOURCE, WORK, made, upscaled=(1440, 960))

    assert decoder == [
        FFMPEG,
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(SOURCE),
        "-map",
        "0:V:0",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gbrpf32le",
        "-",
    ]
    assert encoder[:17] == [
        FFMPEG,
        "-nostdin",  # its frames still come in on standard input
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gbrpf32le",
        "-s",
        "1440x960",
        "-r",
        "24000/1001",
        "-i",
        "-",
        "-i",
        str(SOURCE),
    ]
    assert (
        encoder[encoder.index("-vf") + 1] == "scale=1440:1080:flags=lanczos,setsar=1,format=p010le"
    )
    assert [encoder[i + 1] for i, part in enumerate(encoder) if part == "-map"] == [
        "0:v",
        "1:a?",
        "1:s?",
        "1:t?",
    ]
    assert encoder[encoder.index("-map_chapters") + 1] == "1"
    assert f"KURA={TAG}" in encoder


def test_interlacing_is_told_from_a_look_at_the_picture():
    command = interlace_command(FF, SOURCE, at=600.0)
    report = (
        "[Parsed_idet_0 @ 0000] Single frame detection: TFF: 280 BFF: 0 Progressive: 300\n"
        "[Parsed_idet_0 @ 0000] Multi frame detection: TFF: 420 BFF: 2 Progressive: 150"
        " Undetermined: 28\n"
    )

    assert command[command.index("-vf") + 1] == "idet"
    assert interlaced(report) is True
    assert interlaced(report.replace("TFF: 420", "TFF: 12")) is False
    assert interlaced("no report") is False


def test_a_result_that_matches_passes_and_one_that_doesnt_says_why():
    made = recipe(SOURCE, sd(), Decision(Method.BEST, 1440, 1080), tag=TAG)
    good = replace(
        sd(),
        video=Video("hevc", 1440, 1080, Fraction(4, 3), Fraction(24000, 1001), 10, False),
        duration=1439.6,
        kura_tag=TAG,
    )

    assert check(sd(), good, made) == []
    assert check(sd(), replace(good, duration=1200.0), made) == ["It's 20:00 long, not 24:00"]
    assert check(sd(), replace(good, audio=good.audio[:1]), made) == ["It has 1 sound track, not 2"]
    assert check(sd(), replace(good, video=None), made) == ["It has no picture"]


def test_no_ffmpeg_kura_starts_reads_keys_from_its_standard_input():
    """ffmpeg looks for key presses on standard input. Under Kura's window that's the engine's own
    input, which the engine waits on, and Windows makes ffmpeg's look wait too: it would stop."""
    made = recipe(SOURCE, sd(), Decision(Method.BEST, 1440, 1080), tag=TAG)
    commands = [
        decoder_command(FF, SOURCE, made),
        encoder_command(FF, SOURCE, WORK, made, upscaled=(1440, 960)),
        one_command(FF, SOURCE, WORK, replace(made, method=Method.REENCODE), shader=None),
        interlace_command(FF, SOURCE, at=60.0),
    ]

    assert all(command[1] == "-nostdin" for command in commands)
