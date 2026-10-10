"""The library standard, and what each file needs to reach it.

Every file is brought to the standard, even a 720p file going to 720p. A file that is already
exactly at the standard (the right picture, MKV, no lossless sound) is only renamed.
"""

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

from kura.core.media import MediaInfo, Video


@dataclass(frozen=True)
class Standard:
    name: str
    height: int  # 1080 or 720; widths follow the picture's shape
    codec: str = "hevc"
    bit_depth: int = 10
    container: str = "mkv"
    ai_for_sd: bool = True  # 480p and 576p get the best-quality AI model
    fast_for_hd: bool = True  # sizes between SD and the standard get the fast upscale
    megabytes_per_minute: float = 18.75  # for estimates: about 450 MB for a 24-minute episode


CINEMA_1080 = Standard("Cinema 1080p", 1080)
COMPACT_720 = Standard("Compact 720p", 720, megabytes_per_minute=250 / 24)


class Method(StrEnum):
    RENAME = "rename"  # already at the standard: only the name changes
    REMUX = "remux"  # the picture stays; the container or lossless sound changes
    REENCODE = "reencode"  # a new picture without AI: another codec, or scaled plainly
    FAST = "fast"  # upscaled with the fast model (Anime4K)
    BEST = "best"  # upscaled with the best-quality AI model (Real-ESRGAN)
    SKIP = "skip"  # nothing to convert


@dataclass(frozen=True)
class Decision:
    method: Method
    width: int = 0
    height: int = 0
    deinterlace: bool = False
    reasons: tuple[str, ...] = ()


SD_HEIGHT = 576  # 480p and 576p are SD
_SAME_SIZE = (0.95, 1.05)  # within 5% of the standard counts as its size (cropped films)


def decide(media: MediaInfo, standard: Standard) -> Decision:
    video = media.video
    if video is None:
        return Decision(Method.SKIP, reasons=("No picture to convert",))

    width, height = _output_size(video.display_aspect, standard)
    deinterlace = video.interlaced is True
    extras = _sound_and_container(media, standard)
    if deinterlace:
        extras = ("Interlaced: deinterlaced first", *extras)

    scale = max(video.height / standard.height, video.width / _box_width(standard))
    if scale < _SAME_SIZE[0]:
        method, reason = _upscale(video, standard)
    elif scale > _SAME_SIZE[1]:
        method, reason = Method.REENCODE, f"{video.height}p: brought down to {standard.height}p"
    elif not _picture_matches(video, standard):
        method, reason = Method.REENCODE, f"{_codec_name(video)} becomes {_target_name(standard)}"
    elif extras:
        return Decision(Method.REMUX, width, height, deinterlace, extras)
    else:
        already = f"Already {standard.height}p {_target_name(standard)} in MKV: only renamed"
        return Decision(Method.RENAME, width, height, reasons=(already,))
    return Decision(method, width, height, deinterlace, (reason, *extras))


def _upscale(video: Video, standard: Standard) -> tuple[Method, str]:
    if video.height <= SD_HEIGHT and standard.ai_for_sd:
        return Method.BEST, f"SD {video.height}p: the AI model brings it to {standard.height}p"
    if video.height > SD_HEIGHT and standard.fast_for_hd:
        return Method.FAST, f"{video.height}p: the fast upscale brings it to {standard.height}p"
    return Method.REENCODE, f"{video.height}p: scaled up to {standard.height}p"


def _sound_and_container(media: MediaInfo, standard: Standard) -> tuple[str, ...]:
    changes: list[str] = []
    if media.container != standard.container:
        changes.append(f"{media.container.upper()} becomes {standard.container.upper()}")
    for codec in dict.fromkeys(audio.codec for audio in media.audio if audio.lossless):
        changes.append(f"Lossless {codec.upper()} sound becomes AAC")
    return tuple(changes)


def _picture_matches(video: Video, standard: Standard) -> bool:
    return video.codec == standard.codec and video.bit_depth == standard.bit_depth


def _output_size(shape: Fraction, standard: Standard) -> tuple[int, int]:
    """The largest size with the picture's shape that fits the standard's 16:9 frame."""
    box_width = _box_width(standard)
    if shape >= Fraction(16, 9):
        return box_width, _even(box_width / shape)
    return _even(standard.height * shape), standard.height


def _box_width(standard: Standard) -> int:
    return _even(Fraction(standard.height * 16, 9))


def _even(value: Fraction | float) -> int:
    return round(value / 2) * 2


_CODEC_NAMES = {
    "h264": "H.264",
    "hevc": "HEVC",
    "mpeg4": "MPEG-4",
    "mpeg2video": "MPEG-2",
    "av1": "AV1",
    "vp9": "VP9",
}


def _codec_name(video: Video) -> str:
    name = _CODEC_NAMES.get(video.codec, video.codec.upper())
    return f"{name} {video.bit_depth}-bit" if video.codec == "hevc" else name


def _target_name(standard: Standard) -> str:
    return f"{_CODEC_NAMES.get(standard.codec, standard.codec.upper())} {standard.bit_depth}-bit"
