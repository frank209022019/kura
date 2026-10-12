"""Converting one file, start to finish.

The picture is looked at for interlacing (idet) when ffprobe couldn't tell, then made by the
method its recipe names (kura/core/convert.py): the AI model between two ffmpegs (kura/upscale.py)
or one ffmpeg command. The result is checked (length, streams, Kura's tag, a test play at three
points) and only then takes the original's place, the original going to quarantine on its own
drive. Both moves are journaled (kura/changes.py), so a crash leaves nothing half done, and
`restore` puts the original back.

The work happens beside the original, in a file whose name ends in .kura-converting: no scan or
watcher counts it as a video, and it moves into place on the same drive at once. A crash while
it moves leaves the job "replacing": `settle` finishes it, or puts the original back. When
another app has the original open (a player playing it), the checked result waits beside it
(InUseError) and `put_in` puts it in place once the app lets go.
"""

import json
import logging
import shutil
import sqlite3
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, ExitStack, nullcontext
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path, PurePath
from typing import IO, Literal, Protocol, cast

from kura import __version__
from kura.changes import (
    ChangeState,
    SavedChange,
    apply_plan,
    changes_of,
    save_plan,
    undo_plan,
)
from kura.core.convert import (
    QUIET_INPUT,
    Recipe,
    check,
    decoder_command,
    encoder_command,
    interlace_command,
    interlaced,
    one_command,
    recipe,
)
from kura.core.estimate import FILM, estimate
from kura.core.fields import Json
from kura.core.library import WORKING, drive_of, work_of
from kura.core.media import MediaInfo, Video, media_from_ffprobe
from kura.core.naming import unique_path
from kura.core.plan import Change, ChangeKind, Plan, quarantine_place
from kura.core.standard import Decision, Method, Standard, decide, deinterlaced
from kura.probe import ProbeError, ProbeToolError
from kura.system import in_use
from kura.upscale import UpscaleError, Upscaler, pipe, upscaled_size

log = logging.getLogger(__name__)

SHADER = Path(__file__).parent / "assets" / "anime4k-mode-a-hq.glsl"  # the fast upscale
CONVERTED = (Method.REMUX, Method.REENCODE, Method.FAST, Method.BEST)  # what a job can be
_UPSCALES = (Method.BEST, Method.FAST, Method.REENCODE)  # heaviest first
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PLAY_SECONDS = 5  # how much of the result a test play decodes, at each of three points
_LOOK_TIMEOUT = 300  # seconds for idet or a test play
SPACE_MARGIN = 1.25  # free space wanted, over the estimated size of the result
_SAID_LINES = 400  # of what ffmpeg says, kept for "Copy full log"
_HELD_TRIES = 5  # times Kura tries to take away a result Windows holds a moment
_HELD_PAUSE = 0.2  # seconds between them
IN_USE_WAIT = timedelta(minutes=5)  # before a result waiting for its original is tried again

type Stage = Literal["looking", "converting", "checking", "replacing"]


@dataclass(frozen=True)
class Progress:
    stage: Stage
    frames: int  # done so far
    total: int  # in all, as far as Kura can tell


class ConvertError(Exception):
    """The file couldn't be converted, and the original is as it was. The message says why, and
    `log` holds what ffmpeg said, when it was ffmpeg that stopped."""

    def __init__(self, message: str, log: str | None = None) -> None:
        super().__init__(message)
        self.log = log


class NoRoomError(ConvertError):
    """There isn't room on the file's drive ("D:") for the result."""

    def __init__(self, drive: str, needed: int, free: int) -> None:
        super().__init__(
            f"There isn't room on {drive} for the next file: it needs about {needed / 1e9:.1f} GB,"
            f" and {free / 1e9:.1f} GB is free."
        )
        self.drive = drive


class InUseError(ConvertError):
    """Another app has the original open (a player playing it), so it can't be set aside: the
    checked result waits beside it, and the job is tried again with `put_in`."""


class Stopped(Exception):  # noqa: N818 - not an error: the owner paused or skipped it
    """Converting stopped because the owner asked; nothing changed."""


class Starter(Protocol):
    """Starts a program, as subprocess.Popen does."""

    def __call__(
        self,
        command: Sequence[str],
        *,
        stdin: int | None = None,
        stdout: int | None = None,
        stderr: int | None = None,
    ) -> subprocess.Popen[bytes]: ...


def start(
    command: Sequence[str],
    *,
    stdin: int | None = None,
    stdout: int | None = None,
    stderr: int | None = None,
) -> subprocess.Popen[bytes]:
    """A program without a console window (the engine has none), and with nothing on standard
    input unless it's given frames there: the engine's own input is the app's (see QUIET_INPUT)."""
    return subprocess.Popen(  # noqa: S603 - Kura's own ffmpeg, never a shell
        list(command),
        stdin=subprocess.DEVNULL if stdin is None else stdin,
        stdout=stdout,
        stderr=stderr,
        creationflags=_NO_WINDOW,
    )


@dataclass(frozen=True)
class Programs:
    """What converting runs: ffmpeg (a command, so tests can stand in for it), ffprobe on a file,
    the AI model for frames of a size, and Anime4K's shader."""

    ffmpeg: Sequence[str]
    read: Callable[[Path], Json]
    model: Callable[[int, int], Upscaler]
    shader: Path
    start: Starter = field(default=start)


def convert(
    conn: sqlite3.Connection,
    job_id: int,
    programs: Programs,
    standard: Standard,
    *,
    now: Callable[[], datetime],
    report: Callable[[Progress], None],
    stop: Callable[[], bool],
    discard: Callable[[], bool],
    hold: Callable[[], AbstractContextManager[None]] = nullcontext,
) -> None:
    """Converts a job's file and puts the result in its place, `hold` holding scans off while
    it moves. `stop` stops it while the file is being made; once it's made, it's checked and put
    in place unless `discard` says to throw it away (the owner skipped it, say). Raises
    ConvertError when it can't (the original stays as it was), or Stopped when asked."""
    row = _job(conn, job_id)
    source = Path(row["path"])
    _still_as_read(source, row["size"], row["modified"])
    media = media_from_ffprobe(json.loads(row["probe"]))
    decision = decide(media, standard)
    if decision.method not in CONVERTED or media.video is None:
        raise ConvertError("It's at your standard already, so there's nothing to convert.")
    decision = replace(decision, method=lighter(decision.method, Method(row["method"])))
    total = _frames(media)
    report(Progress("looking", 0, total))
    if media.video.interlaced is None and _looks_interlaced(programs, source, media):
        decision = deinterlaced(decision)
    made = recipe(
        source, media, decision, tag=f"{decision.method} to {standard.height}p · Kura {__version__}"
    )
    _name_free(source, Path(made.output))
    _enough_space(source, media, decision, standard)
    work = work_of(source)
    _clear(work)
    try:
        if made.method is Method.BEST:
            _with_model(programs, source, work, made, media.video, total, report, stop)
        else:
            _in_one_command(programs, source, work, made, total, report, stop)
        report(Progress("checking", total, total))
        try:
            result = programs.read(work)
        except (ProbeError, ProbeToolError) as error:
            raise ConvertError(f"The result couldn't be read back: {error}") from None
        problems = check(media, media_from_ffprobe(result), made)
        problems += _play(programs, work, media.duration or 0.0)
        if problems:
            raise ConvertError(
                f"The result didn't check out: {problems[0]}. The original is as it was."
            )
    except BaseException:
        _discard(work)
        raise
    report(Progress("replacing", total, total))
    with ExitStack() as held:
        try:
            held.enter_context(hold())
            if discard():
                raise Stopped
            _still_as_read(source, row["size"], row["modified"])  # nothing saved over it since
        except BaseException:
            _discard(work)  # never put in place: nothing to keep
            raise
        if in_use(source):
            _keep(conn, row, result, made.method)
            raise InUseError(_open_elsewhere(row))
        _replace(conn, row, source, work, made.output, made.method, result, now())


def put_in(conn: sqlite3.Connection, job_id: int, *, now: datetime) -> None:
    """Puts a result that waited beside its original (InUseError) in the original's place. The
    caller holds scans off. Raises InUseError while the original is still open, and ConvertError
    when the result can't go in: it went, or the original changed since it was made."""
    row = _job(conn, job_id)
    source = Path(row["path"])
    work = work_of(source)
    if row["output_probe"] is None or not work.is_file():
        raise ConvertError("Its converted copy isn't there any more. Try again to convert it anew.")
    _still_as_read(source, row["source_size"], row["source_modified"])
    if in_use(source):
        raise InUseError(_open_elsewhere(row))
    result: Json = json.loads(row["output_probe"])
    method = Method(row["method"])
    _replace(conn, row, source, work, source.with_suffix(".mkv"), method, result, now)


def throw_away_kept(conn: sqlite3.Connection, job_id: int) -> None:
    """Takes away the result a job kept beside its original (InUseError), once the job won't put
    it in place: skipped, taken out of the queue, or failed. A job without one keeps its file."""
    row = conn.execute(
        """SELECT f.path FROM jobs AS j JOIN files AS f ON f.id = j.file_id
           WHERE j.id = ? AND j.retry_at IS NOT NULL""",
        (job_id,),
    ).fetchone()
    if row is None:
        return
    path = Path(row["path"])
    _discard(work_of(path))


def _keep(conn: sqlite3.Connection, row: sqlite3.Row, result: Json, method: Method) -> None:
    """What `put_in` needs of a result kept beside its original: what it is, how it was made,
    and the original as it was made from."""
    with conn:
        conn.execute(
            """UPDATE jobs SET method = ?, output_probe = ?, source_size = ?, source_modified = ?
               WHERE id = ?""",
            (
                method.value,
                json.dumps(result, separators=(",", ":")),
                row["size"],
                row["modified"],
                row["id"],
            ),
        )


def _open_elsewhere(row: sqlite3.Row) -> str:
    minutes = round(IN_USE_WAIT.total_seconds() / 60)
    return (
        f"{label_of(row)} is open in another app, maybe your player. Kura will try again in "
        f"{minutes} minutes."
    )


def lighter(decided: Method, chosen: Method) -> Method:
    """The method a file gets when the owner chose one for it: never more than suits it (the AI
    model only for SD), and lighter when they asked (Anime4K, or only a re-encode, for speed)."""
    if decided in _UPSCALES and chosen in _UPSCALES:
        return max(decided, chosen, key=_UPSCALES.index)
    return decided


def restore(conn: sqlite3.Connection, job_id: int, *, now: datetime) -> None:
    """Puts a converted file's original back, and the converted copy away. The original comes
    back where the converted file is now (a tidy-up may have filed it since), under that name with
    its own extension. It works for a conversion that failed after setting its original aside."""
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    plan_id: int | None = job["plan_id"] if job else None
    set_aside = _set_aside(conn, plan_id)
    if job is None or plan_id is None or set_aside is None or job["state"] == "restored":
        raise ConvertError("Kura has no converted file to put back for that.")
    if set_aside.cleared_at is not None:
        raise ConvertError("Its original was cleared out of quarantine, so it can't come back.")
    _follow_the_copy(conn, plan_id, job["file_id"])
    undo_plan(conn, plan_id, now=now)
    set_aside, moved = _set_aside(conn, plan_id), _moved(conn, plan_id)
    if set_aside is None or set_aside.state is not ChangeState.UNDONE:
        problem = set_aside.problem if set_aside else None
        raise ConvertError(problem or "Kura couldn't put the original back.")
    if moved is not None:
        _take_away(moved.source)  # the converted copy, taken out of the way
    original = set_aside.source
    probe = json.loads(job["source_probe"])
    _record(conn, job["file_id"], original, job["source_size"], job["source_modified"], probe, now)
    with conn:  # it keeps when it finished: History says how long converting took
        conn.execute("UPDATE jobs SET state = 'restored' WHERE id = ?", (job_id,))


def settle(
    conn: sqlite3.Connection, job_id: int, read: Callable[[Path], Json] | None, now: datetime
) -> None:
    """A job a crash stopped while its result was taking its original's place (its changes as
    kura/changes.py's `recover` left them): finished when the result can still go in, or else
    the original is put back and the job waits in the queue again. `read` is ffprobe, when
    Kura has it; without it the next scan reads the result."""
    job = conn.execute("SELECT file_id, plan_id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    plan_id: int | None = job["plan_id"] if job else None
    moved = _moved(conn, plan_id)
    carry_on = moved is not None and moved.state is ChangeState.PLANNED and moved.source.exists()
    if plan_id is not None and carry_on:  # the result was checked before the crash
        apply_plan(conn, plan_id, now=now)
        moved = _moved(conn, plan_id)
    if moved is not None and moved.state is ChangeState.DONE:
        try:
            result = read(moved.target) if read else None
        except ProbeError, ProbeToolError:
            result = None
        if result is not None:
            finish(conn, job_id, result, now)
            return
        with conn:  # in place, but unread: the next scan reads it
            conn.execute(
                "UPDATE files SET path = ?, probed_at = NULL, gone_at = NULL WHERE id = ?",
                (str(moved.target), job["file_id"]),
            )
            conn.execute(
                """UPDATE jobs SET state = 'done', finished_at = COALESCE(finished_at, ?),
                          retry_at = NULL
                   WHERE id = ?""",
                (now.isoformat(), job_id),
            )
        return
    if plan_id is not None:
        undo_plan(conn, plan_id, now=now)
        if moved is not None:
            _take_away(moved.source)  # the result, never in place
    with conn:  # a result kept beside its original (InUseError) that never began going in waits on
        conn.execute(
            """UPDATE jobs SET state = 'queued', plan_id = NULL, started_at = NULL,
                      retry_at = CASE WHEN ? THEN retry_at END,
                      finished_at = CASE WHEN ? THEN finished_at END
               WHERE id = ?""",
            (plan_id is None, plan_id is None, job_id),
        )


def _take_away(result: Path) -> None:
    """Removes a result that never went in, or came back out: only ever a file named as Kura's
    work in progress, whatever a damaged or imported journal says."""
    if result.name.endswith(WORKING):
        _discard(result)


def _discard(result: Path) -> None:
    """Takes away a result that won't go in. Windows may hold it a moment after its ffmpeg ends
    (an antivirus looking at it, say), so Kura tries a few times; one still held is left for the
    next try, which takes it away first. Never what decides how a conversion went."""
    for tried in range(1, _HELD_TRIES + 1):
        try:
            result.unlink(missing_ok=True)
            return
        except OSError:
            if tried == _HELD_TRIES:
                log.warning("Couldn't remove %s; the next try takes it away", result)
                return
            time.sleep(_HELD_PAUSE)


def _moved(conn: sqlite3.Connection, plan_id: int | None) -> SavedChange | None:
    """A conversion plan's second change: the result into its original's place."""
    if plan_id is None:
        return None
    return next((c for c in changes_of(conn, plan_id) if c.kind is ChangeKind.MOVE), None)


def _set_aside(conn: sqlite3.Connection, plan_id: int | None) -> SavedChange | None:
    """A conversion plan's first change: the original into quarantine."""
    if plan_id is None:
        return None
    return next((c for c in changes_of(conn, plan_id) if c.kind is ChangeKind.QUARANTINE), None)


def _follow_the_copy(conn: sqlite3.Connection, plan_id: int, file_id: int) -> None:
    """When a tidy-up has moved the converted file since (its record followed it), the plan's
    changes are pointed at where it is now: putting the original back then takes the converted
    file from there, and the original takes its place, with the original's own extension."""
    moved, set_aside = _moved(conn, plan_id), _set_aside(conn, plan_id)
    row = conn.execute("SELECT path FROM files WHERE id = ?", (file_id,)).fetchone()
    if moved is None or set_aside is None or row is None or moved.state is not ChangeState.DONE:
        return
    now_at = Path(row["path"])
    if str(now_at) == str(moved.target):
        return
    with conn:
        conn.execute(
            "UPDATE changes SET source = ?, target = ? WHERE id = ?",
            (str(work_of(now_at)), str(now_at), moved.id),
        )
        conn.execute(
            "UPDATE changes SET source = ? WHERE id = ?",
            (str(now_at.with_suffix(set_aside.source.suffix)), set_aside.id),
        )


def _job(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row:
    row = conn.execute(
        """SELECT j.id, j.file_id, j.method, j.output_probe, j.source_size, j.source_modified,
                  f.path, f.size, f.modified, f.probe, f.season, f.episode, t.name AS title
           FROM jobs AS j JOIN files AS f ON f.id = j.file_id
           LEFT JOIN titles AS t ON t.id = f.title_id
           WHERE j.id = ? AND f.gone_at IS NULL""",
        (job_id,),
    ).fetchone()
    if row is None or row["probe"] is None:
        raise ConvertError("That file isn't in the library any more, or hasn't been read.")
    return row


def _still_as_read(source: Path, size: int, modified: int) -> None:
    try:
        now = source.stat()
    except OSError:
        raise ConvertError(f"It isn't at {source} any more.") from None
    if (now.st_size, now.st_mtime_ns) != (size, modified):
        raise ConvertError("It changed since Kura read it: a scan reads it again, then it can go.")


def _frames(media: MediaInfo) -> int:
    rate = media.video.frame_rate if media.video and media.video.frame_rate else FILM
    return round((media.duration or 0.0) * float(rate))


def _looks_interlaced(programs: Programs, source: Path, media: MediaInfo) -> bool:
    """idet's look at a stretch from the middle of the picture."""
    command = interlace_command(programs.ffmpeg, source, at=(media.duration or 0.0) / 2)
    done = _run(programs, command)
    return interlaced(done.stderr.decode("utf-8", "replace"))


def _name_free(source: Path, output: Path) -> None:
    """The result takes the original's name as an MKV: a file there already (an MKV beside an
    MP4 of the same name) would only be found once it's made, so it's looked for first."""
    if str(output).casefold() != str(source).casefold() and output.exists():
        raise ConvertError(
            f"{output.name} is beside it already, and the converted file would take that name. "
            "Tidy up first, or move one of them."
        )


def _clear(work: Path) -> None:
    """Takes away what an earlier try left of the result (a crash, say)."""
    try:
        work.unlink(missing_ok=True)
    except OSError:
        raise ConvertError(
            "Its unfinished copy from an earlier try is still in use, so it can't start over yet."
            " Try again in a minute."
        ) from None


def room_for(media: MediaInfo, decision: Decision, standard: Standard) -> int:
    """The free space a file's result wants on its drive, in bytes: its size, as estimated, with
    a margin."""
    return round(estimate(media, decision, standard).output_bytes * SPACE_MARGIN)


def _enough_space(source: Path, media: MediaInfo, decision: Decision, standard: Standard) -> None:
    needed = room_for(media, decision, standard)
    free = shutil.disk_usage(source.parent).free
    if free < needed:
        raise NoRoomError(drive_of(source) or str(source.parent), needed, free)


def _with_model(
    programs: Programs,
    source: Path,
    work: Path,
    made: Recipe,
    video: Video,
    total: int,
    report: Callable[[Progress], None],
    stop: Callable[[], bool],
) -> None:
    """The AI model between a decoder and an encoder."""
    try:
        upscale = programs.model(video.width, video.height)
        size = upscaled_size(upscale, video.width, video.height)
    except UpscaleError as error:
        raise ConvertError(str(error)) from error
    decoder = programs.start(
        decoder_command(programs.ffmpeg, source, made),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    encoder = programs.start(
        encoder_command(programs.ffmpeg, source, work, made, upscaled=size),
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    decoding, encoding = _Said(decoder.stderr), _Said(encoder.stderr)
    reached = [0]  # frames made so far

    def done(count: int) -> None:
        reached[0] = count
        report(Progress("converting", count, total))

    try:
        pipe(
            cast("IO[bytes]", decoder.stdout),
            cast("IO[bytes]", encoder.stdin),
            upscale,
            video.width,
            video.height,
            done=done,
            stop=stop,
        )
    except UpscaleError as error:
        _end(decoder, encoder)
        log = _log(decoding, encoding, stopped=(reached[0], total))
        raise ConvertError(f"{error} {encoding.last() or decoding.last()}".strip(), log) from error
    if stop():
        _end(decoder, encoder)
        raise Stopped
    if decoder.wait() != 0:
        _end(encoder)
        played = _clock(reached[0] / float(made.frame_rate), whole=True)
        raise ConvertError(
            f"It couldn't be read past {played} ({decoding.last() or 'ffmpeg stopped'}). The "
            "original is untouched and plays up to there.",
            _log(decoding, encoding, stopped=(reached[0], total)),
        )
    if encoder.wait() != 0:
        raise ConvertError(
            f"ffmpeg couldn't encode it: {encoding.last() or 'it stopped'}.",
            _log(decoding, encoding, stopped=(reached[0], total)),
        )


def _in_one_command(
    programs: Programs,
    source: Path,
    work: Path,
    made: Recipe,
    total: int,
    report: Callable[[Progress], None],
    stop: Callable[[], bool],
) -> None:
    """One ffmpeg, its progress read from its standard output."""
    command = one_command(programs.ffmpeg, source, work, made, shader=programs.shader)
    process = programs.start(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    said = _Said(process.stderr)
    frames = 0
    for line in cast("IO[bytes]", process.stdout):
        if stop():
            _end(process)
            raise Stopped
        if line.startswith(b"frame="):
            frames = int(line.split(b"=", 1)[1].strip() or 0)
            report(Progress("converting", frames, total))
    if process.wait() != 0:
        reached = f" past {_clock(frames / float(made.frame_rate), whole=True)}" if frames else ""
        raise ConvertError(
            f"ffmpeg couldn't convert it{reached}: {said.last() or 'it stopped'}.",
            _log(said, stopped=(frames, total)),
        )


def _play(programs: Programs, work: Path, duration: float) -> list[str]:
    """A test play of the result at three points: what went wrong, if anything."""
    problems: list[str] = []
    for share in (0.1, 0.5, 0.9):
        at = max(0.0, duration * share - _PLAY_SECONDS / 2)
        command = [
            *programs.ffmpeg,
            *QUIET_INPUT,
            "-v",
            "error",
            "-xerror",
            "-ss",
            f"{at:.1f}",
            "-i",
            str(work),
            "-t",
            str(_PLAY_SECONDS),
            "-map",
            "0:V:0",
            "-map",
            "0:a?",
            "-f",
            "null",
            "-",
        ]
        done = _run(programs, command)
        said = done.stderr.decode("utf-8", "replace").strip()
        if done.returncode != 0 or said:
            first = said.splitlines()[0] if said else f"ffmpeg stopped with {done.returncode}"
            problems.append(f"it didn't play at {_clock(at)} ({first})")
            break
    return problems


def _log(*said: _Said, stopped: tuple[int, int]) -> str:
    """What ffmpeg said, for "Copy full log", and where it stopped."""
    reached, total = stopped
    lines = [line for each in said for line in each.lines()]
    return "\n".join([*lines, f"Stopped at frame {reached:,} of {total:,}."])


def _replace(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    source: Path,
    work: Path,
    output: PurePath,
    method: Method,
    result: Json,
    now: datetime,
) -> None:
    """The original to quarantine and the result into its place, journaled; then the library's
    record of the file describes the result, keeping what it was identified as."""
    label = label_of(row)
    place = _free_place(source, now)
    plan = Plan(
        (
            Change(
                ChangeKind.QUARANTINE,
                source,
                place,
                f"{label} · original",
                "Set aside: its converted copy takes its place",
            ),
            Change(ChangeKind.MOVE, work, output, label, f"Converted ({method})"),
        )
    )
    plan_id = save_plan(conn, plan, f"Converted {label}", now=now, kind="convert")
    original = source.stat()
    with conn:
        conn.execute(
            """UPDATE jobs SET state = 'replacing', plan_id = ?, method = ?, source_size = ?,
                      source_modified = ?, source_probe = ?
               WHERE id = ?""",
            (
                plan_id,
                method.value,
                original.st_size,
                original.st_mtime_ns,
                row["probe"],
                row["id"],
            ),
        )
    outcome = apply_plan(conn, plan_id, now=now)
    if outcome.problems:
        undone = undo_plan(conn, plan_id, now=now)
        if not undone.problems and in_use(source):  # a player opened it a moment ago
            _forget(conn, plan_id, row["id"])  # nothing moved: it leaves no trace
            _keep(conn, row, result, method)
            raise InUseError(_open_elsewhere(row))
        _discard(work)
        problem = outcome.problems[0].problem
        if undone.problems:  # the original stays in quarantine: History can still put it back
            raise ConvertError(
                f"Kura couldn't put it in place ({problem}), nor the original back: it's in "
                f"{place}. Put it back from History."
            )
        raise ConvertError(f"Kura couldn't put it in place, so the original is back: {problem}")
    finish(conn, row["id"], result, now)


def _forget(conn: sqlite3.Connection, plan_id: int, job_id: int) -> None:
    """A plan that moved nothing, gone from the journal and History."""
    with conn:
        conn.execute("UPDATE jobs SET plan_id = NULL WHERE id = ?", (job_id,))
        conn.execute("DELETE FROM changes WHERE plan_id = ?", (plan_id,))
        conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))


def _free_place(source: Path, now: datetime) -> Path:
    """Where the original is set aside: today's quarantine folder on its drive, under its name,
    or with (2), (3)… when copies set aside earlier today have those names."""
    place = Path(quarantine_place(source, now.date()))
    try:
        taken = {str(path) for path in place.parent.iterdir()}
    except OSError:  # not there yet: the first today
        taken = set[str]()
    return Path(unique_path(place, taken))


def finish(conn: sqlite3.Connection, job_id: int, result: Json, now: datetime) -> None:
    """A result in its place: the library's record describes it, and the job is done."""
    job = conn.execute("SELECT file_id, plan_id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    moved = next(c for c in changes_of(conn, job["plan_id"]) if c.kind is ChangeKind.MOVE)
    if moved.state is not ChangeState.DONE:
        raise ConvertError("The converted copy isn't in place.")
    stat = moved.target.stat()
    _record(conn, job["file_id"], moved.target, stat.st_size, stat.st_mtime_ns, result, now)
    with conn:
        conn.execute(
            """UPDATE jobs SET state = 'done', finished_at = COALESCE(finished_at, ?),
                      output_size = ?, output_probe = ?, problem = NULL, retry_at = NULL
               WHERE id = ?""",
            (now.isoformat(), stat.st_size, json.dumps(result, separators=(",", ":")), job_id),
        )


def _record(
    conn: sqlite3.Connection,
    file_id: int,
    path: Path,
    size: int,
    modified: int,
    report: Json,
    now: datetime,
) -> None:
    """The library's record of a file, as a scan would have read it. Another record at its
    path (one a scan made meanwhile, or a file once there and gone since) gives way: this one
    knows what the file is."""
    media = media_from_ffprobe(report)
    video = media.video
    with conn:
        conn.execute("DELETE FROM files WHERE path = ? AND id != ?", (str(path), file_id))
        conn.execute(
            """UPDATE files SET path = ?, size = ?, modified = ?, gone_at = NULL, probed_at = ?,
                      probe = ?, problem = NULL, duration = ?, width = ?, height = ?, codec = ?
               WHERE id = ?""",
            (
                str(path),
                size,
                modified,
                now.isoformat(),
                json.dumps(report, separators=(",", ":")),
                media.duration,
                video.width if video else None,
                video.height if video else None,
                video.codec if video else None,
                file_id,
            ),
        )


def label_of(row: sqlite3.Row) -> str:
    """ "Trigun · S01E03", or the film's name, or the file's, from a row with the file's `path`,
    `season` and `episode`, and its title's name (`title`)."""
    title = row["title"] or Path(row["path"]).stem
    if row["season"] is not None and row["episode"] is not None:
        return f"{title} · S{row['season']:02d}E{row['episode']:02d}"
    return title


class _Said:
    """What a program writes to its error output, read as it goes so it never blocks: its last
    few hundred lines."""

    def __init__(self, stream: IO[bytes] | None) -> None:
        self._lines: deque[str] = deque(maxlen=_SAID_LINES)
        self._thread = threading.Thread(target=self._read, args=(stream,), daemon=True)
        self._thread.start()

    def _read(self, stream: IO[bytes] | None) -> None:
        if stream is None:
            return
        for line in stream:
            text = line.decode("utf-8", "replace").strip()
            if text:
                self._lines.append(text)

    def last(self) -> str:
        self._thread.join(timeout=5)
        return self._lines[-1] if self._lines else ""

    def lines(self) -> list[str]:
        self._thread.join(timeout=5)
        return list(self._lines)


def _end(*processes: subprocess.Popen[bytes]) -> None:
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait()


def _run(programs: Programs, command: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    process = programs.start(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        _, err = process.communicate(timeout=_LOOK_TIMEOUT)
    except subprocess.TimeoutExpired:
        _end(process)
        raise ConvertError("ffmpeg took too long to look at it, so Kura stopped it.") from None
    return subprocess.CompletedProcess(list(command), process.returncode, b"", err)


def _clock(seconds: float, *, whole: bool = False) -> str:
    """ "04:12": to the nearest second, or the whole seconds reached (`whole`)."""
    count = int(seconds) if whole else round(seconds)
    return f"{count // 60:02d}:{count % 60:02d}"
