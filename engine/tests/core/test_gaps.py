"""Missing episodes: what TMDB lists as aired that the library doesn't hold."""

from datetime import date

from kura.core.catalog import Episode, Show, show
from kura.core.gaps import SeasonCount, find_gaps
from tests.tmdb_data import DBZ_SEASONS, tv_details

TODAY = date(2026, 10, 11)


def tmdb_show(details: dict[str, object]) -> Show:
    found = show(details)
    assert found is not None
    return found


DBZ = tmdb_show(
    tv_details(12971, "Dragon Ball Z", DBZ_SEASONS, first_aired=date(1989, 4, 26), specials=2)
)


def every_episode_but(*left_out: tuple[int, int]) -> list[tuple[int, int, int | None]]:
    return [
        (season, number, None)
        for season, size in enumerate(DBZ_SEASONS, start=1)
        for number in range(1, size + 1)
        if (season, number) not in left_out
    ]


def test_episodes_the_library_lacks_are_missing():
    # The title board's Dragon Ball Z: 287 of 291, missing S04E11, S04E12, S07E13 and S09E01.
    gaps = find_gaps(DBZ, every_episode_but((4, 11), (4, 12), (7, 13), (9, 1)), TODAY)

    assert [(e.season, e.number) for e in gaps.missing] == [(4, 11), (4, 12), (7, 13), (9, 1)]
    assert (gaps.present, gaps.aired) == (287, 291)
    assert gaps.seasons[3] == SeasonCount(4, 30, 32, 32)


def test_specials_are_listed_apart_and_never_count_as_missing():
    gaps = find_gaps(DBZ, every_episode_but(), TODAY)

    assert gaps.missing == ()
    assert [(e.season, e.number) for e in gaps.specials_missing] == [(0, 1), (0, 2)]


def test_a_file_with_two_episodes_covers_both():
    held = [*every_episode_but((1, 1), (1, 2)), (1, 1, 2)]

    assert find_gaps(DBZ, held, TODAY).missing == ()


def test_episodes_still_to_air_arent_missing():
    # Weekly from 6 September: episode 6 airs today, so 7 to 10 are still to come.
    airing = tmdb_show(
        tv_details(
            37854, "One Piece", (10,), first_aired=date(2026, 9, 6), status="Returning Series"
        )
    )

    gaps = find_gaps(airing, [(1, 1, None), (1, 2, None)], TODAY)

    assert [e.number for e in gaps.missing] == [3, 4, 5, 6]
    assert [e.number for e in gaps.upcoming] == [7, 8, 9, 10]
    assert gaps.seasons == (SeasonCount(1, 2, 6, 10),)


def test_a_finished_shows_undated_episodes_still_count():
    undated = tuple(Episode(1, number, None, None, 24) for number in (1, 2, 3))
    old = Show(1, "Old Show", "Old Show", date(1980, 1, 1), False, None, undated)

    assert len(find_gaps(old, [], TODAY).missing) == 3


def test_an_airing_shows_undated_episodes_are_still_to_come():
    undated = tuple(Episode(1, number, None, None, 24) for number in (1, 2))
    airing = Show(2, "New Show", "New Show", None, True, None, undated)

    gaps = find_gaps(airing, [], TODAY)

    assert gaps.missing == ()
    assert len(gaps.upcoming) == 2
