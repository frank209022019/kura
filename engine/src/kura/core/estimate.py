"""How long converting takes on the graphics card, and how much space the results need.

Until Kura has measured this PC's card, it uses what the owner's GTX 1660 Super managed in the
upscaling test (2026-10-11): about an hour per 24-minute SD episode with the AI model, 10 minutes
for a 720p episode with the fast upscale, 3 minutes to re-encode a 1080p one.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from kura.core.media import MediaInfo
from kura.core.standard import Decision, Method, Standard

FILM = Fraction(24000, 1001)  # assumed when a file doesn't say its frame rate
_MEASURED_ON = 720 * 540  # the SD picture the AI model's speed was measured on


@dataclass(frozen=True)
class Speeds:
    """What this PC's graphics card manages for each method that uses it.

    The AI model's work grows with the source picture, so its speed is in megapixels of source
    per second; the other methods are in frames per second.
    """

    best: float = 3.2  # Real-ESRGAN: 8.2 frames a second from 720x540
    fast: float = 56.5  # Anime4K, 720p to 1080p
    reencode: float = 175.0  # 1080p, decoded on the processor


@dataclass(frozen=True)
class Estimate:
    gpu_seconds: float
    output_bytes: int


NOTHING = Estimate(0.0, 0)


def estimate(
    media: MediaInfo, decision: Decision, standard: Standard, speeds: Speeds | None = None
) -> Estimate:
    speeds = speeds or Speeds()
    seconds = media.duration or 0.0
    match decision.method:
        case Method.SKIP:
            return NOTHING
        case Method.RENAME | Method.REMUX:
            return Estimate(0.0, media.size or 0)  # streams are copied, not encoded
        case Method.BEST:
            fps = speeds.best * 1e6 / _pixels(media)
        case Method.FAST:
            fps = speeds.fast
        case Method.REENCODE:
            fps = speeds.reencode
    rate = media.video.frame_rate if media.video and media.video.frame_rate else FILM
    frames = seconds * float(rate)
    return Estimate(frames / fps, round(seconds / 60 * standard.megabytes_per_minute * 1e6))


def total(estimates: Iterable[Estimate]) -> Estimate:
    gpu_seconds, output_bytes = 0.0, 0
    for part in estimates:
        gpu_seconds += part.gpu_seconds
        output_bytes += part.output_bytes
    return Estimate(gpu_seconds, output_bytes)


def _pixels(media: MediaInfo) -> int:
    video = media.video
    return video.width * video.height if video and video.width and video.height else _MEASURED_ON
