"""Converting one file to the library standard: what it becomes, the ffmpeg commands that make it,
and checking the result before it takes the original's place.

The picture is made by one of three methods (kura/core/standard.py decides which): the AI model
for SD (ffmpeg decodes raw frames, ONNX Runtime upscales them, ffmpeg encodes), Anime4K's shaders
through libplacebo for sizes between SD and the standard, or a plain re-encode. Whatever the
method, the result is HEVC 10-bit from the graphics card's encoder (NVENC) in an MKV that keeps
the original's sound (lossless sound becomes AAC), subtitles (MP4's text ones become SRT), fonts
and chapters, tagged as Kura's.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from pathlib import PurePath

from kura.core.estimate import FILM
from kura.core.media import MediaInfo
from kura.core.standard import Decision, Method

# NVENC's HEVC 10-bit: quality-led (constant quality 23 is about 450 MB a 24-minute episode).
NVENC = (
    "-c:v",
    "hevc_nvenc",
    "-preset",
    "p5",
    "-tune",
    "hq",
    "-rc",
    "vbr",
    "-cq",
    "23",
    "-b:v",
    "0",
    "-spatial-aq",
    "1",
    "-profile:v",
    "main10",
)
DEINTERLACE = "bwdif=mode=send_frame"  # one frame per frame: anime needn't double its rate
_KBPS_PER_CHANNEL = 96  # AAC in place of lossless sound
_SAMPLE_FRAMES = 600  # frames idet looks at to tell whether a picture is interlaced


@dataclass(frozen=True)
class AudioPlan:
    index: int  # among the file's sound tracks
    aac_kbps: int | None  # None: copied as it is


@dataclass(frozen=True)
class Recipe:
    """What one file becomes."""

    method: Method  # REMUX, REENCODE, FAST or BEST
    width: int
    height: int
    deinterlace: bool
    frame_rate: Fraction
    audio: tuple[AudioPlan, ...]
    subtitles: tuple[str, ...]  # per subtitle track: "copy", or "srt" for MP4's text
    fonts: bool  # the file carries fonts (MKV attachments), which go with it
    output: PurePath  # where the result goes: the original's name as an MKV
    tag: str  # written as the KURA tag


def recipe(source: PurePath, media: MediaInfo, decision: Decision, *, tag: str) -> Recipe:
    if decision.method not in (Method.REMUX, Method.REENCODE, Method.FAST, Method.BEST):
        raise ValueError(f"A {decision.method} file isn't converted.")
    video = media.video
    return Recipe(
        method=decision.method,
        width=decision.width,
        height=decision.height,
        deinterlace=decision.deinterlace,
        frame_rate=(video.frame_rate if video and video.frame_rate else FILM),
        audio=tuple(
            AudioPlan(index, _KBPS_PER_CHANNEL * max(audio.channels, 2) if audio.lossless else None)
            for index, audio in enumerate(media.audio)
        ),
        subtitles=tuple("srt" if s.codec == "mov_text" else "copy" for s in media.subtitles),
        fonts=media.fonts > 0,
        output=source.with_suffix(".mkv"),
        tag=tag,
    )


# ffmpeg looks for key presses (q to quit) on standard input. Under Kura's window that's the
# engine's own input, which the engine waits on to know when the app closes, and Windows makes
# ffmpeg's look wait behind that read: ffmpeg would stop for good. Every command turns it off.
QUIET_INPUT = ("-nostdin",)


def one_command(
    ffmpeg: Sequence[str],
    source: PurePath,
    work: PurePath,
    made: Recipe,
    *,
    shader: PurePath | None,
) -> list[str]:
    """The whole conversion in one ffmpeg command, for every method but the AI model's. FAST
    needs Anime4K's shader; progress goes to standard output, as ffmpeg's key=value lines."""
    devices: list[str] = []
    filters: list[str] = [DEINTERLACE] if made.deinterlace else []
    match made.method:
        case Method.FAST:
            if shader is None:
                raise ValueError("The fast upscale needs Anime4K's shader.")
            devices = ["-init_hw_device", "vulkan=vk", "-filter_hw_device", "vk"]
            filters += [
                "hwupload",
                f"libplacebo=w={made.width}:h={made.height}:format=p010le:"
                f"custom_shader_path={_filter_path(shader)}",
                "hwdownload",
                "format=p010le",
                "setsar=1",
            ]
        case Method.REENCODE:
            filters += [_scale(made), "setsar=1", "format=p010le"]
        case _:
            pass  # REMUX copies the picture
    picture = ["-c:v", "copy"] if made.method is Method.REMUX else [*NVENC]
    return [
        *ffmpeg,
        *QUIET_INPUT,
        "-v",
        "error",
        "-y",
        *devices,
        "-i",
        str(source),
        *_maps(0, 0),
        *(["-vf", ",".join(filters)] if filters else []),
        *picture,
        *_streams(made),
        "-progress",
        "pipe:1",
        "-nostats",
        "-f",
        "matroska",
        str(work),
    ]


def decoder_command(ffmpeg: Sequence[str], source: PurePath, made: Recipe) -> list[str]:
    """For the AI model: the picture as raw frames of planar float RGB on standard output."""
    return [
        *ffmpeg,
        *QUIET_INPUT,
        "-v",
        "error",
        "-i",
        str(source),
        "-map",
        "0:V:0",
        *(["-vf", DEINTERLACE] if made.deinterlace else []),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gbrpf32le",
        "-",
    ]


def encoder_command(
    ffmpeg: Sequence[str],
    source: PurePath,
    work: PurePath,
    made: Recipe,
    *,
    upscaled: tuple[int, int],
) -> list[str]:
    """For the AI model: its frames on standard input (`upscaled` big), scaled to the standard's
    size and encoded, with the original's sound, subtitles, fonts and chapters."""
    width, height = upscaled
    return [
        *ffmpeg,
        *QUIET_INPUT,  # its frames still come in on standard input
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gbrpf32le",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{made.frame_rate.numerator}/{made.frame_rate.denominator}",
        "-i",
        "-",
        "-i",
        str(source),
        *_maps(0, 1, picture="0:v"),
        "-vf",
        f"{_scale(made)},setsar=1,format=p010le",
        *NVENC,
        *_streams(made),
        "-f",
        "matroska",
        str(work),
    ]


def interlace_command(ffmpeg: Sequence[str], source: PurePath, *, at: float) -> list[str]:
    """ffmpeg's idet looking at a stretch of the picture from `at` seconds; it reports how many
    frames look interlaced (see `interlaced`)."""
    return [
        *ffmpeg,
        *QUIET_INPUT,
        "-v",
        "info",
        "-nostats",
        "-ss",
        f"{at:.0f}",
        "-i",
        str(source),
        "-map",
        "0:V:0",
        "-frames:v",
        str(_SAMPLE_FRAMES),
        "-vf",
        "idet",
        "-an",
        "-sn",
        "-f",
        "null",
        "-",
    ]


def interlaced(report: str) -> bool:
    """Whether idet's report says the picture is interlaced: more of its frames look it than
    look progressive."""
    for line in report.splitlines():
        if "Multi frame detection" in line:
            counts = _counts(line)
            return counts.get("TFF", 0) + counts.get("BFF", 0) > counts.get("Progressive", 0)
    return False


def check(source: MediaInfo, output: MediaInfo, made: Recipe) -> list[str]:
    """What's wrong with a converted file, in words; nothing when it may replace the original."""
    video = output.video
    if video is None:
        return ["It has no picture"]
    problems: list[str] = []
    want, got = source.duration or 0.0, output.duration or 0.0
    if abs(want - got) > max(1.0, want * 0.005):
        problems.append(f"It's {_clock(got)} long, not {_clock(want)}")
    if made.method is not Method.REMUX and (
        (video.codec, video.bit_depth, video.width, video.height)
        != ("hevc", 10, made.width, made.height)
    ):
        problems.append(
            f"Its picture is {video.codec} {video.bit_depth}-bit {video.width}x{video.height},"
            f" not hevc 10-bit {made.width}x{made.height}"
        )
    problems += _count("sound track", len(output.audio), len(source.audio))
    problems += _count("subtitle track", len(output.subtitles), len(source.subtitles))
    problems += _count("font", output.fonts, source.fonts)
    if output.kura_tag != made.tag:
        problems.append("Kura's tag isn't in it")
    return problems


def _maps(picture_input: int, other_input: int, *, picture: str | None = None) -> list[str]:
    """The picture from one input; sound, subtitles, fonts, chapters and tags from another."""
    other = str(other_input)
    return [
        "-map",
        picture or f"{picture_input}:V:0",  # V: the picture, never a cover image
        "-map",
        f"{other}:a?",
        "-map",
        f"{other}:s?",
        "-map",
        f"{other}:t?",
        "-map_chapters",
        other,
        "-map_metadata",
        other,
    ]


def _streams(made: Recipe) -> list[str]:
    """How the sound, subtitles and fonts are carried, and Kura's tag."""
    parts: list[str] = []
    for audio in made.audio:
        if audio.aac_kbps is None:
            parts += [f"-c:a:{audio.index}", "copy"]
        else:
            parts += [f"-c:a:{audio.index}", "aac", f"-b:a:{audio.index}", f"{audio.aac_kbps}k"]
    for index, way in enumerate(made.subtitles):
        parts += [f"-c:s:{index}", way]
    return [*parts, "-c:t", "copy", "-metadata", f"KURA={made.tag}"]


def _scale(made: Recipe) -> str:
    return f"scale={made.width}:{made.height}:flags=lanczos"


def _filter_path(path: PurePath) -> str:
    r"""A Windows path as a filter's option: forward slashes, the drive's colon escaped, quoted
    ('C\:/Kura/modeA_hq.glsl')."""
    text = str(path).replace("\\", "/").replace(":", "\\:").replace("'", "'\\''")
    return f"'{text}'"


def _counts(line: str) -> dict[str, int]:
    """ "TFF: 420 BFF: 2 Progressive: 150" as {"TFF": 420, ...}."""
    words = line.replace(":", " ").split()
    found: dict[str, int] = {}
    for name, value in pairwise(words):
        if value.isdigit():
            found[name] = int(value)
    return found


def _count(thing: str, got: int, want: int) -> Sequence[str]:
    if got == want:
        return []
    return [f"It has {got} {thing}{'' if got == 1 else 's'}, not {want}"]


def _clock(seconds: float) -> str:
    whole = round(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"
