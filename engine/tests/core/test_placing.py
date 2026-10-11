"""Where a file sits in a TMDB show: numbered by season, counted straight through, or by date."""

import json
from datetime import date
from pathlib import Path, PureWindowsPath

from kura.core.catalog import Anime, Show, anime_list, show
from kura.core.names import parse_name
from kura.core.placing import How, Placement, place
from tests.tmdb_data import DBZ_SEASONS, tv_details

ANILIST = Path(__file__).parent.parent / "data" / "anilist"


def tmdb_show(details: dict[str, object]) -> Show:
    found = show(details)
    assert found is not None
    return found


DBZ = tmdb_show(tv_details(12971, "Dragon Ball Z", DBZ_SEASONS, first_aired=date(1989, 4, 26)))

# Attack on Titan as TMDB has it: season 3 holds both of AniList's parts, the second starting
# with episode 13 on 29 April 2019.
TITAN = tmdb_show(
    tv_details(
        1429,
        "Attack on Titan",
        (25, 12, 22, 30),
        first_aired=date(2013, 4, 7),
        aired={
            (2, 1): date(2017, 4, 1),
            (3, 1): date(2018, 7, 23),
            (3, 13): date(2019, 4, 29),
            (4, 1): date(2020, 12, 7),
        },
    )
)

# Cowboy Bebop with its specials in season 0; the second first aired on 26 June 1998.
BEBOP = tmdb_show(
    tv_details(
        30991,
        "Cowboy Bebop",
        (26,),
        first_aired=date(1998, 4, 3),
        specials=3,
        special_dates=(date(1998, 4, 3), date(1998, 6, 26), date(2012, 12, 21)),
    )
)


def anilist(name: str, anime_id: int) -> Anime:
    found = anime_list(json.loads((ANILIST / f"{name}.json").read_text(encoding="utf-8")))
    return next(entry for entry in found if entry.id == anime_id)


def placed(path: str, where: Show, entry: Anime | None = None) -> Placement | None:
    return place(parse_name(PureWindowsPath(path)), where, entry)


def test_a_number_counted_straight_through_finds_its_season():
    # 39 + 35 + 33 + 32 = 139 episodes in seasons 1 to 4: episode 150 is season 5's eleventh.
    assert placed(r"D:\Anime\Dragon Ball Z\Dragon Ball Z - 150.mkv", DBZ) == Placement(
        5, 11, None, How.STRAIGHT
    )
    assert placed(r"D:\Anime\[Group] DBZ - 001 [480p].mkv", DBZ) == Placement(
        1, 1, None, How.STRAIGHT
    )
    assert placed(r"D:\Anime\Dragon Ball Z\Dragon Ball Z - 291.mkv", DBZ) == Placement(
        9, 38, None, How.STRAIGHT
    )


def test_a_number_past_the_last_episode_isnt_placed():
    assert placed(r"D:\Anime\Dragon Ball Z\Dragon Ball Z - 292.mkv", DBZ) is None


def test_a_season_and_episode_are_taken_as_they_are():
    assert placed(r"D:\Anime\Dragon Ball Z - S04E05 - Title.mkv", DBZ) == Placement(
        4, 5, None, How.NUMBERED
    )
    assert placed(r"D:\Anime\Dragon Ball Z\Season 04\05.mkv", DBZ) == Placement(
        4, 5, None, How.NUMBERED
    )


def test_a_season_with_numbers_counted_through_the_show():
    # HorribleSubs numbered Attack on Titan's third season on from the second: 38 to 59.
    found = placed(r"D:\Anime\[HorribleSubs] Shingeki no Kyojin S3 - 49 [720p].mkv", TITAN)

    assert found == Placement(3, 12, None, How.STRAIGHT)


def test_a_later_part_numbered_from_one_again_is_placed_by_its_first_air_date():
    part_two = anilist("attack-on-titan-season-3-part-2", 104578)

    found = placed(
        r"D:\Anime\[SubsPlease] Shingeki no Kyojin S3 Part 2 - 03 (1080p).mkv", TITAN, part_two
    )

    assert found == Placement(3, 15, None, How.BY_DATE)


def test_the_first_entry_of_a_show_doesnt_shift_its_numbers():
    dbz = anilist("dragon-ball-z", 813)  # starts with the show's first episode

    found = placed(r"D:\Anime\Dragon Ball Z\Dragon Ball Z - S04E05.mkv", DBZ, dbz)

    assert found == Placement(4, 5, None, How.NUMBERED)


def test_two_episodes_in_one_file_stay_in_one_season():
    assert placed(r"D:\Anime\Dragon Ball Z - 001-002.mkv", DBZ) == Placement(1, 1, 2, How.STRAIGHT)
    # 39 and 40 straddle seasons 1 and 2: only the first is placed.
    assert placed(r"D:\Anime\Dragon Ball Z - 039-040.mkv", DBZ) == Placement(
        1, 39, None, How.STRAIGHT
    )


def test_a_special_goes_to_season_zero_by_the_date_it_first_aired():
    yoseatsume = anilist("cowboy-bebop", 4037)  # first aired 26 June 1998

    found = placed(r"D:\Anime\Cowboy Bebop\Cowboy Bebop - OVA.mkv", BEBOP, yoseatsume)

    assert found == Placement(0, 2, None, How.BY_DATE)


def test_a_special_already_numbered_keeps_its_number():
    found = placed(r"D:\Anime\Cowboy Bebop\Specials\Cowboy Bebop - 03.mkv", BEBOP)

    assert found == Placement(0, 3, None, How.NUMBERED)


def test_a_special_kura_cant_date_or_number_isnt_placed():
    assert placed(r"D:\Anime\Cowboy Bebop\Cowboy Bebop - OVA.mkv", BEBOP) is None
    assert placed(r"D:\Anime\Dragon Ball Z\Specials\Dragon Ball Z - 01.mkv", DBZ) is None


def test_films_and_extras_arent_episodes():
    assert placed(r"D:\Anime\Cowboy Bebop - The Movie (2001).mkv", BEBOP) is None
    assert placed(r"D:\Anime\Cowboy Bebop\Extras\NCOP01.mkv", BEBOP) is None
