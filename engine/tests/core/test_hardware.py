"""What a PC can do for Kura, from its cards and what testing it found."""

from dataclasses import replace
from fractions import Fraction

import pytest

from kura.core.estimate import Speeds
from kura.core.hardware import (
    BEST_MEMORY,
    GIB,
    Card,
    Checked,
    abilities,
    best_card,
    best_wants,
    capable,
    cards_from,
    driver_name,
    driver_problem,
    episode_seconds,
    hearing_places,
    is_integrated,
    maker_of,
    processor_name,
    ways,
    why_not_converting,
)
from kura.core.media import MediaInfo, Video
from kura.core.standard import CINEMA_1080, Method, decide

GTX = Card("NVIDIA GeForce GTX 1660 SUPER", "nvidia", 6 * GIB, False, "617.42")
UHD = Card("Intel(R) UHD Graphics 620", "intel", 128 * 1024**2, True, "31.0.101.2111")
SMALL = Card("NVIDIA GeForce GTX 1050", "nvidia", 2 * GIB, False, "551.86")
CHECKED = Checked("nvenc", None, ai=True, anime4k=True, at="2026-10-15T15:00:00+02:00")


def test_a_cards_maker_is_known_by_its_vendor_or_its_name():
    assert maker_of("Some Card", "10de") == "nvidia"
    assert maker_of("AMD Radeon RX 6700 XT") == "amd"
    assert maker_of("Intel(R) UHD Graphics 620") == "intel"
    assert maker_of("Microsoft Basic Display Adapter") == "other"


def test_the_processors_graphics_have_little_memory_of_their_own():
    assert is_integrated("intel", 128 * 1024**2)
    assert is_integrated("amd", 512 * 1024**2)
    assert not is_integrated("amd", 12 * GIB)
    assert not is_integrated("intel", 8 * GIB)  # an Arc card
    assert not is_integrated("nvidia", None)


def test_drivers_and_processors_are_named_as_people_know_them():
    assert driver_name("32.0.16.1742", "nvidia") == "617.42"
    assert driver_name("31.0.101.2111", "intel") == "31.0.101.2111"
    assert processor_name("Intel(R) Core(TM) i5-9600K CPU @ 3.70GHz") == "Intel Core i5-9600K"
    assert processor_name("AMD Ryzen 7 5800X 8-Core Processor") == "AMD Ryzen 7 5800X 8-Core"


def test_kura_works_on_the_dedicated_card_with_the_most_memory():
    assert best_card([UHD, SMALL, GTX]) == GTX
    assert best_card([UHD]) == UHD
    assert best_card([]) is None


def test_subtitles_go_where_the_card_has_the_memory_for_them():
    assert hearing_places([GTX], CHECKED) == {"best": "card", "fast": "card"}
    assert hearing_places([SMALL], CHECKED) == {"best": None, "fast": "card"}
    assert hearing_places([UHD], CHECKED) == {"best": None, "fast": "processor"}
    no_directml = Checked("nvenc", None, ai=False, anime4k=True, at="")
    assert hearing_places([GTX], no_directml) == {"best": None, "fast": "processor"}
    assert hearing_places([], None) == {"best": "card", "fast": "card"}  # not tested yet
    unsaid = Card("NVIDIA GeForce RTX 4060", "nvidia", None, False, None)
    assert hearing_places([unsaid], CHECKED) == {"best": "card", "fast": "card"}  # as it was
    assert hearing_places([], CHECKED) == {"best": "card", "fast": "card"}


def sd() -> MediaInfo:
    picture = Video("mpeg2video", 720, 480, Fraction(4, 3), Fraction(24000, 1001), 8, False)
    return MediaInfo("mkv", 1440.0, 0, picture, (), (), 0)


def hd() -> MediaInfo:
    picture = Video("h264", 1280, 720, Fraction(16, 9), Fraction(24000, 1001), 8, False)
    return MediaInfo("mkv", 1440.0, 0, picture, (), (), 0)


def test_what_this_pc_cant_run_gets_the_next_way_down():
    no_ai = capable(CINEMA_1080, Checked("qsv", None, ai=False, anime4k=True, at=""))
    neither = capable(CINEMA_1080, Checked("qsv", None, ai=False, anime4k=False, at=""))

    assert decide(sd(), CINEMA_1080).method is Method.BEST
    assert decide(sd(), no_ai).method is Method.FAST
    assert decide(sd(), neither).method is Method.REENCODE
    assert decide(hd(), neither).method is Method.REENCODE
    assert capable(CINEMA_1080, None) == CINEMA_1080  # not tested yet: as it was


def test_a_way_over_three_hours_an_episode_is_slow_here():
    owners = Speeds()
    laptops = Speeds(best=0.35, fast=12.0, reencode=40.0)

    assert ways(CHECKED, owners) == {
        Method.BEST: "ready",
        Method.FAST: "ready",
        Method.REENCODE: "ready",
    }
    assert ways(CHECKED, laptops)[Method.BEST] == "slow"
    assert episode_seconds(Method.BEST, laptops) > 3 * 3600
    no_encoder = Checked(None, None, ai=True, anime4k=True, at="")
    assert set(ways(no_encoder, owners).values()) == {"no"}
    assert set(ways(None, laptops).values()) == {"ready"}  # not tested yet


def test_the_owners_pc_does_everything():
    found = abilities([GTX], CHECKED, Speeds())

    assert [(each.part, each.state) for each in found] == [
        ("convert", "ready"),
        ("ai", "ready"),
        ("fast", "ready"),
        ("subtitles", "ready"),
        ("player", "ready"),
    ]
    assert found[0].how == "HEVC 10-bit on NVIDIA's encoder (NVENC)"
    assert found[1].seconds[0] == pytest.approx(3600, rel=0.1)  # about an hour an episode
    assert len(found[3].seconds) == 2  # Best's and Fast's


def test_a_laptop_says_whats_slow_and_what_runs_on_the_processor():
    laptop = Checked("qsv", None, ai=True, anime4k=True, at="")

    found = abilities([UHD], laptop, Speeds(best=0.35, fast=12.0, reencode=40.0))

    ai, subtitles = found[1], found[3]
    assert (ai.state, ai.how) == ("slow", "Real-ESRGAN on the processor's graphics, slowly")
    assert ai.note == "SD episodes get the fast upscale unless you choose the AI model on Convert."
    assert (subtitles.state, subtitles.how) == ("limited", "Fast on the processor")
    assert subtitles.note == "Best wants a graphics card with 4 GB of memory of its own."


def test_a_pc_with_no_encoder_says_why_and_what_stopped_its_own_cards():
    stopped = Checked(
        None, "Driver does not support the required nvenc API version", True, True, ""
    )

    found = abilities([GTX], stopped, Speeds())

    convert = found[0]
    assert (convert.state, convert.how) == ("no", "Not on this PC")
    assert convert.note == (
        "NVIDIA's encoder (NVENC) didn't start: Driver does not support the required nvenc API "
        "version"
    )
    assert found[1].note == "Not without an encoder for converting."
    assert found[4].state == "ready"  # the player plays on any PC


def test_another_encoder_converts_while_the_cards_own_needs_its_driver():
    other = Checked(
        "qsv", "Driver does not support the required nvenc API version.", True, True, ""
    )

    convert = abilities([GTX, UHD], other, Speeds())[0]

    assert (convert.state, convert.how) == ("ready", "HEVC 10-bit on Intel Quick Sync")
    assert convert.note == (
        "NVIDIA's encoder (NVENC) didn't start: Driver does not support the required nvenc API "
        "version."
    )


def test_cards_are_what_windows_lists_on_the_pcs_bus():
    listed: list[dict[str, object]] = [
        {
            "Name": "NVIDIA GeForce GTX 1660 SUPER",
            "PNPDeviceID": r"PCI\VEN_10DE&DEV_21C4&SUBSYS_00000000",
            "DriverVersion": "32.0.16.1742",
            "AdapterRAM": 4293918720,  # Windows' listing stops at 4 GB
        },
        {
            "Name": "Intel(R) UHD Graphics 630",
            "PNPDeviceID": r"PCI\VEN_8086&DEV_3E92",
            "DriverVersion": "31.0.101.2111",
            "AdapterRAM": 1073741824,
        },
        {"Name": "Microsoft Remote Display Adapter", "PNPDeviceID": r"SWD\REMOTEDISPLAYENUM"},
        {"Name": "", "PNPDeviceID": r"PCI\VEN_1002"},
    ]

    cards = cards_from(listed, {"NVIDIA GeForce GTX 1660 SUPER": 6 * GIB})

    assert cards == (
        Card("NVIDIA GeForce GTX 1660 SUPER", "nvidia", 6 * GIB, False, "617.42"),
        Card("Intel(R) UHD Graphics 630", "intel", GIB, True, "31.0.101.2111"),
    )


def test_only_words_about_its_driver_send_the_owner_for_a_newer_one():
    assert driver_problem("Driver does not support the required nvenc API version.")
    assert driver_problem("DLL amfrt64.dll failed to open.")
    assert not driver_problem("Error creating a MFX session: -9.")
    assert not driver_problem("No capable devices found.")
    assert not driver_problem(None)

    old = Checked(None, "No capable devices found.", True, True, "")
    convert = abilities([GTX], old, Speeds())[0]

    assert convert.note == "Its graphics card has no encoder for HEVC 10-bit."


def test_windows_listing_a_card_at_its_cap_has_four_gb_or_more():
    listed: list[dict[str, object]] = [
        {
            "Name": "NVIDIA GeForce RTX 3060",
            "PNPDeviceID": r"PCI\VEN_10DE&DEV_2504",
            "AdapterRAM": 4293918720,  # Windows' most, for any card of 4 GB or more
        }
    ]

    [card] = cards_from(listed, {})  # the registry didn't say

    assert card.memory is not None
    assert card.memory >= BEST_MEMORY
    assert hearing_places([card], CHECKED)["best"] == "card"


def test_best_names_what_this_pc_lacks_for_it():
    no_directx = Checked("nvenc", None, ai=False, anime4k=True, at="")

    assert best_wants(no_directx) == "Best wants a graphics card that runs DirectX 12."
    assert best_wants(CHECKED) == "Best wants a graphics card with 4 GB of memory of its own."
    subtitles = abilities([GTX], no_directx, Speeds())[3]
    assert subtitles.note == "Best wants a graphics card that runs DirectX 12."


def test_the_queue_says_why_this_pc_cant_convert():
    stopped = Checked(
        None, "Driver does not support the required nvenc API version.", True, True, ""
    )
    none = Checked(None, "No capable devices found.", True, True, "")

    assert why_not_converting([GTX], stopped).startswith("NVIDIA's encoder (NVENC) didn't start")
    assert why_not_converting([GTX], none) == (
        "This PC can't convert to your standard: its graphics card has no encoder for HEVC 10-bit."
    )


def test_the_player_is_what_its_check_found():
    windows_n = replace(CHECKED, player="h264_nvenc")
    nothing = replace(CHECKED, player=None)

    assert abilities([GTX], CHECKED, Speeds())[4].how == "Windows' own video encoder"
    assert abilities([GTX], windows_n, Speeds())[4].how == "NVIDIA's encoder (NVENC)"
    player = abilities([GTX], nothing, Speeds())[4]
    assert (player.state, player.how) == ("no", "Not on this PC")
    assert player.note is not None
    assert "Media Feature Pack" in player.note


def test_a_slow_fast_upscale_points_to_the_quicker_way():
    crawling = Speeds(best=3.2, fast=3.0, reencode=40.0)

    fast = abilities([GTX], CHECKED, crawling)[2]

    assert fast.state == "slow"
    assert fast.note == "Re-encode only, on Convert, is much quicker."
