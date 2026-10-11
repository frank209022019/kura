"""The reports Kura writes next to each anime: "Kura - Gap analysis.md", worded by
kura/core/report.py. Plex ignores .md files.

A report only goes into a folder of the title's own: never a library folder itself, and never a
folder that holds another anime's videos (a mixed Downloads folder gets none; once tidied, each
show has its folder and its report). A report whose news hasn't changed isn't rewritten.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path, PureWindowsPath

from kura.core.catalog import Show
from kura.core.episodes import EpisodeNumber
from kura.core.estimate import Estimate, estimate, total
from kura.core.gaps import find_gaps
from kura.core.media import media_from_ffprobe
from kura.core.report import (
    GAP_ANALYSIS_FILE,
    EpisodeState,
    GapAnalysis,
    SpecialState,
    Status,
    conversion_summary,
    gap_analysis_markdown,
)
from kura.core.standard import CINEMA_1080, COMPACT_720, Method, Standard, decide
from kura.titles import held, show_of

log = logging.getLogger(__name__)

_SEASON_FOLDER = ("season ", "specials")


@dataclass(frozen=True)
class Written:
    reports: int
    problems: tuple[str, ...]  # folders Kura couldn't write to, in words


def write_reports(conn: sqlite3.Connection, *, now: datetime) -> Written:
    """Writes or refreshes the gap analysis of every series that has a folder of its own."""
    standard = library_standard(conn)
    roots = [Path(row["path"]) for row in conn.execute("SELECT path FROM folders")]
    written = 0
    problems: list[str] = []
    for row in conn.execute("SELECT id, name, year FROM titles WHERE kind != 'movie'").fetchall():
        folder = own_folder(conn, row["id"], roots)
        show = show_of(conn, row["id"])
        if folder is None or show is None:
            continue
        root = next(r for r in roots if folder.is_relative_to(r))
        analysis = _analysis(conn, row, show, root, standard, now)
        try:
            if _write(folder / GAP_ANALYSIS_FILE, gap_analysis_markdown(analysis)):
                written += 1
        except OSError as error:
            log.warning("Kura couldn't write a report in %s: %s", folder, error)
            problems.append(
                f"Kura couldn't write the report in {folder}: {error.strerror or error}."
            )
    return Written(written, tuple(problems))


def own_folder(conn: sqlite3.Connection, title_id: int, roots: list[Path]) -> Path | None:
    """The folder that holds a title's videos and nothing of another anime's, or None."""
    paths = [
        Path(row["path"])
        for row in conn.execute(
            "SELECT path FROM files WHERE title_id = ? AND gone_at IS NULL", (title_id,)
        )
    ]
    folders = {_show_folder(path.parent) for path in paths}
    if len(folders) != 1:
        return None
    [folder] = folders
    if not any(folder != root and folder.is_relative_to(root) for root in roots):
        return None  # a library folder itself, or a folder outside the library
    others = conn.execute(
        """SELECT path FROM files
           WHERE gone_at IS NULL AND title_id IS NOT NULL AND title_id != ?""",
        (title_id,),
    )
    if any(Path(row["path"]).is_relative_to(folder) for row in others):
        return None  # shared with another anime
    return folder


def library_standard(conn: sqlite3.Connection) -> Standard:
    """The standard the owner chose in setup, with their upscaling choices."""
    stored = {
        row["key"]: json.loads(row["value"]) for row in conn.execute("SELECT * FROM settings")
    }
    base = COMPACT_720 if stored.get("standard") == "compact-720" else CINEMA_1080
    return replace(
        base,
        ai_for_sd=stored.get("upscale_sd", True) is not False,
        fast_for_hd=stored.get("upscale_720", True) is not False,
    )


def _analysis(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    show: Show,
    root: Path,
    standard: Standard,
    now: datetime,
) -> GapAnalysis:
    files = {
        (f["season"], f["episode"]): f
        for f in conn.execute(
            """SELECT season, episode, episode_end, problem, probe FROM files
               WHERE title_id = ? AND gone_at IS NULL AND season IS NOT NULL""",
            (row["id"],),
        )
    }
    covering: dict[tuple[int, int], sqlite3.Row] = {}
    for (season, first), file in files.items():
        for number in range(first, (file["episode_end"] or first) + 1):
            covering[(season, number)] = file
    gaps = find_gaps(show, held(conn, row["id"]), now.date())
    states: list[EpisodeState] = []
    to_convert: list[Estimate] = []
    heights: list[int] = []
    absolute = 0
    for number in show.seasons:
        for episode in show.season(number):
            if episode in gaps.upcoming:
                continue
            absolute += 1
            where = EpisodeNumber(number, episode.number, absolute)
            file = covering.get((number, episode.number))
            if file is None:
                states.append(EpisodeState(where, Status.MISSING))
            elif file["problem"] or not file["probe"]:
                states.append(EpisodeState(where, Status.BROKEN, file["problem"]))
            else:
                media = media_from_ffprobe(json.loads(file["probe"]))
                decision = decide(media, standard)
                if decision.method is Method.RENAME:
                    states.append(EpisodeState(where, Status.READY))
                else:
                    states.append(EpisodeState(where, Status.TO_CONVERT))
                    to_convert.append(estimate(media, decision, standard))
                    if media.video:
                        heights.append(media.video.height)
    name = f"{row['name']} ({row['year']})" if row["year"] else row["name"]
    return GapAnalysis(
        show=name,
        library=PureWindowsPath(root),
        updated=now,
        episodes=tuple(states),
        conversion=conversion_summary(heights, standard) if heights else None,
        to_convert=total(to_convert),
        specials=tuple(SpecialState(e.number, e.title, e.aired) for e in gaps.specials_missing),
    )


def _show_folder(folder: Path) -> Path:
    """A "Season 02" or "Specials" folder belongs to the show folder above it."""
    if folder.name.casefold().startswith(_SEASON_FOLDER):
        return folder.parent
    return folder


def _write(path: Path, text: str) -> bool:
    """Writes the report unless only its "Updated" line would change. True if it wrote."""
    try:
        before = path.read_text(encoding="utf-8")
    except OSError:
        before = None
    if before is not None and _news(before) == _news(text):
        return False
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def _news(text: str) -> list[str]:
    return [line for line in text.splitlines() if not line.startswith("_Updated ")]
