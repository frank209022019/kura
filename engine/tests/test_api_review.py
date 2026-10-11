"""Files waiting for a match: the owner's choice, pinned, and "not anime"."""

import json
import sqlite3
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from kura import credentials
from kura.anilist import API as ANILIST
from kura.config import DataPaths
from tests.fake_web import Asked, FakeWeb
from tests.services import SAVED, internet
from tests.shelf import identify, library

COWBOY_BEBOP = json.loads((SAVED / "cowboy-bebop.json").read_text(encoding="utf-8"))
SERIES = next(m for m in COWBOY_BEBOP["data"]["Page"]["media"] if m["id"] == 1)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "Anime"


@pytest.fixture
def waiting(paths: DataPaths, conn: sqlite3.Connection, root: Path, web: FakeWeb) -> FakeWeb:
    """Four [subs] episodes in Downloads that Kura couldn't name, as on the design's board."""
    library(conn, root, [f"Downloads/[subs] ep0{n} final.mkv" for n in (3, 4, 5, 6)])
    identify(paths, conn, internet())
    stood_in = internet()
    web.answers.update(stood_in.answers)
    return web


def test_the_files_kura_couldnt_name_wait_with_their_facts(client: TestClient, waiting: FakeWeb):
    found = client.get("/review").json()

    assert [f["episode"] for f in found] == [3, 4, 5, 6]
    first = found[0]
    assert (first["group"], first["kind"], first["height"], first["codec"]) == (
        "subs",
        "episode",
        540,
        "hevc",
    )
    assert first["audio"] == ["jpn"]
    assert len(first["alike"]) == 3  # the other [subs] files beside it


def test_searching_anilist_scores_its_entries_against_the_file(
    client: TestClient, waiting: FakeWeb
):
    [first, *_] = client.get("/review").json()

    found = client.get(f"/review/{first['id']}/search", params={"q": "Cowboy Bebop"}).json()

    assert found[0]["anilistId"] == 1
    assert found[0]["title"] == "Cowboy Bebop"
    assert 0 <= found[0]["confidence"] <= 100


def test_the_owners_choice_places_the_files_and_sticks(
    client: TestClient, waiting: FakeWeb, paths: DataPaths, conn: sqlite3.Connection
):
    credentials.save(paths, "tmdb", "a-test-key")
    waiting.answers[f"POST {ANILIST}"] = lambda asked: _entry_or_search(asked)
    [first, *_] = client.get("/review").json()

    answer = client.post(
        f"/review/{first['id']}", json={"anilistId": 1, "kind": "episode", "also": first["alike"]}
    )

    assert answer.json() == {"placed": 4}
    rows = conn.execute(
        "SELECT episode, season, matched, pinned FROM files ORDER BY episode"
    ).fetchall()
    assert [tuple(row) for row in rows] == [(n, 1, "sure", 1) for n in (3, 4, 5, 6)]
    assert client.get("/review").json() == []

    identify(paths, conn, internet())  # a rescan
    assert conn.execute("SELECT COUNT(*) FROM files WHERE pinned = 1").fetchone()[0] == 4


def test_not_anime_is_left_out_for_good(
    client: TestClient, waiting: FakeWeb, conn: sqlite3.Connection
):
    [first, *_] = client.get("/review").json()

    assert client.post(f"/review/{first['id']}/ignore").status_code == 204

    assert len(client.get("/review").json()) == 3
    row = conn.execute("SELECT matched, pinned FROM files WHERE id = ?", (first["id"],)).fetchone()
    assert tuple(row) == ("ignored", 1)


def test_offline_a_choice_changes_nothing_and_says_so(
    client: TestClient, waiting: FakeWeb, conn: sqlite3.Connection
):
    [first, *_] = client.get("/review").json()
    waiting.offline = True

    answer = client.post(f"/review/{first['id']}", json={"anilistId": 1})

    assert answer.status_code == 503
    assert answer.json()["detail"].endswith("Nothing was changed; try again in a moment.")
    assert conn.execute("SELECT COUNT(*) FROM files WHERE pinned = 1").fetchone()[0] == 0


def _entry_or_search(asked: Asked) -> object:
    variables = cast("dict[str, object]", asked.payload["variables"])
    if variables.get("id") == 1:
        return {"data": {"Media": SERIES}}
    return COWBOY_BEBOP
