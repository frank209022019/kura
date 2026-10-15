from pathlib import PurePath

from kura.core.languages import beside_language, is_english, listed, track_languages


def test_english_is_known_however_a_file_names_it():
    assert all(is_english(code) for code in ("eng", "en", "English", "EN", "en-US", "en_GB"))
    assert not any(is_english(code) for code in ("jpn", "ger", "fre", ""))


def test_a_subtitle_file_beside_a_video_names_its_language():
    video = PurePath("Show (1989) - S01E01.mkv")

    assert beside_language(PurePath("Show (1989) - S01E01.en.srt"), video) == "en"
    assert beside_language(PurePath("Show (1989) - S01E01.English.forced.ass"), video) == "english"
    assert beside_language(PurePath("Show (1989) - S01E01.forced.de.srt"), video) == "de"
    assert beside_language(PurePath("Show (1989) - S01E01.srt"), video) == ""
    # The name Kura gives its own when another file has the first.
    assert beside_language(PurePath("Show (1989) - S01E01.kura.en.srt"), video) == "en"


def test_each_track_keeps_its_language_or_none():
    assert track_languages(["JPN", None, "eng"]) == ["jpn", "", "eng"]


def test_each_language_is_listed_once_in_the_order_first_met():
    assert listed(["jpn", "eng", "jpn", "", ""]) == ["jpn", "eng", ""]
