"""Where files go and what they're called. Expected names come from the design boards."""

from pathlib import PureWindowsPath

import pytest

from kura.core.naming import (
    MAX_PATH,
    PathTooLongError,
    episode_path,
    movie_path,
    safe_name,
    unique_path,
)

LIBRARY = PureWindowsPath(r"D:\Anime")


class TestEpisodes:
    def test_an_episode_goes_into_its_show_and_season_folders(self):
        path = episode_path(
            LIBRARY,
            "Dragon Ball Z",
            1989,
            season=1,
            episode=1,
            title="The New Threat",
            extension=".mkv",
        )

        assert path == LIBRARY / (
            r"TV\Dragon Ball Z (1989)\Season 01\Dragon Ball Z (1989) - S01E01 - The New Threat.mkv"
        )

    def test_without_an_episode_title(self):
        path = episode_path(LIBRARY, "Dragon Ball Z", 1989, season=1, episode=5, extension=".mkv")

        assert path.name == "Dragon Ball Z (1989) - S01E05.mkv"

    def test_without_a_year(self):
        path = episode_path(LIBRARY, "Trigun", None, season=1, episode=3, extension=".mp4")

        assert path == LIBRARY / r"TV\Trigun\Season 01\Trigun - S01E03.mp4"

    def test_three_digit_episode_numbers(self):
        path = episode_path(
            LIBRARY, "Dragon Ball Super", 2015, season=1, episode=131, extension=".mkv"
        )

        assert path.name == "Dragon Ball Super (2015) - S01E131.mkv"

    def test_two_episodes_in_one_file(self):
        path = episode_path(
            LIBRARY, "Naruto Shippuden", 2007, season=1, episode=1, last_episode=2, extension=".mkv"
        )

        assert path.name == "Naruto Shippuden (2007) - S01E01-E02.mkv"

    def test_specials_go_to_season_00(self):
        path = episode_path(
            LIBRARY, "Dragon Ball Z", 1989, season=0, episode=1, title="Bardock", extension=".mkv"
        )

        assert path == LIBRARY / (
            r"TV\Dragon Ball Z (1989)\Season 00\Dragon Ball Z (1989) - S00E01 - Bardock.mkv"
        )

    def test_titles_are_made_safe_for_windows(self):
        path = episode_path(
            LIBRARY,
            "Re:Zero",
            2016,
            season=1,
            episode=1,
            title="The End of the Beginning and the Beginning of the End?",
            extension=".mkv",
        )

        assert path == LIBRARY / (
            r"TV\Re-Zero (2016)\Season 01"
            r"\Re-Zero (2016) - S01E01 - The End of the Beginning and the Beginning of the End.mkv"
        )


class TestMovies:
    def test_a_movie_gets_its_own_folder(self):
        path = movie_path(
            LIBRARY, "Dragon Ball Z: Broly - The Legendary Super Saiyan", 1993, extension=".avi"
        )

        assert path == LIBRARY / (
            r"Movies\Dragon Ball Z - Broly - The Legendary Super Saiyan (1993)"
            r"\Dragon Ball Z - Broly - The Legendary Super Saiyan (1993).avi"
        )

    def test_a_movie_without_a_year(self):
        path = movie_path(LIBRARY, "Cowboy Bebop: The Movie", None, extension=".mkv")

        assert path == LIBRARY / r"Movies\Cowboy Bebop - The Movie\Cowboy Bebop - The Movie.mkv"


class TestSafeNames:
    @pytest.mark.parametrize(
        ("name", "safe"),
        [
            ("Broly: The Legendary Super Saiyan", "Broly - The Legendary Super Saiyan"),
            ("Kaguya-sama: Love Is War", "Kaguya-sama - Love Is War"),
            ("Re:Zero", "Re-Zero"),
            ("Is This a Zombie? Of the Dead", "Is This a Zombie - Of the Dead"),
            ("Who Wants to Be a Hero?", "Who Wants to Be a Hero"),
            ("Fate/Zero", "Fate-Zero"),
            ('The "Hero" Returns', "The 'Hero' Returns"),
            ("Bokura no*", "Bokura no"),
            ("Steins;Gate", "Steins;Gate"),
            ("Love Live! School Idol Project", "Love Live! School Idol Project"),
            ("Mr. Osomatsu.", "Mr. Osomatsu"),
            ("Dragon  Ball\tZ", "Dragon Ball Z"),
            ("  Trigun  ", "Trigun"),
        ],
    )
    def test_characters_windows_cant_use_are_replaced(self, name: str, safe: str):
        assert safe_name(name) == safe

    @pytest.mark.parametrize("reserved", ["CON", "nul", "Com1", "LPT9", "aux"])
    def test_names_windows_reserves_get_an_underscore(self, reserved: str):
        assert safe_name(reserved) == f"{reserved}_"

    def test_a_name_with_nothing_usable_is_refused(self):
        with pytest.raises(ValueError, match="nothing Windows can use"):
            safe_name("???")


class TestLongPaths:
    def test_a_long_episode_title_is_shortened_at_a_word_to_fit(self):
        title = "A Very Long Episode Title " * 12
        path = episode_path(
            LIBRARY, "Dragon Ball Z", 1989, season=1, episode=1, title=title, extension=".mkv"
        )

        assert len(str(path)) <= MAX_PATH
        assert path.name.startswith("Dragon Ball Z (1989) - S01E01 - A Very Long Episode Title")
        assert path.suffix == ".mkv"
        assert not path.stem.endswith((" ", "-"))

    def test_the_episode_title_goes_entirely_when_nothing_else_fits(self):
        deep = PureWindowsPath("D:\\" + "\\".join(["Folder"] * 26))
        path = episode_path(
            deep,
            "Dragon Ball Z",
            1989,
            season=1,
            episode=1,
            title="The New Threat",
            extension=".mkv",
        )

        assert len(str(path)) <= MAX_PATH
        assert path.name == "Dragon Ball Z (1989) - S01E01.mkv"

    def test_a_path_that_can_never_fit_is_refused(self):
        deep = PureWindowsPath("D:\\" + "\\".join(["Folder"] * 40))

        with pytest.raises(PathTooLongError):
            episode_path(deep, "Dragon Ball Z", 1989, season=1, episode=1, extension=".mkv")


class TestTakenNames:
    def test_a_free_name_is_kept(self):
        path = LIBRARY / "Show - S01E05.mkv"

        assert unique_path(path, taken=set()) == path

    def test_a_taken_name_gets_2_and_then_3(self):
        path = LIBRARY / "Show - S01E05.mkv"
        taken = {str(path), str(LIBRARY / "Show - S01E05 (2).mkv")}

        assert unique_path(path, taken=taken) == LIBRARY / "Show - S01E05 (3).mkv"

    def test_windows_names_differ_only_by_case_count_as_taken(self):
        path = LIBRARY / "Show - S01E05.mkv"

        assert unique_path(path, taken={r"d:\anime\show - s01e05.MKV"}).name == (
            "Show - S01E05 (2).mkv"
        )
