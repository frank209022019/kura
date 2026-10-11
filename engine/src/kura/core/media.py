"""What a video file holds: its picture, sound, subtitles and fonts, read from ffprobe's report.

The report is ffprobe's JSON (`-show_format -show_streams -show_chapters`); running ffprobe is
someone else's job, so everything here is a plain function of that data.
"""

from dataclasses import dataclass
from fractions import Fraction

from kura.core import fields
from kura.core.fields import Json

KURA_TAG = "KURA"  # the tag Kura writes into every file it converts


@dataclass(frozen=True)
class Video:
    codec: str
    width: int
    height: int
    display_aspect: Fraction  # 4/3, 16/9…: the shape on screen, whatever the pixels' shape
    frame_rate: Fraction | None
    bit_depth: int
    interlaced: bool | None  # None: ffprobe couldn't tell; a picture check decides later


@dataclass(frozen=True)
class Audio:
    codec: str
    channels: int
    language: str | None
    lossless: bool


@dataclass(frozen=True)
class Subtitle:
    codec: str
    language: str | None
    text: bool  # text (ASS, SRT) rather than pictures (PGS, DVD)
    forced: bool


@dataclass(frozen=True)
class MediaInfo:
    container: str  # "mkv", "mp4", "avi", "mpeg"…
    duration: float | None  # seconds
    size: int | None  # bytes
    video: Video | None
    audio: tuple[Audio, ...] = ()
    subtitles: tuple[Subtitle, ...] = ()
    fonts: int = 0
    chapters: int = 0
    kura_tag: str | None = None


def media_from_ffprobe(report: Json) -> MediaInfo:
    streams = fields.mappings(report, "streams")
    format_ = fields.mapping(report, "format")
    pictures = [s for s in streams if fields.text(s, "codec_type") == "video" and not _is_cover(s)]
    return MediaInfo(
        container=_container(fields.text(format_, "format_name")),
        duration=fields.decimal(format_, "duration"),
        size=fields.whole(format_, "size"),
        video=_video(pictures[0]) if pictures else None,
        audio=tuple(_audio(s) for s in streams if fields.text(s, "codec_type") == "audio"),
        subtitles=tuple(
            _subtitle(s) for s in streams if fields.text(s, "codec_type") == "subtitle"
        ),
        fonts=sum(1 for s in streams if _is_font(s)),
        chapters=len(fields.mappings(report, "chapters")),
        kura_tag=_tag(format_, KURA_TAG),
    )


_LOSSLESS_AUDIO = frozenset({"flac", "alac", "truehd", "mlp", "wavpack", "tta", "ape"})
_TEXT_SUBTITLES = frozenset({"ass", "ssa", "subrip", "srt", "webvtt", "mov_text", "text"})
_INTERLACED_FIELDS = frozenset({"tt", "bb", "tb", "bt"})


def _video(stream: Json) -> Video:
    width = fields.whole(stream, "width") or 0
    height = fields.whole(stream, "height") or 0
    return Video(
        codec=fields.text(stream, "codec_name") or "unknown",
        width=width,
        height=height,
        display_aspect=_display_aspect(stream, width, height),
        frame_rate=_ratio(fields.text(stream, "avg_frame_rate"))
        or _ratio(fields.text(stream, "r_frame_rate")),
        bit_depth=_bit_depth(stream),
        interlaced=_interlaced(fields.text(stream, "field_order")),
    )


def _audio(stream: Json) -> Audio:
    codec = fields.text(stream, "codec_name") or "unknown"
    lossless = codec in _LOSSLESS_AUDIO or codec.startswith("pcm_")
    if codec == "dts" and "MA" in (fields.text(stream, "profile") or ""):
        lossless = True  # DTS-HD Master Audio
    return Audio(
        codec=codec,
        channels=fields.whole(stream, "channels") or 0,
        language=_language(stream),
        lossless=lossless,
    )


def _subtitle(stream: Json) -> Subtitle:
    codec = fields.text(stream, "codec_name") or "unknown"
    return Subtitle(
        codec=codec,
        language=_language(stream),
        text=codec in _TEXT_SUBTITLES,
        forced=fields.whole(fields.mapping(stream, "disposition"), "forced") == 1,
    )


def _container(format_name: str | None) -> str:
    names = (format_name or "unknown").split(",")
    if "matroska" in names:
        return "mkv"
    if "mp4" in names:
        return "mp4"
    return names[0]


def _display_aspect(stream: Json, width: int, height: int) -> Fraction:
    if (shape := _ratio(fields.text(stream, "display_aspect_ratio"))) is not None:
        return shape
    pixel = _ratio(fields.text(stream, "sample_aspect_ratio")) or Fraction(1)
    return Fraction(width, height) * pixel if height else Fraction(1)


def _bit_depth(stream: Json) -> int:
    pixels = fields.text(stream, "pix_fmt") or ""
    for depth in (16, 12, 10):
        if f"p{depth}" in pixels:
            return depth
    return fields.whole(stream, "bits_per_raw_sample") or 8


def _interlaced(field_order: str | None) -> bool | None:
    if field_order == "progressive":
        return False
    if field_order in _INTERLACED_FIELDS:
        return True
    return None


def _language(stream: Json) -> str | None:
    language = _tag(stream, "language")
    return None if language in (None, "und") else language


def _is_cover(stream: Json) -> bool:
    return fields.whole(fields.mapping(stream, "disposition"), "attached_pic") == 1


def _is_font(stream: Json) -> bool:
    if fields.text(stream, "codec_type") != "attachment":
        return False
    mimetype = (_tag(stream, "mimetype") or "").casefold()
    return "font" in mimetype or (_tag(stream, "filename") or "").casefold().endswith(
        (".ttf", ".otf", ".ttc")
    )


def _tag(data: Json, name: str) -> str | None:
    tags = fields.mapping(data, "tags")
    for key, value in tags.items():
        if key.casefold() == name.casefold() and isinstance(value, str):
            return value
    return None


def _ratio(value: str | None) -> Fraction | None:
    """ffprobe's "24000/1001" or "4:3"; None for "0/0", "0:1" and anything unreadable."""
    if not value:
        return None
    top, _, bottom = value.replace(":", "/").partition("/")
    try:
        ratio = Fraction(int(top), int(bottom or 1))
    except ValueError, ZeroDivisionError:
        return None
    return ratio if ratio > 0 else None
