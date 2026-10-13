"""Which titles make one franchise: the ones AniList ties together by story."""

from collections.abc import Sequence
from datetime import date, timedelta

from kura.core.catalog import Episode, Show
from kura.core.franchise import (
    Entry,
    Kept,
    Link,
    franchises,
    missing,
    nearest,
    own_links,
    story_neighbours,
)

# AniList's numbers for a few Dragon Ball entries, and Cowboy Bebop's.
DRAGON_BALL, DBZ, GT, KAI, SUPER, BATTLE_OF_GODS = 223, 813, 225, 6033, 21175, 14837
BEBOP, BEBOP_MOVIE, ONE_PIECE = 1, 5, 21


def test_titles_tied_by_story_make_one_franchise():
    titles = {
        1: {DRAGON_BALL},
        2: {DBZ},
        3: {BATTLE_OF_GODS},
        4: {BEBOP},
        5: {BEBOP_MOVIE},
    }
    links = [
        Link(DBZ, DRAGON_BALL, "PREQUEL"),
        Link(BATTLE_OF_GODS, DBZ, "PARENT"),
        Link(BEBOP_MOVIE, BEBOP, "PARENT"),
    ]

    assert franchises(titles, links) == [[1, 2, 3], [4, 5]]


def test_a_crossover_ties_nothing_together():
    titles = {1: {DBZ}, 2: {ONE_PIECE}}

    assert franchises(titles, [Link(DBZ, ONE_PIECE, "CHARACTER")]) == [[1], [2]]


def test_an_entry_the_library_lacks_still_ties_its_neighbours():
    # Dragon Ball Z isn't in the library, but both GT and Kai say how they relate to it.
    titles = {1: {GT}, 2: {KAI}}
    links = [Link(GT, DBZ, "PREQUEL"), Link(KAI, DBZ, "ALTERNATIVE")]

    assert franchises(titles, links) == [[1, 2]]


def test_every_entry_a_title_holds_ties_it():
    # TMDB keeps Attack on Titan's third season under one show, which AniList splits in two parts;
    # only the second part says what comes after it.
    season_3, part_2, final_season = 99147, 104578, 110277
    titles = {1: {season_3, part_2}, 2: {final_season}}

    assert franchises(titles, [Link(part_2, final_season, "SEQUEL")]) == [[1, 2]]


def test_franchises_keep_the_order_of_their_first_titles():
    titles = {7: {BEBOP}, 3: {DBZ}, 9: {SUPER}}

    assert franchises(titles, [Link(SUPER, DBZ, "PREQUEL")]) == [[7], [3, 9]]


# The rest of a franchise: what AniList ties to the library's titles, and what the library lacks.
DEAD_ZONE, CURSE_OF_THE_BLOOD_RUBIES, KAI_FINAL = 894, 502, 20635
BARDOCK, TRUNKS = 986, 985


def entry(
    number: int,
    name: str,
    format_: str | None = "TV",
    start: date | None = None,
    episodes: int | None = None,
    status: str = "FINISHED",
    names: Sequence[str] = (),
) -> Entry:
    return Entry(number, name, (name, *names), format_, status, start, episodes, None)


def weekly(season: int, first: date, count: int, names: Sequence[str] = ()) -> list[Episode]:
    """A season airing once a week from `first`."""
    return [
        Episode(
            season, n, names[n - 1] if n <= len(names) else None, first + timedelta(weeks=n - 1), 24
        )
        for n in range(1, count + 1)
    ]


def show(*episodes: Episode) -> Show:
    return Show(1, "A show", "A show", episodes[0].aired, False, None, episodes)


def test_the_rest_of_a_franchise_is_what_its_story_ties_to_the_library():
    links = [
        Link(DBZ, DRAGON_BALL, "PREQUEL"),
        Link(DBZ, DEAD_ZONE, "SIDE_STORY"),
        Link(DBZ, ONE_PIECE, "CHARACTER"),  # a crossover ties nothing
        Link(CURSE_OF_THE_BLOOD_RUBIES, DRAGON_BALL, "PARENT"),  # known from the film's side
    ]

    assert nearest({DBZ}, story_neighbours(links)) == [
        DBZ,
        DRAGON_BALL,
        DEAD_ZONE,
        CURSE_OF_THE_BLOOD_RUBIES,
    ]


def test_the_rest_of_a_franchise_stops_at_its_limit():
    neighbours = story_neighbours([Link(n, n + 1, "SEQUEL") for n in range(1, 10)])

    assert nearest({1}, neighbours, limit=3) == [1, 2, 3]
    assert nearest({5, 1}, neighbours, limit=1) == [1]


def test_the_rest_of_a_franchise_stops_at_another_franchise_the_library_has():
    # A crossover AniList ties to both by story: it's in Cowboy Bebop's reach, One Piece isn't.
    crossover = 999
    neighbours = story_neighbours(
        [Link(BEBOP, crossover, "SPIN_OFF"), Link(crossover, ONE_PIECE, "PARENT")]
    )

    assert nearest({BEBOP}, neighbours, others={ONE_PIECE}) == [BEBOP, crossover]


def test_franchises_are_tied_by_the_librarys_own_links_only():
    # What Kura looked up past the library (a crossover's links) ties nothing of it together.
    crossover = 999
    links = [
        Link(BEBOP, BEBOP_MOVIE, "SIDE_STORY"),
        Link(BEBOP, crossover, "SPIN_OFF"),
        Link(crossover, ONE_PIECE, "PARENT"),
    ]
    titles = {1: {BEBOP}, 2: {BEBOP_MOVIE}, 3: {ONE_PIECE}}

    assert franchises(titles, own_links(links, {BEBOP, BEBOP_MOVIE, ONE_PIECE})) == [[1, 2], [3]]


def test_missing_is_what_the_library_has_no_part_of_oldest_release_first():
    entries = [
        entry(DBZ, "Dragon Ball Z", start=date(1989, 4, 26)),
        entry(DEAD_ZONE, "Dragon Ball Z: Dead Zone", "MOVIE", date(1989, 7, 15), 1),
        entry(DRAGON_BALL, "Dragon Ball", start=date(1986, 2, 26)),
        entry(2, "Dragon Ball Super: Ginga Patrol", None, status="NOT_YET_RELEASED"),  # no kind yet
        entry(3, "Cha-La Head-Cha-La", "MUSIC", date(1989, 5, 3)),
        entry(4, "A film that never came", "MOVIE", status="CANCELLED"),
        entry(5, "Dragon Ball: Undated", "SPECIAL"),
    ]

    found = missing(entries, {DBZ}, [], [])

    assert [e.name for e in found] == [
        "Dragon Ball",
        "Dragon Ball Z: Dead Zone",
        "Dragon Ball: Undated",  # undated last
    ]


def test_a_later_part_tmdb_keeps_as_a_shows_season_counts_once_the_library_has_some_of_it():
    # TMDB keeps Kai's final chapters as its later seasons; AniList has them as an entry of
    # their own, their files matched to Kai's.
    kai = show(*weekly(1, date(2009, 4, 5), 3), *weekly(2, date(2014, 4, 6), 3))
    final = entry(
        KAI_FINAL, "Dragon Ball Z Kai: The Final Chapters", start=date(2014, 4, 6), episodes=3
    )
    links = [Link(KAI_FINAL, KAI, "PREQUEL")]

    held_some = Kept(frozenset({KAI}), kai, frozenset({(1, 1), (2, 2)}))
    held_none = Kept(frozenset({KAI}), kai, frozenset({(1, 1), (1, 2), (1, 3)}))

    assert missing([final], {KAI}, [held_some], links) == []
    assert missing([final], {KAI}, [held_none], links) == [final]


def test_a_series_that_aired_alongside_a_show_isnt_held_by_it():
    # A spin-off that started the week a long show aired an episode: another telling.
    long_show = show(*weekly(1, date(2014, 1, 4), 52))
    spin_off = entry(7, "Magic Kaito 1412", start=date(2014, 10, 4), episodes=24)
    every_episode = frozenset((1, n) for n in range(1, 53))
    links = [Link(7, 8, "SPIN_OFF")]

    assert missing([spin_off], {8}, [Kept(frozenset({8}), long_show, every_episode)], links) == [
        spin_off
    ]


def test_a_special_among_a_shows_specials_counts_once_the_library_has_it():
    dbz = show(
        *weekly(1, date(1989, 4, 26), 2),
        Episode(0, 1, "Bardock - The Father of Goku", date(1990, 10, 17), 48),
        Episode(0, 2, "The History of Trunks", date(1993, 2, 24), 48),
    )
    bardock = entry(
        BARDOCK, "Dragon Ball Z: Bardock - The Father of Goku", "SPECIAL", date(1990, 10, 17), 1
    )
    trunks = entry(TRUNKS, "Dragon Ball Z: The History of Trunks", "SPECIAL", date(1993, 2, 24), 1)
    undated = entry(TRUNKS, "Dragon Ball Z: The History of Trunks", "SPECIAL")  # by its name, then

    kept = [Kept(frozenset({DBZ}), dbz, frozenset({(1, 1), (0, 1)}))]
    assert missing([bardock, trunks], {DBZ}, kept, []) == [trunks]

    kept = [Kept(frozenset({DBZ}), dbz, frozenset({(0, 2)}))]
    assert missing([bardock, undated], {DBZ}, kept, []) == [bardock]


def test_an_ova_dated_weeks_apart_by_anilist_and_tmdb_counts_once_the_library_has_a_part():
    # AniList dates the OVA's release, TMDB its first showing; a remake years later is named
    # alike but isn't the same one.
    dbz = show(
        *weekly(1, date(1989, 4, 26), 2),
        Episode(0, 5, "Plan to Eradicate the Saiyans (1)", date(1993, 8, 6), 30),
        Episode(0, 6, "Plan to Eradicate the Saiyans (2)", date(1993, 8, 6), 30),
        Episode(0, 9, "Plan to Eradicate the Super Saiyans", date(2010, 11, 11), 30),
    )
    ova = entry(984, "Dragon Ball Z: Plan to Eradicate the Saiyans", "OVA", date(1993, 7, 23), 2)
    remake = entry(
        10017, "Dragon Ball: Plan to Eradicate the Super Saiyans", "OVA", date(2010, 11, 11), 1
    )

    kept = [Kept(frozenset({DBZ}), dbz, frozenset({(0, 6)}))]
    assert missing([ova, remake], {DBZ}, kept, []) == [remake]

    kept = [Kept(frozenset({DBZ}), dbz, frozenset({(0, 9)}))]
    assert missing([ova, remake], {DBZ}, kept, []) == [ova]


def test_specials_its_other_names_name_count_once_the_library_has_them():
    dragon_ball = show(
        *weekly(1, date(1986, 2, 26), 2),
        Episode(0, 1, "Goku's Fire Brigade", date(1988, 6, 8), 12),
        Episode(0, 2, "Goku's Traffic Safety", date(1988, 6, 8), 12),
    )
    specials = entry(
        2520,
        "Dragon Ball Specials",
        "SPECIAL",
        names=("Dragon Ball: Goku's Traffic Safety", "Dragon Ball: Goku's Fire Brigade"),
    )

    kept = [Kept(frozenset({DRAGON_BALL}), dragon_ball, frozenset({(0, 2)}))]
    assert missing([specials], {DRAGON_BALL}, kept, []) == []


def test_a_film_isnt_held_by_a_special_shown_a_fortnight_from_its_premiere():
    dbz = show(*weekly(1, date(1989, 4, 26), 2), Episode(0, 1, "A Special", date(1993, 7, 24), 45))
    film = entry(902, "Dragon Ball Z: Bojack Unbound", "MOVIE", date(1993, 7, 10), 1)

    kept = [Kept(frozenset({DBZ}), dbz, frozenset({(0, 1)}))]
    assert missing([film], {DBZ}, kept, []) == [film]


def test_of_two_specials_out_the_same_day_their_names_say_which_is_which():
    show_ = show(
        *weekly(1, date(2005, 1, 5), 2),
        Episode(0, 1, "The Lost Island", date(2005, 8, 1), 30),
        Episode(0, 2, "Return of the Captain", date(2005, 8, 1), 30),
    )
    lost = entry(11, "A Show: The Lost Island", "OVA", date(2005, 8, 1), 1)
    captain = entry(12, "A Show: Return of the Captain", "OVA", date(2005, 8, 1), 1)

    kept = [Kept(frozenset({10}), show_, frozenset({(0, 1)}))]
    assert missing([lost, captain], {10}, kept, []) == [captain]


def test_an_ova_out_a_week_from_a_special_the_library_has_isnt_held_by_it():
    # TMDB doesn't list the OVA at all; the special the week before is another one.
    show_ = show(*weekly(1, date(2005, 1, 5), 2), Episode(0, 1, "A Recap", date(2005, 8, 1), 30))
    ova = entry(13, "A Show: Something Else", "OVA", date(2005, 8, 8), 1)

    assert missing([ova], {10}, [Kept(frozenset({10}), show_, frozenset({(0, 1)}))], []) == [ova]
