"""Asking TMDB: the key, searches, whole shows with every season, films and posters."""

from datetime import date

import pytest

from kura.tmdb import API, IMAGES, Tmdb
from kura.web import Reply, WebError
from tests.fake_web import Asked, FakeWeb, reply
from tests.tmdb_data import DBZ_SEASONS, movie_details, tv_details, tv_search

TOKEN = "kura-test-token.a-read-access-token.signature"
V3_KEY = "0123456789abcdef0123456789abcdef"


def test_a_read_access_token_goes_in_the_header():
    web = FakeWeb({f"GET {API}/authentication": {"success": True}})

    Tmdb(TOKEN, web).check()

    assert web.asked[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert "api_key" not in web.asked[0].query


def test_an_api_key_goes_in_the_address():
    web = FakeWeb({f"GET {API}/authentication": {"success": True}})

    Tmdb(f"  {V3_KEY}\n", web).check()  # pasted with spaces around it

    assert web.asked[0].query["api_key"] == V3_KEY
    assert "Authorization" not in web.asked[0].headers


def test_a_key_tmdb_refuses_says_so():
    refused = reply(
        {"status_code": 7, "status_message": "Invalid API key: You must be granted a valid key."},
        401,
    )
    web = FakeWeb({f"GET {API}/authentication": refused})

    with pytest.raises(WebError) as raised:
        Tmdb("wrong", web).check()

    assert raised.value.status == 401
    assert "didn't accept the key" in str(raised.value)


def test_a_search_for_shows_can_name_the_year():
    web = FakeWeb({f"GET {API}/search/tv": tv_search((12971, "Dragon Ball Z", date(1989, 4, 26)))})

    found = Tmdb(TOKEN, web).search("tv", "Dragon Ball Z", 1989)

    assert [hit.id for hit in found] == [12971]
    assert web.asked[0].query == {
        "query": "Dragon Ball Z",
        "include_adult": "false",
        "first_air_date_year": "1989",
    }


def test_a_film_search_uses_the_release_year():
    web = FakeWeb({f"GET {API}/search/movie": {"results": []}})

    Tmdb(TOKEN, web).search("movie", "Cowboy Bebop: The Movie", 2001)

    assert web.asked[0].query["primary_release_year"] == "2001"


def test_a_show_comes_with_every_season_even_past_twenty():
    seasons = (24,) * 22  # a long show, such as One Piece
    full = tv_details(37854, "One Piece", seasons, first_aired=date(1999, 10, 20), specials=3)

    def details(asked: Asked) -> object:
        wanted = asked.query.get("append_to_response")
        if wanted is None:
            return {key: value for key, value in full.items() if not key.startswith("season/")}
        return {**{"id": 37854}, **{key: full[key] for key in wanted.split(",")}}

    web = FakeWeb({f"GET {API}/tv/37854": details})

    one_piece = Tmdb(TOKEN, web).show(37854)

    assert one_piece is not None
    assert one_piece.seasons == tuple(range(1, 23))
    assert len(one_piece.season(0)) == 3
    assert len(one_piece.episodes) == 22 * 24 + 3
    assert len(web.asked) == 3  # the show, then seasons 0-19, then 20-22


def test_a_show_tmdb_no_longer_has_is_none():
    web = FakeWeb()  # every address answers 404

    assert Tmdb(TOKEN, web).show(1) is None
    assert Tmdb(TOKEN, web).film(1) is None


def test_a_film():
    web = FakeWeb(
        {
            f"GET {API}/movie/11299": movie_details(
                11299, "Cowboy Bebop: The Movie", date(2001, 9, 1), 115
            )
        }
    )

    bebop = Tmdb(TOKEN, web).film(11299)

    assert bebop is not None
    assert bebop.title == "Cowboy Bebop: The Movie"


def test_a_poster_comes_from_the_image_server():
    web = FakeWeb({f"GET {IMAGES}/w342/poster-12971.jpg": Reply(200, {}, b"jpeg bytes")})
    dbz = tv_details(12971, "Dragon Ball Z", DBZ_SEASONS, first_aired=date(1989, 4, 26))

    assert Tmdb(TOKEN, web).poster(str(dbz["poster_path"])) == b"jpeg bytes"
