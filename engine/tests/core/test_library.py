"""What a scan counts as a video, where it never looks, and how folders may sit together."""

from pathlib import PureWindowsPath

import pytest

from kura.core.extensions import is_video
from kura.core.library import (
    Covered,
    Holds,
    Picture,
    fits,
    picture_size,
    skipped_folder,
    time_left,
    work_of,
)


@pytest.mark.parametrize(
    "name",
    [
        "[Group] DBZ - 001 [480p].mkv",
        "Dragon Ball - 003 - The Nimbus Cloud of Roshi.MKV",
        "Broly the Legendary Super Saiyan.avi",
        "Cowboy Bebop - The Movie (2001).mp4",
        "VTS_01_1.VOB",
        "episode.m2ts",
        "old.rmvb",
        "show.ogm",
    ],
)
def test_videos_are_found_whatever_the_case_of_their_extension(name: str):
    assert is_video(name)


@pytest.mark.parametrize(
    "name",
    [
        "Dragon Ball - 001.en.srt",
        "Kura - Gap analysis.md",
        "folder.jpg",
        "Dragon Ball Z (1989) - S01E01.mkv.kura-partial",  # a copy Kura is still making
        "release.nfo",
        "mkv",
    ],
)
def test_subtitles_reports_pictures_and_unfinished_copies_are_not_videos(name: str):
    assert not is_video(name)


@pytest.mark.parametrize(
    ("name", "skipped"),
    [
        ("Kura quarantine", True),
        ("kura QUARANTINE", True),
        ("$RECYCLE.BIN", True),
        ("System Volume Information", True),
        (".thumbnails", True),
        ("Season 01", False),
        ("Dragon Ball Z (1989)", False),
        ("Specials", False),
    ],
)
def test_a_scan_never_looks_in_quarantine_or_windows_own_folders(name: str, skipped: bool):
    assert skipped_folder(name) is skipped


ANIME = PureWindowsPath(r"D:\Anime")


def test_a_new_folder_fits_beside_unrelated_ones():
    assert fits(PureWindowsPath(r"F:\More anime"), [ANIME]) is None
    assert fits(PureWindowsPath(r"D:\Anime films"), [ANIME]) is None  # a prefix isn't a parent


def test_a_folder_already_covered_isnt_added_twice():
    assert fits(PureWindowsPath(r"d:\anime"), [ANIME]) == Covered(ANIME)
    assert fits(PureWindowsPath(r"D:\Anime\Shonen\Naruto"), [ANIME]) == Covered(ANIME)


def test_a_parent_folder_takes_in_the_folders_below_it():
    shonen, films = PureWindowsPath(r"D:\Anime\Shonen"), PureWindowsPath(r"D:\Anime\Films")

    assert fits(ANIME, [shonen, PureWindowsPath(r"F:\Other"), films]) == Holds((shonen, films))


@pytest.mark.parametrize(
    ("done", "total", "elapsed", "left"),
    [
        (0, 100, 0.0, None),  # no pace yet
        (3, 100, 9.0, None),  # too few files to tell
        (50, 100, 100.0, 100.0),
        (100, 100, 200.0, 0.0),
    ],
)
def test_time_left_follows_the_pace_so_far(
    done: int, total: int, elapsed: float, left: float | None
):
    assert time_left(done, total, elapsed) == left


@pytest.mark.parametrize(
    ("width", "height", "size"),
    [
        (720, 540, "sd"),  # Dragon Ball's episodes
        (720, 576, "sd"),  # PAL DVD
        (640, 480, "sd"),
        (1280, 720, "720p"),
        (960, 720, "720p"),  # 4:3 at 720p
        (1440, 1080, "1080p"),
        (1920, 800, "1080p"),  # a wide film at 1080p
        (3840, 2160, "larger"),
        (None, None, "unknown"),
    ],
)
def test_a_picture_is_sorted_by_its_size(width: int | None, height: int | None, size: Picture):
    assert picture_size(width, height) == size


def test_a_files_result_is_made_beside_it_under_its_whole_name():
    folder = PureWindowsPath(r"D:\Anime\Old")

    assert work_of(folder / "Ep01.avi") == folder / "Ep01.avi.kura-converting"
    assert work_of(folder / "Ep01.avi") != work_of(folder / "Ep01.mp4")
