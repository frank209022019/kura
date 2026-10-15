"""Checking what this PC can do for Kura, and timing it (kura/hardware.py keeps what's found,
kura/core/hardware.py decides from it).

Each HEVC 10-bit encoder Kura's ffmpeg has is tried on a made-up picture for a moment, the best
card's own maker's first, and the first that starts is the one Kura converts with; so are the
player's H.264 encoders. The AI model runs one small frame on the graphics card (ONNX Runtime with
DirectML), and Anime4K two through libplacebo (Vulkan). Testing the PC, Setup's last step or
About in Settings, times each as well: the encoder making 1080p, the AI model on DVD-sized frames,
and Anime4K making 1080p from 720p, each for at most half a minute (a slow card's speed is what it
managed by then), unless the queue is busy with the card (then it only checks). A way that
couldn't be timed keeps the time it had: no guess is kept as measured.

As the engine starts it checks again when this PC hasn't been checked, its last check found a
part that didn't run, or its cards or their drivers have changed; new cards' times are measured
anew. Converting waits while it checks, and a test asked for meanwhile follows the check.
"""

import logging
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import numpy as np

from kura import db, hardware
from kura.config import DataPaths
from kura.convert import Programs
from kura.core.convert import ENCODERS
from kura.core.filters import filter_path
from kura.core.hardware import ENCODER_OF, Card, Checked, best_card
from kura.core.player import ENCODERS as PLAYER_ENCODERS
from kura.core.player import encoder_check_command
from kura.hardware import Facts

log = logging.getLogger(__name__)

type Step = Literal["encoder", "ai", "anime4k"]

_TIMEOUT = 30  # seconds a try gets, and a timing at most
_VULKAN = ("-init_hw_device", "vulkan=vk", "-filter_hw_device", "vk")
_TRY = 24  # frames a try of an encoder makes
_TIMED = 480  # frames a timing makes, when it has the time: twenty seconds of video
_MODEL_FRAMES = 16  # DVD-sized frames the AI model upscales, at most
_MODEL_SECONDS = 20.0  # or for as long as this, on a slow card
_UNKNOWN = Facts((), None, None, None)
# ffmpeg's lines that say only that something stopped, not why.
_PLUMBING = (
    "Error while opening encoder",
    "Error initializing output stream",
    "Could not open encoder",
    "Error sending frames",
    "Task finished",
    "Terminating thread",
    "Nothing was written",
    "Conversion failed",
)


@dataclass(frozen=True)
class Checking:
    """A check of this PC under way: the part it's on, the parts done, the encoder's frames a
    second once they're timed, and whether it times them."""

    step: Step
    done: tuple[Step, ...]
    fps: float | None
    timing: bool


def check(
    programs: Programs,
    cards: Sequence[Card],
    now: datetime,
    *,
    timing: bool,
    told: Callable[[Checking], None],
) -> tuple[Checked, dict[str, float]]:
    """What this PC can do: the first encoder that starts, the player's, and whether the AI model
    and Anime4K run here; with `timing`, how fast each goes as well ("best", "fast" and
    "reencode", in kura/core/estimate.py's units: only those that could be timed). `told` hears
    each part as it begins."""
    timed: dict[str, float] = {}
    told(Checking("encoder", (), None, timing))
    encoder, problem = _encoder(programs, best_card(cards))
    player = _player(programs)
    if timing and encoder is not None:
        speed = _fps(programs, encoder, "1920x1080", ["-vf", "format=p010le"])
        if speed is not None:
            timed["reencode"] = speed
    told(Checking("ai", ("encoder",), timed.get("reencode"), timing))
    ai = _ai_runs(programs)
    if timing and ai:
        speed = _model_speed(programs)
        if speed is None:
            ai = False  # it ran on a small frame, not on a DVD's: not here
        else:
            timed["best"] = speed
    told(Checking("anime4k", ("encoder", "ai"), timed.get("reencode"), timing))
    anime4k = _anime4k_runs(programs)
    if timing and anime4k and encoder is not None:
        upscale = _anime4k(programs, 1920, 1080, "p010le")
        speed = _fps(programs, encoder, "1280x720", ["-vf", upscale], devices=_VULKAN)
        if speed is not None:
            timed["fast"] = speed  # making 1080p, as kura/core/estimate.py counts it
    log.info(
        "Checked this PC: encoder %s, player %s, AI model %s, Anime4K %s; timed %s",
        encoder,
        player,
        ai,
        anime4k,
        timed,
    )
    return Checked(encoder, problem, ai, anime4k, now.isoformat(), player), timed


class PcCheck:
    """The engine's look at this PC: checked as the engine starts when it needs to be, and tested
    on asking, one at a time, in the background."""

    def __init__(
        self,
        paths: DataPaths,
        programs: Callable[[], Programs | None],
        *,
        now: Callable[[], datetime],
        busy: Callable[[], bool] = lambda: False,
        after: Callable[[], None] = lambda: None,
        looking: Callable[[], Facts | None] = hardware.look,
    ) -> None:
        """`busy` says whether the queue has the card (a test then only checks, as timings
        would be off); `after` hears that a check is over, so converting can go on; `looking`
        asks Windows what the PC has (None when it doesn't answer)."""
        self._paths = paths
        self._programs = programs
        self._now = now
        self._busy = busy
        self._after = after
        self._look = looking
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False  # a look, check or test under way, from asking to its end
        self._testing: Checking | None = None
        self._facts: Facts | None = None
        self._again = False  # a test asked for while something ran: it follows

    def facts(self) -> Facts:
        """What this PC has: as last looked at, or as kept from the last check."""
        with self._lock:
            if self._facts is not None:
                return self._facts
        with closing(db.connect(self._paths.database)) as conn:
            kept, _ = hardware.stored(conn)
        return kept or self._looked()

    def testing(self) -> Checking | None:
        """The check under way, from the moment it's asked for (looking at Windows first), or
        None."""
        with self._lock:
            return self._testing

    def ready(self) -> bool:
        """Whether Kura can check this PC: it has ffmpeg."""
        return self._programs() is not None

    def refresh(self) -> None:
        """In the background: looks at this PC, and checks it when it hasn't been checked, its
        last check found a part that didn't run, or its cards or their drivers have changed
        (timing it too when the cards did). Converting waits till it knows."""
        programs = self._programs()
        if programs is None:
            return  # checked once Kura has ffmpeg: Setup's last step
        with self._lock:
            if not self._running:
                self._launch(lambda: self._refresh(programs), timing=False)

    def test(self) -> bool:
        """Checks and times this PC in the background; asked while a check is under way, right
        after it. False when Kura has no ffmpeg yet."""
        programs = self._programs()
        if programs is None:
            return False
        with self._lock:
            if self._running:
                self._again = True
            else:
                self._launch(lambda: self._run(programs, None, timing=True), timing=True)
        return True

    def wait(self, timeout: float | None = None) -> None:
        """Till the check under way is over (tests)."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _launch(self, work: Callable[[], None], *, timing: bool) -> None:
        """Starts `work` on its own thread. Call with the lock held."""
        self._running = True
        self._testing = Checking("encoder", (), None, timing)
        self._thread = threading.Thread(target=work, name="pc-check", daemon=True)
        self._thread.start()

    def _ended(self) -> bool:
        """Whether the work is over, unless a test was asked for meanwhile: then it's next."""
        with self._lock:
            if self._again:
                self._again = False
                self._testing = Checking("encoder", (), None, True)
                return False
            self._running = False
            self._testing = None
        return True

    def _looked(self) -> Facts:
        """What this PC has, as Windows says now; as last known when Windows doesn't answer."""
        found = self._look()
        with self._lock:
            if found is not None:
                self._facts = found
            known = self._facts
        if known is not None:
            return known
        with closing(db.connect(self._paths.database)) as conn:
            kept, _ = hardware.stored(conn)
        return kept or _UNKNOWN

    def _refresh(self, programs: Programs) -> None:
        try:
            facts = self._looked()
            with closing(db.connect(self._paths.database)) as conn:
                kept, checked = hardware.stored(conn)
                moved = kept is not None and _sizes(kept.cards) != _sizes(facts.cards)
                fresh = (
                    checked is not None
                    and kept is not None
                    and kept.cards == facts.cards
                    and _whole(checked)
                )
                if moved:
                    hardware.forget_speeds(conn)
        except Exception:
            log.exception("Looking at this PC hit a problem")
            facts, fresh, moved = _UNKNOWN, True, False
        if not fresh:
            self._run(programs, facts, timing=moved)
        elif self._ended():
            self._after()
        else:
            self._run(programs, None, timing=True)  # a test asked for while it looked

    def _run(self, programs: Programs, facts: Facts | None, *, timing: bool) -> None:
        while True:
            try:
                facts = facts or self._looked()
                timed = timing and not self._busy()
                checked, found = check(
                    programs, facts.cards, self._now(), timing=timed, told=self._told
                )
                with closing(db.connect(self._paths.database)) as conn:
                    hardware.keep(conn, facts, checked)
                    if timed:
                        hardware.keep_speeds(conn, found, self._now())
            except Exception:
                log.exception("Checking this PC hit a problem")
            if self._ended():
                self._after()
                return
            facts, timing = None, True  # the test asked for meanwhile, looking afresh

    def _told(self, checking: Checking) -> None:
        with self._lock:
            self._testing = checking


def _whole(checked: Checked) -> bool:
    """Whether a check found every part running: one that didn't is checked again as the engine
    starts (it may have been the moment: a card busy, a driver mid-update)."""
    return bool(checked.encoder and checked.ai and checked.anime4k and checked.player)


def _sizes(cards: Sequence[Card]) -> list[tuple[str, int | None]]:
    """The cards without their drivers: a new driver keeps the card's times."""
    return [(card.name, card.memory) for card in cards]


def _encoder(programs: Programs, card: Card | None) -> tuple[str | None, str | None]:
    """The first encoder that makes HEVC 10-bit here, the card's own maker's tried first, and
    what that one said when it didn't start (another may have)."""
    own = ENCODER_OF.get(card.maker) if card is not None else None
    order = [*([own] if own else []), *(name for name in ENCODERS if name != own)]
    problem: str | None = None
    for name in order:
        command = [
            *programs.ffmpeg,
            *("-nostdin", "-v", "error", *_picture("1280x720"), "-frames:v", str(_TRY)),
            *("-vf", "format=p010le", *ENCODERS[name], "-f", "null", "-"),
        ]
        said = _try(programs, command)
        if said is None:
            return name, problem
        if name == own:
            problem = said
    return None, problem


def _player(programs: Programs) -> str | None:
    """The first of the player's H.264 encoders that works here (kura/core/player.py's order:
    Windows' own first), or None."""
    for name, encoder in PLAYER_ENCODERS.items():
        if _try(programs, encoder_check_command(programs.ffmpeg, encoder)) is None:
            return name
    return None


def _ai_runs(programs: Programs) -> bool:
    """Whether the AI model runs on this PC's graphics card: one small frame."""
    try:
        upscale = programs.model(64, 48)
        upscale(np.zeros((1, 3, 48, 64), np.float32))
    except Exception as error:  # UpscaleError, or ONNX Runtime's own, all plain Exceptions
        log.info("The AI model doesn't run here: %s", error)
        return False
    return True


def _anime4k_runs(programs: Programs) -> bool:
    """Whether Anime4K runs through libplacebo here: two small frames."""
    command = [
        *programs.ffmpeg,
        *("-nostdin", "-v", "error", *_VULKAN, *_picture("320x240"), "-frames:v", "2"),
        *("-vf", _anime4k(programs, 640, 480, "yuv420p"), "-f", "null", "-"),
    ]
    said = _try(programs, command)
    if said is not None:
        log.info("Anime4K doesn't run here: %s", said)
    return said is None


def _anime4k(programs: Programs, width: int, height: int, depth: str) -> str:
    """Anime4K's filters, as converting runs them (kura/core/convert.py)."""
    shader = filter_path(programs.shader)
    return (
        f"hwupload,libplacebo=w={width}:h={height}:format={depth}:custom_shader_path={shader},"
        f"hwdownload,format={depth}"
    )


def _picture(size: str) -> tuple[str, ...]:
    """A made-up moving picture of `size` ("1280x720"), so no video is needed."""
    return ("-f", "lavfi", "-i", f"testsrc2=size={size}:rate=24")


def _try(programs: Programs, command: Sequence[str]) -> str | None:
    """Runs a short ffmpeg: None when it worked, else what it said that tells why."""
    process = programs.start(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        _, err = process.communicate(timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        return "It took too long to start."
    if process.returncode == 0:
        return None
    return _why(err.decode("utf-8", "replace")) or f"It stopped with code {process.returncode}."


def _why(said: str) -> str | None:
    """ffmpeg's line that says why, without its "[hevc_nvenc @ 0x…]" in front."""
    for line in said.splitlines():
        text = line.split("] ", 1)[1] if line.startswith("[") and "] " in line else line
        text = text.strip()
        if text and not any(text.startswith(each) for each in _PLUMBING):
            return text.rstrip(".") + "."
    return None


def _fps(
    programs: Programs,
    encoder: str,
    size: str,
    filters: Sequence[str],
    *,
    devices: Sequence[str] = (),
) -> float | None:
    """Frames a second this PC makes through `filters` and the encoder, from a made-up picture
    of `size`: from ffmpeg's own progress, so starting it doesn't count, for at most _TIMEOUT
    seconds (a slow card's is what it managed by then). None when it couldn't be timed."""
    command = [
        *programs.ffmpeg,
        *("-nostdin", "-v", "error", "-stats_period", "0.1", *devices, *_picture(size)),
        *("-frames:v", str(_TIMED), *filters, *ENCODERS[encoder]),
        *("-progress", "pipe:1", "-nostats", "-f", "null", "-"),
    ]
    process = programs.start(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    seen: list[tuple[float, int]] = []

    def read() -> None:
        assert process.stdout is not None  # noqa: S101 - asked for above
        for raw in process.stdout:
            line = raw.decode("ascii", "replace").strip()
            if line.startswith("frame="):
                try:
                    seen.append((time.monotonic(), int(line[6:])))
                except ValueError:
                    continue

    reader = threading.Thread(target=read, name="pc-check-progress", daemon=True)
    reader.start()
    try:
        process.wait(timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()  # a slow card: its speed so far
        process.wait()
    reader.join(5)
    return pace(list(seen))


def pace(seen: Sequence[tuple[float, int]]) -> float | None:
    """Frames a second from ffmpeg's progress (when, frames done), from the first frames made
    on: so starting ffmpeg and its encoder doesn't count. None without two reports apart."""
    started = [(moment, frames) for moment, frames in seen if frames > 0]
    if len(started) < 2:
        return None
    (began, first), (ended, last) = started[0], started[-1]
    if ended <= began or last <= first:
        return None
    return (last - first) / (ended - began)


def _model_speed(programs: Programs) -> float | None:
    """The AI model's megapixels a second here, from DVD-sized frames (after one to warm up),
    or None when it can't upscale them."""
    width, height = 720, 480
    try:
        upscale = programs.model(width, height)
        frame = np.random.default_rng(0).random((1, 3, height, width), np.float32)
        upscale(frame)
        began, done = time.monotonic(), 0
        while done < _MODEL_FRAMES and time.monotonic() - began < _MODEL_SECONDS:
            upscale(frame)
            done += 1
    except Exception as error:
        log.info("The AI model couldn't upscale a DVD's frames: %s", error)
        return None
    return done * width * height / 1e6 / max(time.monotonic() - began, 1e-3)
