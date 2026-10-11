"""The library's titles, their gaps and posters through the API, and the reports next to them."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kura import credentials
from kura.config import DataPaths
from kura.core.report import GAP_ANALYSIS_FILE
from kura.reports import own_folder, write_reports
from kura.web import Reply
from tests.fake_web import FakeWeb
from tests.services import internet
from tests.shelf import NOW, identify, library

DBZ = [f"Dragon Ball Z (1989)/Dragon Ball Z - {n:03}.mkv" for n in range(1, 292) if n != 150]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "Anime"


@pytest.fixture
def identified(paths: DataPaths, conn: sqlite3.Connection, root: Path) -> sqlite3.Connection:
    """Dragon Ball Z without episode 150, Cowboy Bebop's first episode, and its film."""
    credentials.save(paths, "tmdb", "a-test-key")
    library(conn, root, [*DBZ, "Cowboy Bebop/Cowboy Bebop - 01.mkv"])
    library(conn, root, ["Movies/Cowboy Bebop - The Movie (2001).mkv"], minutes=115)
    identify(paths, conn, internet())
    return conn


def test_titles_list_oldest_release_first(client: TestClient, identified: sqlite3.Connection):
    found = client.get("/titles").json()

    assert [(t["name"], t["kind"], t["released"]) for t in found] == [
        ("Dragon Ball Z", "series", "1989-04-26"),
        ("Cowboy Bebop", "series", "1998-04-03"),
        ("Cowboy Bebop: The Movie", "movie", "2001-09-01"),
    ]


def test_titles_sort_by_name_too(client: TestClient, identified: sqlite3.Connection):
    found = client.get("/titles", params={"sort": "name"}).json()

    assert [t["name"] for t in found] == [
        "Cowboy Bebop",
        "Cowboy Bebop: The Movie",
        "Dragon Ball Z",
    ]


def test_a_title_says_how_much_of_it_is_there(client: TestClient, identified: sqlite3.Connection):
    dbz = next(t for t in client.get("/titles").json() if t["name"] == "Dragon Ball Z")

    assert (dbz["files"], dbz["aired"], dbz["present"], dbz["missing"]) == (290, 291, 290, 1)
    assert dbz["specialsMissing"] == 0
    assert dbz["hasPoster"] is True


def test_one_title_lists_its_seasons_and_the_episode_it_lacks(
    client: TestClient, identified: sqlite3.Connection
):
    [dbz_id] = [t["id"] for t in client.get("/titles").json() if t["name"] == "Dragon Ball Z"]

    detail = client.get(f"/titles/{dbz_id}").json()

    assert detail["seasons"][4] == {"season": 5, "present": 25, "aired": 26, "total": 26}
    assert detail["missingEpisodes"] == [
        {"season": 5, "number": 11, "name": "Episode 11", "aired": "1992-03-04"}
    ]
    assert len(detail["videos"]) == 290


def test_an_unknown_title_is_404(client: TestClient, conn: sqlite3.Connection):
    assert client.get("/titles/999").status_code == 404


def test_a_poster_is_fetched_once_then_kept(
    client: TestClient, identified: sqlite3.Connection, web: FakeWeb
):
    [movie_id] = [t["id"] for t in client.get("/titles").json() if t["kind"] == "movie"]
    web.answers["GET https://image.tmdb.org/t/p/w342/poster-movie-11299.jpg"] = Reply(
        200, {}, b"jpeg bytes"
    )

    first = client.get(f"/titles/{movie_id}/poster")
    again = client.get(f"/titles/{movie_id}/poster")

    assert (first.status_code, first.content, first.headers["content-type"]) == (
        200,
        b"jpeg bytes",
        "image/jpeg",
    )
    assert again.content == b"jpeg bytes"
    assert web.paths().count("GET https://image.tmdb.org/t/p/w342/poster-movie-11299.jpg") == 1


def test_a_poster_that_cant_be_fetched_is_404(client: TestClient, identified: sqlite3.Connection):
    [movie_id] = [t["id"] for t in client.get("/titles").json() if t["kind"] == "movie"]

    assert client.get(f"/titles/{movie_id}/poster").status_code == 404  # nothing answers


def test_a_report_goes_next_to_a_show_with_a_folder_of_its_own(
    identified: sqlite3.Connection, root: Path
):
    written = write_reports(identified, now=NOW)

    report = (root / "Dragon Ball Z (1989)" / GAP_ANALYSIS_FILE).read_text(encoding="utf-8")
    assert report.startswith("# Dragon Ball Z (1989) — gap analysis\n")
    assert "- Present: **290 of 291** episodes (100%)" in report
    assert "| S05E11  | 150      | Season 05 |" in report
    assert (root / "Cowboy Bebop" / GAP_ANALYSIS_FILE).exists()
    assert written.reports == 2
    assert written.problems == ()


def test_no_report_goes_into_a_library_folder_or_a_shared_one(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    library(conn, root, ["Dragon Ball Z - 001.mkv", "Mixed/Dragon Ball Z - 002.mkv"])
    library(conn, root, ["Mixed/Cowboy Bebop - 01.mkv"])
    identify(paths, conn, internet())
    roots = [root]

    ids = {row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM titles")}

    assert own_folder(conn, ids["Dragon Ball Z"], roots) is None  # spread over two folders
    assert own_folder(conn, ids["Cowboy Bebop"], roots) is None  # shares Mixed with DBZ
    assert write_reports(conn, now=NOW).reports == 0
    assert not list(root.rglob(GAP_ANALYSIS_FILE))


def test_an_unchanged_report_isnt_written_again(identified: sqlite3.Connection, root: Path):
    write_reports(identified, now=NOW)
    report = root / "Dragon Ball Z (1989)" / GAP_ANALYSIS_FILE
    before = report.stat().st_mtime_ns

    again = write_reports(identified, now=NOW.replace(hour=11))

    assert again.reports == 0
    assert report.stat().st_mtime_ns == before
