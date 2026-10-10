"""What a video file holds: its picture, sound, subtitles and fonts, read from ffprobe's report.

The report is ffprobe's JSON (`-show_format -show_streams -show_chapters`); running ffprobe is
someone else's job, so everything here is a plain function of that data.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import cast

type Json = Mapping[str, object]

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
    streams = _list(report, "streams")
    format_ = _map(report, "format")
    pictures = [s for s in streams if _text(s, "codec_type") == "video" and not _is_cover(s)]
    return MediaInfo(
        container=_container(_text(format_, "format_name")),
        duration=_decimal(format_, "duration"),
        size=_whole(format_, "size"),
        video=_video(pictures[0]) if pictures else None,
        audio=tuple(_audio(s) for s in streams if _text(s, "codec_type") == "audio"),
        subtitles=tuple(_subtitle(s) for s in streams if _text(s, "codec_type") == "subtitle"),
        fonts=sum(1 for s in streams if _is_font(s)),
        chapters=len(_list(report, "chapters")),
        kura_tag=_tag(format_, KURA_TAG),
    )


_LOSSLESS_AUDIO = frozenset({"flac", "alac", "truehd", "mlp", "wavpack", "tta", "ape"})
_TEXT_SUBTITLES = frozenset({"ass", "ssa", "subrip", "srt", "webvtt", "mov_text", "text"})
_INTERLACED_FIELDS = frozenset({"tt", "bb", "tb", "bt"})


def _video(stream: Json) -> Video:
    width = _whole(stream, "width") or 0
    height = _whole(stream, "height") or 0
    return Video(
        codec=_text(stream, "codec_name") or "unknown",
        width=width,
        height=height,
        display_aspect=_display_aspect(stream, width, height),
        frame_rate=_ratio(_text(stream, "avg_frame_rate")) or _ratio(_text(stream, "r_frame_rate")),
        bit_depth=_bit_depth(stream),
        interlaced=_interlaced(_text(stream, "field_order")),
    )


def _audio(stream: Json) -> Audio:
    codec = _text(stream, "codec_name") or "unknown"
    lossless = codec in _LOSSLESS_AUDIO or codec.startswith("pcm_")
    if codec == "dts" and "MA" in (_text(stream, "profile") or ""):
        lossless = True  # DTS-HD Master Audio
    return Audio(
        codec=codec,
        channels=_whole(stream, "channels") or 0,
        language=_language(stream),
        lossless=lossless,
    )


def _subtitle(stream: Json) -> Subtitle:
    codec = _text(stream, "codec_name") or "unknown"
    return Subtitle(
        codec=codec,
        language=_language(stream),
        text=codec in _TEXT_SUBTITLES,
        forced=_whole(_map(stream, "disposition"), "forced") == 1,
    )


def _container(format_name: str | None) -> str:
    names = (format_name or "unknown").split(",")
    if "matroska" in names:
        return "mkv"
    if "mp4" in names:
        return "mp4"
    return names[0]


def _display_aspect(stream: Json, width: int, height: int) -> Fraction:
    if (shape := _ratio(_text(stream, "display_aspect_ratio"))) is not None:
        return shape
    pixel = _ratio(_text(stream, "sample_aspect_ratio")) or Fraction(1)
    return Fraction(width, height) * pixel if height else Fraction(1)


def _bit_depth(stream: Json) -> int:
    pixels = _text(stream, "pix_fmt") or ""
    for depth in (16, 12, 10):
        if f"p{depth}" in pixels:
            return depth
    return _whole(stream, "bits_per_raw_sample") or 8


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
    return _whole(_map(stream, "disposition"), "attached_pic") == 1


def _is_font(stream: Json) -> bool:
    if _text(stream, "codec_type") != "attachment":
        return False
    mimetype = (_tag(stream, "mimetype") or "").casefold()
    return "font" in mimetype or (_tag(stream, "filename") or "").casefold().endswith(
        (".ttf", ".otf", ".ttc")
    )


def _tag(data: Json, name: str) -> str | None:
    tags = _map(data, "tags")
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


def _text(data: Json, key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) else None


def _whole(data: Json, key: str) -> int | None:
    value = data.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _decimal(data: Json, key: str) -> float | None:
    value = data.get(key)
    try:
        return float(value) if isinstance(value, (str, int, float)) else None
    except ValueError:
        return None


def _map(data: Json, key: str) -> Json:
    value = data.get(key)
    return cast("Json", value) if isinstance(value, Mapping) else {}


def _list(data: Json, key: str) -> list[Json]:
    value = data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    items = cast("Sequence[object]", value)
    return [cast("Json", item) for item in items if isinstance(item, Mapping)]
