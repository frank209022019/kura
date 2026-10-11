"""Settings > Your data: where Kura keeps it and how big each part is, the export, and what Kura
keeps next to the anime files."""

import sqlite3
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kura import credentials
from kura.config import DataPaths
from kura.core.library import QUARANTINE_FOLDER
from kura.core.report import GAP_ANALYSIS_FILE
from kura.reports import write_reports
from tests.services import internet
from tests.shelf import NOW, identify, library

pytestmark = pytest.mark.usefixtures("quarantine")


def test_each_part_of_the_data_folder_is_measured(
    client: TestClient, paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    for folder, size in (("artwork", 1000), ("cache", 500), ("logs", 200), ("tools", 50)):
        (paths.root / folder).mkdir(parents=True, exist_ok=True)
        (paths.root / folder / "a file").write_bytes(bytes(size))
    library(conn, tmp_path / "Anime", ["Bebop/Cowboy Bebop - 01.mkv"])
    set_aside = Path(tmp_path.anchor) / QUARANTINE_FOLDER / NOW.date().isoformat()
    set_aside.mkdir(parents=True, exist_ok=True)
    (set_aside / "copy.mkv").write_bytes(bytes(300))

    found = client.get("/data").json()

    assert found["folder"] == str(paths.root)
    assert found["database"] > 0
    assert (found["artwork"], found["cache"], found["logs"], found["tools"]) == (1000, 500, 200, 50)
    assert found["backups"] == 0
    [quarantine] = found["quarantine"]
    assert quarantine["folder"] == str(Path(tmp_path.anchor) / QUARANTINE_FOLDER)
    assert quarantine["bytes"] >= 300
    assert quarantine["files"] >= 1


def test_the_export_is_written_where_the_owner_asks(
    client: TestClient, conn: sqlite3.Connection, tmp_path: Path
):
    answer = client.post("/export", json={"folder": str(tmp_path / "Backups")}).json()

    path = Path(answer["path"])
    assert path.parent == tmp_path / "Backups"
    assert answer["size"] == path.stat().st_size
    assert "kura.db" in zipfile.ZipFile(path).namelist()


def test_turning_the_reports_off_takes_them_out_of_the_anime_folders(
    client: TestClient, paths: DataPaths, conn: sqlite3.Connection, tmp_path: Path
):
    credentials.save(paths, "tmdb", "a-test-key")
    root = tmp_path / "Anime"
    library(conn, root, ["Cowboy Bebop/Cowboy Bebop - 01.mkv"])
    identify(paths, conn, internet())
    write_reports(conn, now=NOW)
    report = root / "Cowboy Bebop" / GAP_ANALYSIS_FILE
    assert report.is_file()
    settings = client.get("/settings").json()

    client.put("/settings", json={**settings, "reports": False})

    assert not report.exists()
    client.put("/settings", json={**settings, "reports": True})
    assert report.is_file()
