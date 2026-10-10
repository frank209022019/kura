"""How long converting takes on the graphics card, and how much space the results need.

Speeds are frames per second for each method. Until Kura has measured this PC's card, it uses
the figures the design assumed for a GTX 1660 Super: about an hour per 24-minute episode with
the best model, 12 minutes with the fast one, 3 minutes to re-encode.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from kura.core.media import MediaInfo
from kura.core.standard import Decision, Method, Standard

FILM = Fraction(24000, 1001)  # assumed when a file doesn't say its frame rate


@dataclass(frozen=True)
class Speeds:
    """Frames per second on this PC's graphics card, for each method that uses it."""

    best: float = 9.6
    fast: float = 48.0
    reencode: float = 192.0


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
            fps = speeds.best
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
