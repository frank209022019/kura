"""Converting one file, start to finish.

The picture is looked at for interlacing (idet) when ffprobe couldn't tell, then made by the
method its recipe names (kura/core/convert.py): the AI model between two ffmpegs (kura/upscale.py)
or one ffmpeg command. The result is checked (length, streams, Kura's tag, a test play at three
points) and only then takes the original's place, the original going to quarantine on its own
drive. Both moves are journaled (kura/changes.py), so a crash leaves nothing half done, and
`restore` puts the original back.

The work happens beside the original, in a file whose name ends in .kura-converting: no scan or
watcher counts it as a video, and it moves into place on the same drive at once. A crash while
it moves leaves the job "replacing": `settle` finishes it, or puts the original back.
"""

import json
import shutil
import sqlite3
import subprocess
import threading
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, ExitStack, nullcontext
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
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
from kura.core.media import MediaInfo, Video, media_from_ffprobe
from kura.core.naming import unique_path
from kura.core.plan import Change, ChangeKind, Plan, quarantine_place
from kura.core.standard import Decision, Method, Standard, decide
from kura.probe import ProbeError, ProbeToolError
from kura.upscale import UpscaleError, Upscaler, pipe, upscaled_size

WORKING = ".kura-converting"  # the end of a result's name while it's being made
SHADER = Path(__file__).parent / "assets" / "anime4k-mode-a-hq.glsl"  # the fast upscale
CONVERTED = (Method.REMUX, Method.REENCODE, Method.FAST, Method.BEST)  # what a job can be
_UPSCALES = (Method.BEST, Method.FAST, Method.REENCODE)  # heaviest first
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PLAY_SECONDS = 5  # how much of the result a test play decodes, at each of three points
_LOOK_TIMEOUT = 300  # seconds for idet or a test play
_SPACE_MARGIN = 1.25  # free space wanted, over the estimated size of the result

type Stage = Literal["looking", "converting", "checking", "replacing"]


@dataclass(frozen=True)
class Progress:
    stage: Stage
    frames: int  # done so far
    total: int  # in all, as far as Kura can tell


class ConvertError(Exception):
    """The file couldn't be converted, and the original is as it was. The message says why."""


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
    """A program without a console window (the engine has none)."""
    return subprocess.Popen(  # noqa: S603 - Kura's own ffmpeg, never a shell
        list(command), stdin=stdin, stdout=stdout, stderr=stderr, creationflags=_NO_WINDOW
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
    hold: Callable[[], AbstractContextManager[None]] = nullcontext,
) -> None:
    """Converts a job's file and puts the result in its place, `hold` holding scans off while
    it moves. Raises ConvertError when it can't (the original stays as it was), or Stopped when
    `stop` asked."""
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
    made = recipe(
        source, media, decision, tag=f"{decision.method} to {standard.height}p · Kura {__version__}"
    )
    if media.video.interlaced is None:
        made = replace(made, deinterlace=_looks_interlaced(programs, source, media))
    _enough_space(source, media, decision, standard)
    work = source.with_name(source.stem + WORKING)
    work.unlink(missing_ok=True)
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
        work.unlink(missing_ok=True)
        raise
    report(Progress("replacing", total, total))
    with ExitStack() as held:
        try:
            held.enter_context(hold())
        except BaseException:
            work.unlink(missing_ok=True)  # never put in place: nothing to keep
            raise
        _replace(conn, row, source, work, made, result, now())


def lighter(decided: Method, chosen: Method) -> Method:
    """The method a file gets when the owner chose one for it: never more than suits it (the AI
    model only for SD), and lighter when they asked (Anime4K, or only a re-encode, for speed)."""
    if decided in _UPSCALES and chosen in _UPSCALES:
        return max(decided, chosen, key=_UPSCALES.index)
    return decided


def restore(conn: sqlite3.Connection, job_id: int, *, now: datetime) -> None:
    """Puts a converted file's original back in its place, and the converted copy away."""
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None or job["plan_id"] is None or job["state"] != "done":
        raise ConvertError("Kura has no converted file to put back for that.")
    changes = changes_of(conn, job["plan_id"])
    original = next(c.source for c in changes if c.kind is ChangeKind.QUARANTINE)
    copy = next(c.source for c in changes if c.kind is ChangeKind.MOVE)  # where it was made
    outcome = undo_plan(conn, job["plan_id"], now=now)
    if outcome.problems:
        raise ConvertError(f"Kura couldn't put the original back. {outcome.problems[0].problem}")
    copy.unlink(missing_ok=True)
    probe = json.loads(job["source_probe"])
    _record(conn, job["file_id"], original, job["source_size"], job["source_modified"], probe, now)
    with conn:
        conn.execute(
            "UPDATE jobs SET state = 'restored', finished_at = ? WHERE id = ?",
            (now.isoformat(), job_id),
        )


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
                "UPDATE jobs SET state = 'done', finished_at = ? WHERE id = ?",
                (now.isoformat(), job_id),
            )
        return
    if plan_id is not None:
        undo_plan(conn, plan_id, now=now)
        if moved is not None:
            moved.source.unlink(missing_ok=True)  # the result, never in place
    with conn:
        conn.execute(
            "UPDATE jobs SET state = 'queued', plan_id = NULL, started_at = NULL WHERE id = ?",
            (job_id,),
        )


def _moved(conn: sqlite3.Connection, plan_id: int | None) -> SavedChange | None:
    """A conversion plan's second change: the result into its original's place."""
    if plan_id is None:
        return None
    return next((c for c in changes_of(conn, plan_id) if c.kind is ChangeKind.MOVE), None)


def _job(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row:
    row = conn.execute(
        """SELECT j.id, j.file_id, j.method, f.path, f.size, f.modified, f.probe, f.season,
                  f.episode, t.name AS title
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


def _enough_space(source: Path, media: MediaInfo, decision: Decision, standard: Standard) -> None:
    needed = estimate(media, decision, standard).output_bytes * _SPACE_MARGIN
    free = shutil.disk_usage(source.parent).free
    if free < needed:
        drive = source.anchor or str(source.parent)
        raise ConvertError(
            f"There isn't room on {drive}: {free / 1e9:.1f} GB free, and the result needs about"
            f" {needed / 1e9:.1f} GB."
        )


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
    try:
        pipe(
            cast("IO[bytes]", decoder.stdout),
            cast("IO[bytes]", encoder.stdin),
            upscale,
            video.width,
            video.height,
            done=lambda count: report(Progress("converting", count, total)),
            stop=stop,
        )
    except UpscaleError as error:
        _end(decoder, encoder)
        raise ConvertError(f"{error} {encoding.last() or decoding.last()}".strip()) from error
    if stop():
        _end(decoder, encoder)
        raise Stopped
    if decoder.wait() != 0:
        _end(encoder)
        raise ConvertError(f"ffmpeg couldn't read it: {decoding.last() or 'it stopped'}.")
    if encoder.wait() != 0:
        raise ConvertError(f"ffmpeg couldn't encode it: {encoding.last() or 'it stopped'}.")


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
    for line in cast("IO[bytes]", process.stdout):
        if stop():
            _end(process)
            raise Stopped
        if line.startswith(b"frame="):
            frames = int(line.split(b"=", 1)[1].strip() or 0)
            report(Progress("converting", frames, total))
    if process.wait() != 0:
        raise ConvertError(f"ffmpeg couldn't convert it: {said.last() or 'it stopped'}.")
    if stop():
        raise Stopped


def _play(programs: Programs, work: Path, duration: float) -> list[str]:
    """A test play of the result at three points: what went wrong, if anything."""
    problems: list[str] = []
    for share in (0.1, 0.5, 0.9):
        at = max(0.0, duration * share - _PLAY_SECONDS / 2)
        command = [
            *programs.ffmpeg,
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


def _replace(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    source: Path,
    work: Path,
    made: Recipe,
    result: Json,
    now: datetime,
) -> None:
    """The original to quarantine and the result into its place, journaled; then the library's
    record of the file describes the result, keeping what it was identified as."""
    label = label_of(row)
    place = Path(quarantine_place(source, now.date()))
    if place.exists():
        place = Path(unique_path(place, {str(place)}))
    plan = Plan(
        (
            Change(
                ChangeKind.QUARANTINE,
                source,
                place,
                f"{label} · original",
                "Set aside: its converted copy takes its place",
            ),
            Change(ChangeKind.MOVE, work, made.output, label, f"Converted ({made.method})"),
        )
    )
    plan_id = save_plan(conn, plan, f"Converted {label}", now=now, kind="convert")
    original = source.stat()
    with conn:
        conn.execute(
            """UPDATE jobs SET state = 'replacing', plan_id = ?, source_size = ?,
                      source_modified = ?, source_probe = ?
               WHERE id = ?""",
            (plan_id, original.st_size, original.st_mtime_ns, row["probe"], row["id"]),
        )
    outcome = apply_plan(conn, plan_id, now=now)
    if outcome.problems:
        undo_plan(conn, plan_id, now=now)
        work.unlink(missing_ok=True)
        raise ConvertError(
            f"Kura couldn't put it in place, so the original is back: {outcome.problems[0].problem}"
        )
    finish(conn, row["id"], result, now)


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
            """UPDATE jobs SET state = 'done', finished_at = ?, output_size = ?,
                      output_probe = ?, problem = NULL
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
    """The library's record of a file, as a scan would have read it."""
    media = media_from_ffprobe(report)
    video = media.video
    with conn:
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
    """What a program writes to its error output, read as it goes so it never blocks."""

    def __init__(self, stream: IO[bytes] | None) -> None:
        self._lines: list[str] = []
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


def _clock(seconds: float) -> str:
    whole = round(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"
