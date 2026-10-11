"""Which titles make one franchise: the ones AniList ties together by story."""

from kura.core.franchise import Link, franchises

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
