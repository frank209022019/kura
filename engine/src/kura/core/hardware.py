"""What a PC can do for Kura, from what it has and what testing it found (kura/hardware.py looks
and tests): its graphics cards, the HEVC 10-bit encoder that started on it, whether the AI model
ran on a graphics card and Anime4K through libplacebo, and how long each takes there. Pure.

Kura was first measured on the owner's GTX 1660 Super; on any other PC each part says whether it
works there, what does it, and how long an episode takes, so nothing is promised that the PC
can't do and no time is someone else's.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Literal

from kura.core.estimate import HEARING, Speeds, estimate
from kura.core.media import MediaInfo, Video
from kura.core.standard import CINEMA_1080, Decision, Method, Standard

type Maker = Literal["nvidia", "amd", "intel", "other"]
type Part = Literal["convert", "ai", "fast", "subtitles", "player"]
type State = Literal["ready", "slow", "limited", "no"]
type Place = Literal["card", "processor"]

GIB = 1024**3
BEST_MEMORY = 4 * GIB  # a card's own memory Whisper medium (Best) wants
FAST_MEMORY = 2 * GIB  # and Whisper small (Fast); with less, Fast runs on the processor
SLOW = 3 * 3600  # seconds an episode may take before a way is slow here: the lighter one goes first
EPISODE = 24 * 60.0  # seconds: the episode every time here is for

# Each encoder Kura converts with (kura/core/convert.py's ENCODERS), as people know it.
ENCODER_NAMES = {
    "nvenc": "NVIDIA's encoder (NVENC)",
    "amf": "AMD's encoder (AMF)",
    "qsv": "Intel Quick Sync",
}
ENCODER_OF: dict[Maker, str] = {"nvidia": "nvenc", "amd": "amf", "intel": "qsv"}
# The player's H.264 encoders (kura/core/player.py's ENCODERS), as people know them.
PLAYER_NAMES = {
    "h264_mf": "Windows' own video encoder",
    "h264_nvenc": "NVIDIA's encoder (NVENC)",
    "h264_amf": "AMD's encoder (AMF)",
    "h264_qsv": "Intel Quick Sync",
}
BEST_WANTS_MEMORY = "Best wants a graphics card with 4 GB of memory of its own."
BEST_WANTS_DIRECTX = "Best wants a graphics card that runs DirectX 12."
NO_ENCODER = (
    "This PC can't convert to your standard: its graphics card has no encoder for HEVC 10-bit."
)
# Windows' listing tells a card's memory only up to this (4 GB less a megabyte): one at it has
# 4 GB or more.
_LISTING_CAP = 0xFFF00000
DRIVERS: dict[Maker, str] = {  # where each maker's drivers are, for a driver too old
    "nvidia": "https://www.nvidia.com/Download/index.aspx",
    "amd": "https://www.amd.com/en/support/download/drivers.html",
    "intel": "https://www.intel.com/content/www/us/en/download-center/home.html",
}
_VENDORS: dict[str, Maker] = {"10de": "nvidia", "1002": "amd", "1022": "amd", "8086": "intel"}


@dataclass(frozen=True)
class Card:
    """A graphics card, or the processor's graphics."""

    name: str  # "NVIDIA GeForce GTX 1660 SUPER"
    maker: Maker
    memory: int | None  # bytes of its own; None when Windows doesn't say
    integrated: bool  # the processor's graphics, sharing the PC's memory
    driver: str | None  # its driver's version, as its maker writes it: "617.42"


@dataclass(frozen=True)
class Checked:
    """What checking this PC found."""

    encoder: str | None  # the first of ENCODERS that started ("nvenc"), or None
    # What the card's own maker's encoder said when it didn't start (another may have).
    encoder_problem: str | None
    ai: bool  # the AI model ran on a graphics card (DirectML)
    anime4k: bool  # Anime4K ran through libplacebo (Vulkan)
    at: str  # when, ISO
    player: str | None = "h264_mf"  # the first of the player's encoders that worked, or None


@dataclass(frozen=True)
class Ability:
    """One part of Kura on this PC: whether it works here, what does it, and how long an episode
    takes."""

    part: Part
    state: State  # ready; slow (over SLOW an episode); limited (a lighter way only); or no
    how: str  # what does it here: "HEVC 10-bit on NVIDIA's encoder (NVENC)"
    note: str | None  # what's slow or limited, or why it can't
    seconds: tuple[float, ...]  # a 24-minute episode's time; subtitles: Best's then Fast's


def maker_of(name: str, vendor: str | None = None) -> Maker:
    """Who made a card, by its PCI vendor id ("10de") or else its name."""
    if vendor and vendor.casefold() in _VENDORS:
        return _VENDORS[vendor.casefold()]
    lowered = name.casefold()
    if any(word in lowered for word in ("nvidia", "geforce", "quadro")):
        return "nvidia"
    if any(word in lowered for word in ("amd", "radeon")):
        return "amd"
    if "intel" in lowered:
        return "intel"
    return "other"


def is_integrated(maker: Maker, memory: int | None) -> bool:
    """Whether a card is the processor's graphics: Intel's and AMD's have little memory of their
    own (dedicated ones have 2 GB or more)."""
    return maker in ("intel", "amd") and (memory is None or memory < FAST_MEMORY)


def driver_name(version: str | None, maker: Maker) -> str | None:
    """A driver's version as its maker writes it: NVIDIA's "617.42" from Windows'
    "32.0.16.1742"; others' as Windows has it."""
    if version is None:
        return None
    if maker == "nvidia":
        digits = version.replace(".", "")[-5:]
        if len(digits) == 5 and digits.isdigit():
            return f"{int(digits[:3])}.{digits[3:]}"
    return version


def driver_problem(problem: str | None) -> bool:
    """Whether what a card's own encoder said points at its driver: too old for the encoder
    Kura's ffmpeg asks for ("Driver does not support the required nvenc API version"), or
    without the runtime it installs ("DLL amfrt64.dll failed to open"). Otherwise the card
    itself has no encoder for HEVC 10-bit."""
    said = (problem or "").casefold()
    return "driver" in said or ".dll" in said


def best_wants(checked: Checked | None) -> str:
    """Why Best (Whisper medium) can't run on this PC: no DirectX 12 for it, or too little
    memory on the card."""
    return BEST_WANTS_DIRECTX if checked is not None and not checked.ai else BEST_WANTS_MEMORY


def why_not_converting(cards: Sequence[Card], checked: Checked) -> str:
    """Why this PC can't convert, as the queue says it: the card's own encoder didn't start for
    want of a newer driver, or it has none for HEVC 10-bit."""
    card = best_card(cards)
    own = ENCODER_OF.get(card.maker) if card else None
    if own is not None and driver_problem(checked.encoder_problem):
        return (
            f"{ENCODER_NAMES[own]} didn't start: the graphics card's driver may be too old for "
            "it. Update it, then test this PC again under About in Settings."
        )
    return NO_ENCODER


def best_card(cards: Sequence[Card]) -> Card | None:
    """The card Kura works on: the dedicated one with the most memory, else the processor's
    graphics."""
    dedicated = [card for card in cards if not card.integrated]
    if dedicated:
        return max(dedicated, key=lambda card: card.memory or 0)
    return cards[0] if cards else None


def processor_name(name: str | None) -> str | None:
    """A processor as people say it: "Intel Core i5-9600K" for Windows' "Intel(R) Core(TM)
    i5-9600K CPU @ 3.70GHz"."""
    if not name:
        return None
    cleaned = name.replace("(R)", "").replace("(TM)", "").replace("(tm)", "")
    cleaned = cleaned.split(" CPU @")[0].split(" @ ")[0]
    for word in (" Processor", " CPU", " with Radeon Graphics"):
        cleaned = cleaned.replace(word, "")
    return " ".join(cleaned.split()) or None


def hearing_places(cards: Sequence[Card], checked: Checked | None) -> dict[str, Place | None]:
    """Where each quality of English subtitles runs: on the card when it has the memory for it,
    Fast else on the processor; Best not at all without a card with 4 GB of its own, or where
    DirectML doesn't run. Before this PC is tested, or when Windows didn't say what its card has,
    both on the card, as on the PC Kura was measured on (a card that runs out of memory says so,
    and offers Fast)."""
    if checked is None:
        return {"best": "card", "fast": "card"}
    if not checked.ai:
        return {"best": None, "fast": "processor"}
    card = best_card(cards)
    if card is None or (not card.integrated and card.memory is None):
        return {"best": "card", "fast": "card"}
    room = 0 if card.integrated or card.memory is None else card.memory
    return {
        "best": "card" if room >= BEST_MEMORY else None,
        "fast": "card" if room >= FAST_MEMORY else "processor",
    }


def capable(standard: Standard, checked: Checked | None) -> Standard:
    """The owner's standard as this PC can make it: no AI model where it doesn't run (SD gets the
    fast upscale instead), no Anime4K where libplacebo doesn't."""
    if checked is None:
        return standard
    return replace(standard, ai_here=checked.ai, anime4k_here=checked.anime4k)


def ways(checked: Checked | None, speeds: Speeds) -> dict[Method, State]:
    """How each way of converting stands on this PC: ready, slow (over SLOW an episode), or no."""
    if checked is None:
        return {Method.BEST: "ready", Method.FAST: "ready", Method.REENCODE: "ready"}
    if checked.encoder is None:
        return {Method.BEST: "no", Method.FAST: "no", Method.REENCODE: "no"}
    return {
        Method.BEST: _pace(checked.ai, episode_seconds(Method.BEST, speeds)),
        Method.FAST: _pace(checked.anime4k, episode_seconds(Method.FAST, speeds)),
        Method.REENCODE: "ready",
    }


def episode_seconds(method: Method, speeds: Speeds, standard: Standard = CINEMA_1080) -> float:
    """How long a 24-minute episode takes this way: SD (a DVD's 720 by 480) for the AI model,
    720p for the fast upscale, 1080p for a re-encode."""
    width, height = {Method.BEST: (720, 480), Method.FAST: (1280, 720)}.get(method, (1920, 1080))
    picture = Video("h264", width, height, Fraction(16, 9), Fraction(24000, 1001), 8, False)
    media = MediaInfo("mkv", EPISODE, 0, picture, (), (), 0)
    return estimate(media, Decision(method, 1920, 1080), standard, speeds).gpu_seconds


def abilities(
    cards: Sequence[Card],
    checked: Checked,
    speeds: Speeds,
    hearing: dict[str, float] | None = None,
) -> tuple[Ability, ...]:
    """Each part of Kura on this PC, in the order Setup lists them. `hearing` holds the measured
    seconds of work for each second of sound: "best", "fast", and "fast_processor"."""
    card = best_card(cards)
    graphics = (
        "the processor's graphics" if card is None or card.integrated else "the graphics card"
    )
    pace = ways(checked, speeds)
    own = ENCODER_OF.get(card.maker) if card else None
    stopped = None
    if own is not None and driver_problem(checked.encoder_problem):
        stopped = f"{ENCODER_NAMES[own]} didn't start: {checked.encoder_problem}"
    if checked.encoder is None:
        why = stopped or "Its graphics card has no encoder for HEVC 10-bit."
        convert = Ability("convert", "no", "Not on this PC", why, ())
    else:
        how = f"HEVC 10-bit on {ENCODER_NAMES[checked.encoder]}"
        note = stopped if own != checked.encoder else None
        convert = Ability(
            "convert", "ready", how, note, (episode_seconds(Method.REENCODE, speeds),)
        )
    return (
        convert,
        _way("ai", pace[Method.BEST], checked, speeds, graphics),
        _way("fast", pace[Method.FAST], checked, speeds, graphics),
        _subtitles(cards, checked, hearing or {}),
        _player(checked),
    )


def _player(checked: Checked) -> Ability:
    if checked.player is None:
        why = (
            "No video encoder for it started. A Windows N edition gets Windows' own from "
            "Microsoft's Media Feature Pack."
        )
        return Ability("player", "no", "Not on this PC", why, ())
    return Ability("player", "ready", PLAYER_NAMES.get(checked.player, checked.player), None, ())


def _pace(runs: bool, seconds: float) -> State:
    if not runs:
        return "no"
    return "slow" if seconds > SLOW else "ready"


def _way(part: Part, state: State, checked: Checked, speeds: Speeds, graphics: str) -> Ability:
    model = "Real-ESRGAN" if part == "ai" else "Anime4K"
    if checked.encoder is None:
        return Ability(part, "no", "Not on this PC", "Not without an encoder for converting.", ())
    if state == "no":
        if part == "ai":
            instead = "get the fast upscale" if checked.anime4k else "are re-encoded"
            why = (
                "Its graphics card can't run the AI model: it needs DirectX 12. SD episodes "
                f"{instead} instead."
            )
        else:
            why = (
                "Its graphics card can't run Anime4K: it needs Vulkan. 720p episodes are "
                "re-encoded instead."
            )
        return Ability(part, "no", "Not on this PC", why, ())
    seconds = (episode_seconds(Method.BEST if part == "ai" else Method.FAST, speeds),)
    if state == "slow":
        note = (
            "SD episodes get the fast upscale unless you choose the AI model on Convert."
            if part == "ai"
            else "Re-encode only, on Convert, is much quicker."
        )
        return Ability(part, "slow", f"{model} on {graphics}, slowly", note, seconds)
    return Ability(part, "ready", f"{model} on {graphics}", None, seconds)


def _subtitles(cards: Sequence[Card], checked: Checked, hearing: dict[str, float]) -> Ability:
    places = hearing_places(cards, checked)
    wanting = best_wants(checked)
    fast = EPISODE * hearing.get("fast", HEARING["fast"])
    if places["best"] == "card":
        best = EPISODE * hearing.get("best", HEARING["best"])
        return Ability(
            "subtitles", "ready", "Best and Fast on the graphics card", None, (best, fast)
        )
    if places["fast"] == "card":
        return Ability("subtitles", "limited", "Fast on the graphics card", wanting, (fast,))
    slow = EPISODE * hearing.get("fast_processor", HEARING["fast_processor"])
    return Ability("subtitles", "limited", "Fast on the processor", wanting, (slow,))


def cards_from(listed: Sequence[dict[str, object]], memories: dict[str, int]) -> tuple[Card, ...]:
    """The cards Windows lists (Win32_VideoController: its Name, PNPDeviceID, DriverVersion and
    AdapterRAM), each with its own memory as the registry has it (`memories`, by name: the
    listing stops at 4 GB). Only cards on the PC's bus: not Windows' basic or remote display,
    nor a virtual one."""
    found: list[Card] = []
    for entry in listed:
        name = str(entry.get("Name") or "").strip()
        device = str(entry.get("PNPDeviceID") or "")
        if not name or not device.upper().startswith("PCI\\"):
            continue
        vendor = device.upper().split("VEN_")[1][:4] if "VEN_" in device.upper() else None
        maker = maker_of(name, vendor)
        listed_ram = entry.get("AdapterRAM")
        reported = listed_ram if isinstance(listed_ram, int) and listed_ram > 0 else None
        if reported is not None and reported >= _LISTING_CAP:
            reported = max(reported, 4 * GIB)  # at least: the listing can't say more
        memory = memories.get(name) or reported
        driver = entry.get("DriverVersion")
        found.append(
            Card(
                name,
                maker,
                memory,
                is_integrated(maker, memory),
                driver_name(str(driver) if driver else None, maker),
            )
        )
    return tuple(found)
