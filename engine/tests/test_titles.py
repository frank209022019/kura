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


def test_a_franchise_gathers_what_anilist_ties_together(
    client: TestClient, identified: sqlite3.Connection
):
    found = client.get("/franchises").json()

    assert [(f["name"], [t["name"] for t in f["titles"]]) for f in found] == [
        ("Dragon Ball Z", ["Dragon Ball Z"]),
        ("Cowboy Bebop", ["Cowboy Bebop", "Cowboy Bebop: The Movie"]),
    ]
    bebop = found[1]
    assert bebop["id"] == bebop["titles"][0]["id"]  # led by its first series
    assert bebop["kinds"] == {"series": 1, "movie": 1, "ova": 0, "special": 0}
    assert (bebop["released"], bebop["files"], bebop["aired"], bebop["present"]) == (
        "1998-04-03",
        2,
        26,
        1,
    )
    assert bebop["missing"] == 25


def test_franchises_sort_like_titles(client: TestClient, identified: sqlite3.Connection):
    found = client.get("/franchises", params={"sort": "missing"}).json()

    assert [f["name"] for f in found] == ["Cowboy Bebop", "Dragon Ball Z"]


def test_a_franchise_lists_its_titles_and_a_title_names_its_franchise(
    client: TestClient, identified: sqlite3.Connection
):
    ids = {t["name"]: t["id"] for t in client.get("/titles").json()}

    franchise = client.get(f"/franchises/{ids['Cowboy Bebop: The Movie']}", params={"sort": "name"})

    assert franchise.json()["name"] == "Cowboy Bebop"
    assert [t["name"] for t in franchise.json()["titles"]] == [
        "Cowboy Bebop",
        "Cowboy Bebop: The Movie",
    ]
    movie = client.get(f"/titles/{ids['Cowboy Bebop: The Movie']}").json()
    assert movie["franchise"] == {"id": ids["Cowboy Bebop"], "name": "Cowboy Bebop"}
    assert client.get(f"/titles/{ids['Dragon Ball Z']}").json()["franchise"] is None
    assert client.get("/franchises/999").status_code == 404


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
    assert "- Present: **290 of 291** episodes (99%)" in report
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


def test_season_folders_named_any_way_belong_to_their_show(
    paths: DataPaths, conn: sqlite3.Connection, root: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    library(
        conn,
        root,
        [
            "Dragon Ball Z (1989)/S01/Dragon Ball Z - 001.mkv",
            "Dragon Ball Z (1989)/Season_02/Dragon Ball Z - 040.mkv",
            "Dragon Ball Z (1989)/Season03/Dragon Ball Z - 075.mkv",
        ],
    )
    identify(paths, conn, internet())

    assert write_reports(conn, now=NOW).reports == 1
    assert [p.relative_to(root) for p in root.rglob(GAP_ANALYSIS_FILE)] == [
        Path("Dragon Ball Z (1989)") / GAP_ANALYSIS_FILE
    ]


def test_an_unchanged_report_isnt_written_again(identified: sqlite3.Connection, root: Path):
    write_reports(identified, now=NOW)
    report = root / "Dragon Ball Z (1989)" / GAP_ANALYSIS_FILE
    before = report.stat().st_mtime_ns

    again = write_reports(identified, now=NOW.replace(hour=11))

    assert again.reports == 0
    assert report.stat().st_mtime_ns == before


def test_a_cover_from_anilist_is_fetched_once_then_kept(client: TestClient, web: FakeWeb):
    cover = "https://s4.anilist.co/file/anilistcdn/media/anime/cover/medium/bx1-cover.png"
    web.answers[f"GET {cover}"] = Reply(200, {}, b"png bytes")

    first = client.get("/artwork", params={"address": cover})
    again = client.get("/artwork", params={"address": cover})

    assert (first.status_code, first.content, first.headers["content-type"]) == (
        200,
        b"png bytes",
        "image/png",
    )
    assert again.content == b"png bytes"
    assert web.paths().count(f"GET {cover}") == 1


def test_a_picture_from_anywhere_else_is_refused_unasked(client: TestClient, web: FakeWeb):
    answer = client.get("/artwork", params={"address": "https://example.org/tracker.png"})

    assert answer.status_code == 404
    assert web.asked == []


def test_a_report_says_the_time_on_this_pc(identified: sqlite3.Connection, root: Path):
    # The scan's clock is UTC; the report is read by a person, in their own time.
    write_reports(identified, now=NOW)

    report = (root / "Dragon Ball Z (1989)" / GAP_ANALYSIS_FILE).read_text(encoding="utf-8")
    local = NOW.astimezone()
    assert f"_Updated {local.day} Oct {local.year}, {local:%H:%M} · library" in report


def test_one_title_has_every_episode_with_its_state_for_the_map(
    client: TestClient, identified: sqlite3.Connection, root: Path
):
    [dbz_id] = [t["id"] for t in client.get("/titles").json() if t["name"] == "Dragon Ball Z"]

    detail = client.get(f"/titles/{dbz_id}").json()

    states = {(e["season"], e["number"]): e["state"] for e in detail["episodes"]}
    assert len(states) == 291
    assert states[(5, 11)] == "missing"
    assert states[(1, 1)] == "to convert"  # 720x540 HEVC isn't the 1080p standard yet
    assert (detail["source"], detail["folder"]) == ("tmdb", str(root / "Dragon Ball Z (1989)"))


def test_a_titles_report_can_be_read_once_its_written(
    client: TestClient, identified: sqlite3.Connection, root: Path
):
    [dbz_id] = [t["id"] for t in client.get("/titles").json() if t["name"] == "Dragon Ball Z"]
    assert client.get(f"/titles/{dbz_id}/report").status_code == 404  # not written yet

    write_reports(identified, now=NOW)
    report = client.get(f"/titles/{dbz_id}/report").json()

    assert report["path"] == str(root / "Dragon Ball Z (1989)" / GAP_ANALYSIS_FILE)
    assert report["text"].startswith("# Dragon Ball Z (1989) — gap analysis")


def test_franchises_form_for_a_library_identified_before_kura_kept_links(
    client: TestClient, identified: sqlite3.Connection, paths: DataPaths
):
    with identified:
        identified.execute("DELETE FROM anilist_links")  # as identified before schema 5
    assert [len(f["titles"]) for f in client.get("/franchises").json()] == [1, 1, 1]

    identify(paths, identified, internet())  # the next scan

    assert [len(f["titles"]) for f in client.get("/franchises").json()] == [1, 2]
