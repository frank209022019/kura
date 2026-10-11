"""Reading file names. Most examples come straight from the design boards."""

from pathlib import PureWindowsPath
from typing import Any

import pytest

from kura.core.names import Kind, ParsedName, film_part, parse_name


def parsed(path: str) -> ParsedName:
    return parse_name(PureWindowsPath(path))


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            r"D:\Anime\Downloads\[Group] DBZ - 001 [480p].mkv",
            {"title": "DBZ", "episode": 1, "group": "Group", "height": 480, "folder_title": None},
        ),
        (
            r"D:\Anime\Downloads\[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv",
            {"title": "Cowboy Bebop", "episode": 1, "height": 720, "group": None},
        ),
        (r"D:\Anime\Downloads\Death Note 01.avi", {"title": "Death Note", "episode": 1}),
        (
            r"D:\Anime\Downloads\[DB] Death_Note_07 (720p).mkv",
            {"title": "Death Note", "episode": 7, "group": "DB", "height": 720},
        ),
        (r"D:\Anime\Downloads\trigun_03.mp4", {"title": "trigun", "episode": 3}),
        (
            r"D:\Anime\[SubsPlease] Frieren - 01 (1080p) [ABCD1234].mkv",
            {"title": "Frieren", "episode": 1, "group": "SubsPlease", "height": 1080},
        ),
        (
            r"D:\Anime\[Erai-raws] Dragon Ball Daima - 20 [1080p][Multiple Subtitle].mkv",
            {"title": "Dragon Ball Daima", "episode": 20, "group": "Erai-raws"},
        ),
        (
            r"D:\Anime\[Coalgirls]_Neon_Genesis_Evangelion_01_(640x480_DVD_h264)_[ABCD1234].mkv",
            {"title": "Neon Genesis Evangelion", "episode": 1, "height": 480},
        ),
        (
            r"D:\Anime\Fullmetal Alchemist Brotherhood - 01v2.mkv",
            {"title": "Fullmetal Alchemist Brotherhood", "episode": 1, "version": 2},
        ),
        (
            r"D:\Anime\Yu Yu Hakusho\Yu Yu Hakusho 112.avi",
            {"title": "Yu Yu Hakusho", "episode": 112},
        ),
        (
            r"D:\Anime\[Group] Dragon Ball GT - 64 (DVD 576p).mkv",
            {"title": "Dragon Ball GT", "episode": 64, "height": 576},
        ),
    ],
)
def test_fansub_names_with_absolute_episode_numbers(path: str, expected: dict[str, Any]):
    result = parsed(path)

    assert result.kind == Kind.EPISODE
    assert {key: getattr(result, key) for key in expected} == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            r"D:\Anime\TV\Dragon Ball Z (1989)\Season 01\Dragon Ball Z (1989) - S01E05.mkv",
            {"title": "Dragon Ball Z", "year": 1989, "season": 1, "episode": 5, "folder_season": 1},
        ),
        (
            r"D:\Anime\Sailor Moon\Season 01\Sailor Moon - S01E01 - A Moon Star is Born.mkv",
            {"season": 1, "episode": 1, "episode_title": "A Moon Star is Born"},
        ),
        (
            r"D:\Anime\[HorribleSubs] One Punch Man S2 - 01 [720p].mkv",
            {"title": "One Punch Man", "season": 2, "episode": 1},
        ),
        (
            r"D:\Anime\Dragon.Ball.Super.S01E131.1080p.BluRay.x264-GROUP.mkv",
            {"title": "Dragon Ball Super", "season": 1, "episode": 131, "episode_title": None},
        ),
    ],
)
def test_season_and_episode_names(path: str, expected: dict[str, Any]):
    result = parsed(path)

    assert result.kind == Kind.EPISODE
    assert {key: getattr(result, key) for key in expected} == expected


def test_a_hunter_x_hunter_year_is_a_year_not_a_season():
    result = parsed(r"D:\Anime\[Kametsu] Hunter x Hunter (2011) - 148 [BD 1080p Hi10 FLAC].mkv")

    assert (result.title, result.year, result.season, result.episode) == (
        "Hunter x Hunter",
        2011,
        None,
        148,
    )


def test_episode_titles_are_kept():
    result = parsed(r"D:\Anime\Dragon Ball\Dragon Ball - 001 - Secret of the Dragon Balls.mkv")

    assert (result.title, result.episode, result.episode_title) == (
        "Dragon Ball",
        1,
        "Secret of the Dragon Balls",
    )


def test_a_title_with_final_in_its_episode_title_keeps_both():
    result = parsed(r"D:\Anime\Dragon Ball Z Kai - 98 - The Final Battle.mkv")

    assert (result.title, result.episode, result.episode_title) == (
        "Dragon Ball Z Kai",
        98,
        "The Final Battle",
    )


def test_two_episodes_in_one_file():
    result = parsed(r"D:\Anime\Naruto Shippuden - 01-02 [720p].mkv")

    assert (result.episode, result.episode_end) == (1, 2)


def test_a_part_number_is_kept_though_anitopy_drops_it():
    # Season 3 Part 2 numbers its episodes from 1 again, so "Part 2" decides where they go.
    result = parsed(r"D:\Anime\[SubsPlease] Shingeki no Kyojin S3 Part 2 - 03 (1080p).mkv")

    assert (result.title, result.season, result.part, result.episode) == (
        "Shingeki no Kyojin",
        3,
        2,
        3,
    )
    assert parsed(r"D:\Anime\Shingeki no Kyojin S3 - 03.mkv").part is None
    assert parsed(r"D:\Anime\Cowboy Bebop\Cowboy Bebop - Session 05 - Part of It.mkv").part is None


def test_words_like_session_are_not_part_of_the_title():
    result = parsed(
        r"D:\Anime\Cowboy Bebop\Cowboy Bebop - Session 05 - Ballad of Fallen Angels.mkv"
    )

    assert (result.title, result.episode, result.episode_title) == (
        "Cowboy Bebop",
        5,
        "Ballad of Fallen Angels",
    )


class TestFolders:
    def test_a_bare_episode_number_takes_show_year_and_season_from_its_folders(self):
        result = parsed(r"D:\Anime\TV\Dragon Ball Z (1989)\Season 03\05.mkv")

        assert result.title is None
        assert (result.folder_title, result.year, result.folder_season, result.episode) == (
            "Dragon Ball Z",
            1989,
            3,
            5,
        )
        assert result.best_title == "Dragon Ball Z"

    def test_absolute_numbers_keep_the_season_folder_apart(self):
        result = parsed(
            r"D:\Anime\Shonen\Naruto Shippuden\Season 07\Naruto Shippuden - 143 [720p].mkv"
        )

        assert (result.title, result.season, result.folder_season, result.episode) == (
            "Naruto Shippuden",
            None,
            7,
            143,
        )
        assert result.folder_title == "Naruto Shippuden"

    def test_a_specials_folder_is_season_zero(self):
        result = parsed(
            r"D:\Anime\TV\Dragon Ball Z (1989)\Specials\Dragon Ball Z (1989) - S00E01.mkv"
        )

        assert (result.season, result.folder_season, result.kind) == (0, 0, Kind.SPECIAL)

    @pytest.mark.parametrize("folder", ["Downloads", "Anime", "TV", "Extras", "New folder"])
    def test_general_folders_are_not_titles(self, folder: str):
        assert parsed(rf"D:\{folder}\01.mkv").folder_title is None

    def test_a_file_at_the_top_of_a_drive_has_no_folder_title(self):
        assert parsed(r"D:\Trigun 01.mkv").folder_title is None


class TestKinds:
    def test_a_name_without_an_episode_number_is_a_movie(self):
        result = parsed(r"D:\Anime\Movies\Broly the Legendary Super Saiyan.avi")

        assert (result.kind, result.title, result.episode) == (
            Kind.MOVIE,
            "Broly the Legendary Super Saiyan",
            None,
        )

    def test_movie_in_the_name_marks_a_movie(self):
        result = parsed(r"D:\Anime\Downloads\Cowboy Bebop Movie.mkv")

        assert (result.kind, result.title) == (Kind.MOVIE, "Cowboy Bebop")

    def test_the_movie_goes_as_a_whole(self):
        result = parsed(r"D:\Anime\Movies\Cowboy Bebop - The Movie (2001).mkv")

        assert (result.kind, result.title, result.year) == (Kind.MOVIE, "Cowboy Bebop", 2001)

    def test_a_year_and_no_episode_is_a_movie(self):
        result = parsed(r"D:\Anime\[Group] Dragon Ball Super - Broly (2018) [1080p].mkv")

        assert (result.kind, result.title, result.year) == (
            Kind.MOVIE,
            "Dragon Ball Super - Broly",
            2018,
        )

    def test_a_movie_title_with_brackets_survives(self):
        result = parsed(r"D:\Anime\Evangelion 1.11 You Are (Not) Alone (2007).mkv")

        assert (result.kind, result.title, result.year) == (
            Kind.MOVIE,
            "Evangelion 1.11 You Are (Not) Alone",
            2007,
        )

    def test_an_ova_is_a_special(self):
        result = parsed(r"D:\Anime\Hellsing Ultimate OVA 01.mkv")

        assert (result.kind, result.title, result.episode) == (
            Kind.SPECIAL,
            "Hellsing Ultimate",
            1,
        )

    def test_a_creditless_ending_is_an_extra(self):
        result = parsed(r"D:\Anime\[Group] Hunter x Hunter - NCED01 [1080p].mkv")

        assert (result.kind, result.title) == (Kind.EXTRA, "Hunter x Hunter")

    def test_a_creditless_opening_alone_has_no_title(self):
        result = parsed(r"D:\Anime\Shonen\Extras\NCOP01.mkv")

        assert (result.kind, result.title, result.folder_title) == (Kind.EXTRA, None, None)

    def test_dvd_files_are_recognised(self):
        result = parsed(r"D:\Anime\Old DVDs\VTS_02_1.VOB")

        assert (result.kind, result.title, result.episode) == (Kind.DVD, None, None)


class TestNamesThatNeedAMatch:
    def test_a_group_and_an_episode_but_no_title(self):
        result = parsed(r"D:\Anime\Downloads\[subs] ep03 final.mkv")

        assert (result.title, result.episode, result.group, result.best_title) == (
            None,
            3,
            "subs",
            None,
        )

    def test_a_movie_named_movie(self):
        result = parsed(r"D:\Anime\Misc\movie_final_v2.mp4")

        assert (result.kind, result.title, result.version) == (Kind.MOVIE, None, 2)

    @pytest.mark.parametrize("name", ["Ep.mkv", "Episode.mkv", "Vol.mkv"])
    def test_a_name_anitopy_trips_over_still_has_its_folders(self, name: str):
        result = parsed(rf"D:\Anime\Cowboy Bebop\{name}")

        assert (result.folder_title, result.episode) == ("Cowboy Bebop", None)


class TestCopies:
    @pytest.mark.parametrize(
        "name",
        [
            "Naruto 042 (copy).mkv",
            "Naruto 042 - Copy.mkv",
            "Naruto 042 - Copy (2).mkv",
            "Naruto 042 (2).mkv",
        ],
    )
    def test_copies_are_marked_and_still_read(self, name: str):
        result = parsed(rf"D:\Anime\Naruto\{name}")

        assert (result.title, result.episode, result.is_copy, result.group) == (
            "Naruto",
            42,
            True,
            None,
        )

    def test_kuras_own_keep_both_names_are_copies(self):
        result = parsed(
            r"D:\TV\Dragon Ball Z (1989)\Season 01\Dragon Ball Z (1989) - S01E05 (2).mkv"
        )

        assert (result.is_copy, result.season, result.episode) == (True, 1, 5)

    def test_an_ordinary_name_is_not_a_copy(self):
        assert parsed(r"D:\Anime\Death Note 01.avi").is_copy is False


def test_parsing_from_many_threads_at_once_gives_the_same_answers():
    from concurrent.futures import ThreadPoolExecutor

    paths = [
        r"D:\Anime\[Group] DBZ - 001 [480p].mkv",
        r"D:\Anime\[Kametsu] Hunter x Hunter (2011) - 148 [BD 1080p Hi10 FLAC].mkv",
    ] * 200
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(parsed, paths))

    assert {(r.title, r.episode) for r in results} == {("DBZ", 1), ("Hunter x Hunter", 148)}


@pytest.mark.parametrize(
    ("name", "part"),
    [
        ("Akira (1988) CD1", 1),
        ("Akira.1988.cd2", 2),
        ("Akira (1988) - pt1", 1),
        ("Akira (1988) - Part 2", 2),
        ("Akira (1988) - disc 2", 2),
        ("Akira (1988) CD1 (copy)", 1),
        ("Akira (1988)", None),
        ("Mobile Suit Gundam 0083", None),
    ],
)
def test_a_films_part_is_read_from_the_end_of_its_name(name: str, part: int | None):
    assert film_part(name) == part


@pytest.mark.parametrize("name", ["Akira (1988).cd2.avi", "Akira (1988) - disc 2.mkv"])
def test_a_films_part_isnt_part_of_its_title(name: str):
    result = parsed(rf"D:\Anime\Movies\{name}")

    assert (result.kind, result.title, result.year, result.episode) == (
        Kind.MOVIE,
        "Akira",
        1988,
        None,
    )
