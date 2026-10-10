"""The reports Kura writes next to each anime, starting with "Kura - Gap analysis.md".

They are plain Markdown, readable without Kura (Plex ignores .md files), and match the title
board in the design word for word.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import PurePath

from kura.core.episodes import EpisodeNumber
from kura.core.estimate import NOTHING, Estimate
from kura.core.standard import SD_HEIGHT, Standard

GAP_ANALYSIS_FILE = "Kura - Gap analysis.md"


class Status(StrEnum):
    READY = "ready"  # at the standard
    CONVERTING = "converting"
    TO_CONVERT = "to convert"
    BROKEN = "broken"
    MISSING = "missing"


@dataclass(frozen=True)
class EpisodeState:
    number: EpisodeNumber
    status: Status
    problem: str | None = None  # what's wrong with a broken file


@dataclass(frozen=True)
class GapAnalysis:
    show: str  # "Dragon Ball Z (1989)"
    library: PurePath
    updated: datetime
    episodes: tuple[EpisodeState, ...]
    conversion: str | None = None  # "SD 480p → 1080p HEVC 10-bit"
    to_convert: Estimate = NOTHING


def gap_analysis_markdown(analysis: GapAnalysis) -> str:
    by_status = {status: [e for e in analysis.episodes if e.status == status] for status in Status}
    present = len(analysis.episodes) - len(by_status[Status.MISSING])
    share = round(present / len(analysis.episodes) * 100) if analysis.episodes else 0

    lines = [
        f"# {analysis.show} — gap analysis",
        f"_Updated {_date(analysis.updated)} · library {analysis.library}_",
        "",
        "## Summary",
        f"- Present: **{present} of {len(analysis.episodes)}** episodes ({share}%)",
        f"- Missing: **{len(by_status[Status.MISSING])}**"
        f" · Broken: **{len(by_status[Status.BROKEN])}**"
        f" · At standard: **{len(by_status[Status.READY])}**",
    ]
    if missing := by_status[Status.MISSING]:
        rows = [
            [e.number.code, str(e.number.absolute), f"Season {e.number.season:02d}"]
            for e in missing
        ]
        lines += ["", "## Missing", *_table(["Episode", "Absolute", "Folder"], rows)]
    if broken := by_status[Status.BROKEN]:
        lines += ["", "## Broken"]
        lines += [
            f"- {e.number.code} ({e.number.absolute}): {e.problem or "doesn't play"}, replace it"
            for e in broken
        ]
    if waiting := by_status[Status.TO_CONVERT]:
        what = f" · {analysis.conversion}" if analysis.conversion else ""
        lines += ["", "## To convert", f"- {len(waiting)} episodes{what}"]
        if analysis.to_convert.gpu_seconds:
            gpu = describe_gpu_time(analysis.to_convert.gpu_seconds)
            lines.append(f"- About {gpu} and {describe_size(analysis.to_convert.output_bytes)}")
    return "\n".join(lines) + "\n"


def conversion_summary(heights: Iterable[int], standard: Standard) -> str:
    """ "SD 480p → 1080p HEVC 10-bit": what the files to convert are, and what they become."""
    sizes = sorted(set(heights))
    sd = [f"{height}p" for height in sizes if height <= SD_HEIGHT]
    parts = [f"SD {' and '.join(sd)}"] if sd else []
    parts += [f"{height}p" for height in sizes if height > SD_HEIGHT]
    target = f"{standard.height}p {standard.codec.upper()} {standard.bit_depth}-bit"
    return f"{', '.join(parts)} → {target}"


def describe_size(size: int) -> str:
    if size < 1e9:
        return f"{round(size / 1e6)} MB"
    if size < 10e9:
        return f"{size / 1e9:.1f} GB"
    if size < 1e12:
        return f"{int(float(f'{size / 1e9:.2g}'))} GB"  # two significant figures
    return f"{size / 1e12:.1f} TB"


def describe_gpu_time(seconds: float) -> str:
    """ "35 GPU hours", "11.7 GPU days": hours up to two days, as the convert board shows."""
    if seconds >= 2 * 86_400:
        return f"{_short(seconds / 86_400)} GPU days"
    if seconds >= 3_600:
        hours = seconds / 3_600
        return f"{round(hours) if hours >= 10 else _short(hours)} GPU hours"
    minutes = max(1, round(seconds / 60))
    return f"{minutes} GPU minute{'s' if minutes != 1 else ''}"


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _date(moment: datetime) -> str:
    """10 Oct 2026, 14:20 (English month names whatever Windows' language)."""
    return f"{moment.day} {_MONTHS[moment.month - 1]} {moment.year}, {moment:%H:%M}"


def _short(value: float) -> str:
    return f"{value:.1f}".removesuffix(".0")


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    widths = [max(len(cell) for cell in column) for column in zip(header, *rows, strict=True)]

    def line(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True)) + " |"

    return [line(header), "|" + "|".join("-" * (w + 2) for w in widths) + "|", *map(line, rows)]
