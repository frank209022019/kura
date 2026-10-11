"""Which anime a file is: grouping files, scoring AniList's entries, picking TMDB's show."""

import json
from datetime import date
from pathlib import Path, PureWindowsPath

from kura.core.catalog import Anime, Hit, TitleKind, anime_list, hits
from kura.core.identify import (
    SURE,
    FileFacts,
    base_title,
    group_files,
    guesses,
    normalize,
    pick_hit,
    similarity,
)
from kura.core.names import parse_name
from tests.tmdb_data import movie_search, tv_search

ANILIST = Path(__file__).parent.parent / "data" / "anilist"


def entries(name: str) -> list[Anime]:
    return anime_list(json.loads((ANILIST / f"{name}.json").read_text(encoding="utf-8")))


def facts(path: str, minutes: float | None = 24.0, number: int = 0) -> FileFacts:
    where = PureWindowsPath(path)
    return FileFacts(number, where, parse_name(where), minutes)


def test_files_named_alike_are_looked_up_together():
    found = group_files(
        [
            facts(r"D:\Anime\Dragon Ball Z\Dragon Ball Z - 001.mkv", number=1),
            facts(r"D:\Anime\Dragon Ball Z\Dragon Ball Z - 002.mkv", number=2),
            facts(r"D:\Anime\Downloads\[Group] Cowboy Bebop - 05 [480p].mkv", number=3),
        ]
    )

    assert [(g.query, [f.id for f in g.files]) for g in found] == [
        ("Cowboy Bebop", [3]),
        ("Dragon Ball Z", [1, 2]),
    ]


def test_a_bare_episode_takes_its_show_from_the_folder():
    [group] = group_files([facts(r"D:\Anime\Trigun (1998)\Season 01\05.mkv")])

    assert (group.query, group.year) == ("Trigun", 1998)


def test_films_are_looked_up_apart_from_episodes():
    found = group_files(
        [
            facts(r"D:\Anime\Cowboy Bebop\Cowboy Bebop - 01.mkv"),
            facts(r"D:\Anime\Cowboy Bebop\Cowboy Bebop - Movie.mkv", minutes=115),
        ]
    )

    assert [(g.query, g.movie) for g in found] == [
        ("Cowboy Bebop", False),
        ("Cowboy Bebop", True),
    ]


def test_extras_and_dvd_files_arent_looked_up():
    found = group_files(
        [
            facts(r"D:\Anime\Trigun\Extras\NCOP01.mkv"),
            facts(r"D:\Anime\Old DVDs\VTS_02_1.VOB"),
        ]
    )

    assert found == []


def test_dragon_ball_z_is_sure_and_kai_is_not():
    [group] = group_files(
        [facts(rf"D:\Anime\Dragon Ball Z (1989)\Dragon Ball Z - {n:03}.mkv") for n in (1, 150, 291)]
    )

    found = guesses(group, entries("dragon-ball-z"))

    assert found[0].anime.id == 813
    assert found[0].confidence >= SURE
    assert "Title matches" in found[0].reasons
    kai = next(guess for guess in found if guess.anime.id == 6033)
    assert kai.confidence < SURE
    assert "Only 97 episodes, files go up to 291" in kai.reasons


def test_a_nickname_finds_the_show():
    [group] = group_files([facts(r"D:\Anime\Downloads\[Group] DBZ - 001 [480p].MKV")])

    assert guesses(group, entries("dragon-ball-z"))[0].anime.id == 813


def test_a_film_file_matches_the_film_not_the_series():
    [group] = group_files(
        [facts(r"D:\Anime\Movies\Cowboy Bebop - The Movie (2001).mkv", minutes=115)]
    )

    best = guesses(group, entries("cowboy-bebop"))[0]

    assert best.anime.kind is TitleKind.MOVIE
    assert best.anime.id == 5


def test_the_wrong_year_counts_against_a_guess():
    right = group_files([facts(r"D:\Anime\Cowboy Bebop (1998)\Cowboy Bebop - 01.mkv")])[0]
    wrong = group_files([facts(r"D:\Anime\Cowboy Bebop (2021)\Cowboy Bebop - 01.mkv")])[0]
    bebop = entries("cowboy-bebop")

    assert guesses(right, bebop)[0].confidence > guesses(wrong, bebop)[0].confidence
    assert "From 1998, not 2021" in guesses(wrong, bebop)[0].reasons


def test_a_length_far_from_the_entrys_counts_against_it():
    short = group_files([facts(r"D:\Anime\Cowboy Bebop\Cowboy Bebop - 01.mkv", minutes=4)])[0]

    best = guesses(short, entries("cowboy-bebop"))[0]

    assert "4 min, not 24" in best.reasons


def test_one_episode_is_counted_as_one():
    files = [
        facts(f"D:/Anime/Cowboy Bebop - Yoseatsume Blues - 0{n}.mkv", number=n) for n in (1, 3)
    ]
    special = [entry for entry in entries("cowboy-bebop") if entry.id == 4037]

    one = guesses(group_files(files[:1])[0], special)[0]
    three = guesses(group_files(files)[0], special)[0]

    assert "1 episode fits" in one.reasons
    assert "Only 1 episode, files go up to 3" in three.reasons


def test_tmdb_has_attack_on_titans_later_parts_under_the_one_show():
    part_two = entries("attack-on-titan-season-3-part-2")[0]
    found = hits(
        tv_search(
            (1429, "Attack on Titan", date(2013, 4, 7)),
            (99999, "Attack on Titan: Junior High", date(2015, 10, 4)),
        ),
        "tv",
    )

    picked = pick_hit(part_two, found)

    assert picked is not None
    assert picked[0].id == 1429


def test_a_live_action_film_loses_to_the_anime_one():
    bebop_movie = next(e for e in entries("cowboy-bebop") if e.id == 5)
    found = hits(
        movie_search(
            (11299, "Cowboy Bebop: The Movie", date(2001, 9, 1)),
        ),
        "movie",
    )
    live_action = Hit(
        1, "movie", "Cowboy Bebop", "Cowboy Bebop", date(2021, 11, 19), False, False, 90
    )

    picked = pick_hit(bebop_movie, [live_action, *found])

    assert picked is not None
    assert picked[0].id == 11299


def test_nothing_alike_on_tmdb_is_no_pick():
    dbz = entries("dragon-ball-z")[0]
    found = hits(tv_search((1, "Sailor Moon", date(1992, 3, 7))), "tv")

    assert pick_hit(dbz, found) is None


def test_season_and_part_words_come_off_the_name():
    assert base_title("Attack on Titan Season 3 Part 2") == "Attack on Titan"
    assert base_title("Shingeki no Kyojin: The Final Season") == "Shingeki no Kyojin"
    assert base_title("Boku no Hero Academia 2nd Season") == "Boku no Hero Academia"
    assert base_title("Mob Psycho 100") == "Mob Psycho 100"
    assert base_title("Season 2") == "Season 2"  # nothing left: keep it as it was


def test_names_compare_without_case_punctuation_or_apostrophes():
    # A curly apostrophe, then a straight one.
    curly = f"Cowboy Bebop: Knockin{chr(0x2019)} on Heaven's Door"
    assert normalize(curly) == "cowboy bebop knockin on heavens door"
    assert similarity("Re:Zero", "Re Zero") == 1.0
    assert similarity("Bebop", "Cowboy Bebop") >= 0.45
    assert similarity("Dragon Ball Z", "Dragon Ball Z Kai") < 1.0
    assert similarity("", "Anything") == 0.0
