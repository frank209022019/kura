"""Tidying up through the API: the proposal, applying it, History, and undoing it."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from kura import credentials
from kura.api import create_app
from kura.config import DataPaths
from kura.scan import Scanner, ScanStatus
from tests.conftest import TOKEN
from tests.services import internet
from tests.shelf import identify, library


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "Anime"


pytestmark = pytest.mark.usefixtures("quarantine")


@pytest.fixture
def mixed(paths: DataPaths, conn: sqlite3.Connection, root: Path) -> sqlite3.Connection:
    """Downloads holding two anime, one episode twice, and a file that waits for a match."""
    credentials.save(paths, "tmdb", "a-test-key")
    library(
        conn,
        root,
        [
            "Downloads/Cowboy Bebop - 01.mkv",
            "Downloads/Cowboy Bebop - 01 (copy).mkv",
            "Downloads/Dragon Ball Z - 150.mkv",
            "Downloads/Mystery Show - 03.mkv",
        ],
    )
    identify(paths, conn, internet())
    return conn


def test_kura_proposes_and_counts_what_waits(client: TestClient, mixed: sqlite3.Connection):
    proposal = client.get("/tidy").json()

    assert [(c["kind"], c["category"], c["title"], c["label"]) for c in proposal["changes"]] == [
        ("quarantine", "duplicate", "Cowboy Bebop", "Cowboy Bebop · S01E01 · duplicate"),
        ("move", "mixed", "Cowboy Bebop", "Cowboy Bebop · S01E01"),
        ("move", "mixed", "Dragon Ball Z", "Dragon Ball Z · S05E11"),
    ]
    [duplicate] = proposal["duplicates"]
    assert duplicate["keep"]["path"].endswith("Cowboy Bebop - 01.mkv")
    assert (duplicate["keep"]["height"], duplicate["keep"]["plays"]) == (540, True)
    assert (proposal["waiting"], proposal["broken"]) == (1, 0)


def test_applying_lists_the_plan_in_history_and_undo_puts_it_back(
    client: TestClient, mixed: sqlite3.Connection, root: Path
):
    sources = [c["source"] for c in client.get("/tidy").json()["changes"]]

    done = client.post("/tidy", json={"sources": sources}).json()

    assert (done["moved"], done["quarantined"], done["problems"]) == (2, 1, [])
    assert client.get("/tidy").json()["changes"] == []
    [plan] = client.get("/history").json()["plans"]
    assert plan["id"] == done["planId"]
    assert plan["title"] == "Tidied 3 files: Cowboy Bebop and Dragon Ball Z"
    assert (plan["moved"], plan["quarantined"], plan["undoneAt"]) == (2, 1, None)

    back = client.post(f"/plans/{done['planId']}/undo").json()

    assert (back["moved"], back["quarantined"]) == (2, 1)
    assert (root / "Downloads" / "Cowboy Bebop - 01 (copy).mkv").exists()
    [plan] = client.get("/history").json()["plans"]
    assert plan["undoneAt"] is not None
    assert plan["undone"] == 3


def test_a_copys_subtitles_go_with_it_and_count_as_no_copy_of_their_own(
    client: TestClient, mixed: sqlite3.Connection, root: Path
):
    (root / "Downloads" / "Cowboy Bebop - 01 (copy).en.srt").write_text("1", encoding="utf-8")
    sources = [c["source"] for c in client.get("/tidy").json()["changes"]]

    done = client.post("/tidy", json={"sources": sources}).json()

    assert len(sources) == 4
    assert (done["moved"], done["quarantined"]) == (2, 1)
    [plan] = client.get("/history").json()["plans"]
    assert (plan["moved"], plan["quarantined"]) == (2, 1)


def test_the_owner_can_keep_the_other_copy(client: TestClient, mixed: sqlite3.Connection):
    copied = next(
        c["source"] for c in client.get("/tidy").json()["changes"] if c["kind"] == "quarantine"
    )

    proposal = client.get("/tidy", params={"keep": copied}).json()
    done = client.post("/tidy", json={"sources": [copied], "keep": [copied]}).json()

    assert proposal["duplicates"][0]["keep"]["path"] == copied
    assert done["moved"] == 1


def test_an_unknown_plan_cant_be_undone(client: TestClient, conn: sqlite3.Connection):
    assert client.post("/plans/99/undo").status_code == 404


class Busy:
    """A scanner in the middle of a scan."""

    def status(self) -> ScanStatus:
        return ScanStatus("running", "reading", None, None, 3, 3, 1, 0, None, None, (), None)

    def recover(self) -> None:
        pass


@pytest.fixture
def scanning(paths: DataPaths) -> Iterator[TestClient]:
    app = create_app(TOKEN, paths, scanner=cast("Scanner", Busy()))
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        yield client


def test_nothing_moves_while_a_scan_runs(scanning: TestClient, conn: sqlite3.Connection):
    answer = scanning.post("/tidy", json={"sources": ["D:/Anime/a.mkv"]})

    assert answer.status_code == 409
    assert answer.json()["detail"] == (
        "A scan is running. Tidy up once it's done, so Kura knows every file."
    )
