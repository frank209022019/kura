"""The TMDB key through the API: checked with TMDB before Kura keeps it."""

from fastapi.testclient import TestClient

from kura import credentials
from kura.config import DataPaths
from kura.tmdb import API
from tests.fake_web import FakeWeb, reply

KEY = "kura-test-token.a-read-access-token.signature"


def test_without_a_key_kura_says_so(client: TestClient):
    answer = client.get("/tmdb")

    assert answer.status_code == 200
    assert answer.json() == {"connected": False, "keyEnd": None}


def test_a_key_tmdb_accepts_is_kept(client: TestClient, web: FakeWeb, paths: DataPaths):
    web.answers[f"GET {API}/authentication"] = {"success": True}

    answer = client.put("/tmdb", json={"key": f"  {KEY}  "})

    assert answer.status_code == 200
    assert answer.json() == {"connected": True, "keyEnd": "ture"}
    assert credentials.load(paths, "tmdb") == KEY
    assert web.asked[0].headers["Authorization"] == f"Bearer {KEY}"


def test_a_key_tmdb_refuses_isnt_kept(client: TestClient, web: FakeWeb, paths: DataPaths):
    web.answers[f"GET {API}/authentication"] = reply(
        {"status_code": 7, "status_message": "Invalid API key: You must be granted a valid key."},
        401,
    )

    answer = client.put("/tmdb", json={"key": "not-a-key"})

    assert answer.status_code == 400
    assert answer.json()["detail"] == (
        "TMDB didn't accept this key. Copy the API Read Access Token from your TMDB account "
        "(themoviedb.org, Settings, API), then paste it here."
    )
    assert credentials.load(paths, "tmdb") is None


def test_offline_the_key_waits_until_it_can_be_checked(
    client: TestClient, web: FakeWeb, paths: DataPaths
):
    web.offline = True

    answer = client.put("/tmdb", json={"key": KEY})

    assert answer.status_code == 503
    assert answer.json()["detail"].endswith(
        "The key isn't saved yet: try again when you're online."
    )
    assert credentials.load(paths, "tmdb") is None


def test_an_empty_key_says_where_to_find_one(client: TestClient, web: FakeWeb):
    answer = client.put("/tmdb", json={"key": "   "})

    assert answer.status_code == 400
    assert "API Read Access Token" in answer.json()["detail"]
    assert web.asked == []


def test_a_key_can_be_removed(client: TestClient, paths: DataPaths):
    credentials.save(paths, "tmdb", KEY)

    answer = client.delete("/tmdb")

    assert answer.json() == {"connected": False, "keyEnd": None}
    assert credentials.load(paths, "tmdb") is None
