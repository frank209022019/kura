"""What Kura keeps about this PC: what it has, what checking found, and its own times."""

import sqlite3
import subprocess
from datetime import datetime
from fractions import Fraction

import pytest

from kura import hardware
from kura.core.estimate import HEARING, Speeds
from kura.core.hardware import GIB, Card, Checked
from kura.core.media import MediaInfo, Video
from kura.core.standard import Method
from kura.hardware import Facts, Measured

NOW = datetime.fromisoformat("2026-10-15T20:00:00+02:00")
LATER = datetime.fromisoformat("2026-10-16T02:00:00+02:00")
UHD = Card("Intel(R) UHD Graphics 620", "intel", 128 * 1024**2, True, "31.0.101.2111")
LAPTOP = Facts((UHD,), "Intel Core i7-8550U", 4, 16 * GIB)
CHECKED = Checked("qsv", None, ai=True, anime4k=True, at=NOW.isoformat())


def episode(width: int, height: int) -> MediaInfo:
    picture = Video("h264", width, height, Fraction(16, 9), Fraction(24000, 1001), 8, False)
    return MediaInfo("mkv", 1440.0, 0, picture, (), (), 0)


def test_what_checking_found_is_kept(conn: sqlite3.Connection):
    assert hardware.stored(conn) == (None, None)

    hardware.keep(conn, LAPTOP, CHECKED)

    assert hardware.stored(conn) == (LAPTOP, CHECKED)
    assert hardware.checked_here(conn) == CHECKED


def test_times_are_a_guess_till_this_pc_measures_them(conn: sqlite3.Connection):
    assert hardware.speeds(conn) == Speeds()
    assert hardware.measured(conn) is None

    hardware.keep_speeds(conn, {}, NOW)  # a test that could time nothing

    assert hardware.measured(conn) is None

    hardware.keep_speeds(conn, {"best": 0.4, "fast": 14.0, "reencode": 40.0}, NOW)

    assert hardware.speeds(conn) == Speeds(best=0.4, fast=14.0, reencode=40.0)
    assert hardware.measured(conn) == Measured(NOW.isoformat(), True, 0, 0)

    hardware.keep_speeds(conn, {"reencode": 50.0}, LATER)  # Anime4K couldn't be timed, say

    assert hardware.speeds(conn) == Speeds(best=0.4, fast=14.0, reencode=50.0)


def test_each_file_done_measures_its_way_again(conn: sqlite3.Connection):
    sd = episode(720, 480)

    hardware.learn_conversion(conn, Method.BEST, sd, 1080, 3600.0, NOW)  # an hour

    frames = 1440 * 24000 / 1001
    first = frames / 3600 * 720 * 480 / 1e6  # megapixels of the source a second
    assert hardware.speeds(conn).best == pytest.approx(first)
    assert hardware.measured(conn) == Measured(NOW.isoformat(), False, 1, 0)

    hardware.learn_conversion(conn, Method.BEST, sd, 1080, 1800.0, LATER)  # twice as quick

    assert hardware.speeds(conn).best == pytest.approx(first * 0.7 + first * 2 * 0.3)
    assert hardware.measured(conn) == Measured(NOW.isoformat(), False, 2, 0)  # since the first


def test_the_fast_upscale_and_a_re_encode_measure_at_1080p(conn: sqlite3.Connection):
    frames = 1440 * 24000 / 1001

    hardware.learn_conversion(conn, Method.FAST, episode(960, 540), 720, 600.0, NOW)
    hardware.learn_conversion(conn, Method.REENCODE, episode(720, 480), 1080, 60.0, NOW)

    speeds = hardware.speeds(conn)
    assert speeds.fast == pytest.approx(frames / 600 * (720 / 1080) ** 2)  # as making 1080p
    assert speeds.reencode == Speeds().reencode  # an SD source says nothing of 1080p's speed

    hardware.learn_conversion(conn, Method.REENCODE, episode(1920, 1080), 1080, 300.0, NOW)

    assert hardware.speeds(conn).reencode == pytest.approx(frames / 300)


def test_subtitles_are_timed_where_they_were_made(conn: sqlite3.Connection):
    hardware.keep(conn, LAPTOP, CHECKED)  # no card with the memory: Fast on the processor
    assert hardware.hearing(conn) == {"best": HEARING["best"], "fast": HEARING["fast_processor"]}
    assert hardware.hearing_place(conn, "fast") == "processor"
    assert hardware.hearing_place(conn, "best") is None

    hardware.learn_hearing(conn, "fast_processor", 1440.0, 2880.0, NOW)

    assert hardware.hearing(conn)["fast"] == 2.0
    assert hardware.rates(conn) == {**HEARING, "fast_processor": 2.0}  # what About shows
    assert hardware.measured(conn) == Measured(NOW.isoformat(), False, 0, 1)


def test_a_test_keeps_the_subtitles_times(conn: sqlite3.Connection):
    hardware.learn_hearing(conn, "fast", 1440.0, 288.0, NOW)

    hardware.keep_speeds(conn, {"best": 3.0, "fast": 50.0, "reencode": 150.0}, LATER)

    assert hardware.hearing(conn)["fast"] == pytest.approx(0.2)
    assert hardware.measured(conn) == Measured(LATER.isoformat(), True, 0, 0)

    hardware.forget_speeds(conn)  # another card's

    assert hardware.speeds(conn) == Speeds()
    assert hardware.hearing(conn)["fast"] == HEARING["fast"]


def test_damaged_records_of_this_pc_are_as_if_never_checked(conn: sqlite3.Connection):
    with conn:
        conn.execute("INSERT INTO settings VALUES ('pc', '{\"facts\": 3}')")
        conn.execute("INSERT INTO settings VALUES ('pc_speeds', 'not json')")

    assert hardware.stored(conn) == (None, None)
    assert hardware.speeds(conn) == Speeds()
    assert hardware.measured(conn) is None


def test_this_pc_as_windows_has_it():
    found = hardware.look()

    assert found is not None  # Windows answered
    assert all(card.name for card in found.cards)
    assert found.memory is None or found.memory > GIB


def test_windows_not_answering_is_told_apart_from_no_cards(monkeypatch: pytest.MonkeyPatch):
    def silent(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired("powershell", 30)

    monkeypatch.setattr("kura.hardware.subprocess.run", silent)

    assert hardware.look() is None
