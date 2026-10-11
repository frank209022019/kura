"""Shared test setup: every test gets its own empty data folder, and a small anime library."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, suppress
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kura import db
from kura.api import create_app
from kura.config import DataPaths
from kura.core.library import QUARANTINE_FOLDER
from tests.fake_web import FakeWeb
from tests.shelf import NOW

TOKEN = "test-token"


@pytest.fixture
def paths(tmp_path: Path) -> DataPaths:
    return DataPaths(tmp_path / "Kura")


@pytest.fixture
def web() -> FakeWeb:
    """The internet as the engine sees it in tests: nothing answers until a test says what."""
    return FakeWeb()


@pytest.fixture
def client(paths: DataPaths, web: FakeWeb) -> Iterator[TestClient]:
    """A client that talks to the API the way the app does: on 127.0.0.1, with the token."""
    app = create_app(TOKEN, paths, transport=web)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as test_client:
        yield test_client


@pytest.fixture
def quarantine(tmp_path: Path) -> Iterator[None]:
    """Copies set aside go to the drive's own "Kura quarantine" folder, outside the test's folder:
    whatever a test leaves there, a failing one say, goes afterwards."""
    days: set[date] = {NOW.date(), datetime.now().astimezone().date()}
    folders = [Path(tmp_path.anchor) / QUARANTINE_FOLDER / day.isoformat() for day in days]
    before = {item for folder in folders if folder.exists() for item in folder.iterdir()}
    yield
    for folder in folders:
        if folder.exists():
            for item in set(folder.iterdir()) - before:
                item.unlink(missing_ok=True)
        with suppress(OSError):
            folder.rmdir()  # only when nothing else is there
    with suppress(OSError):
        folders[0].parent.rmdir()


@pytest.fixture
def conn(paths: DataPaths) -> Iterator[sqlite3.Connection]:
    """The data folder's database, migrated to the latest schema."""
    with closing(db.connect(paths.database)) as connection:
        db.migrate(connection)
        yield connection


@pytest.fixture
def anime(tmp_path: Path) -> Path:
    """A small library in any layout, with things a scan should pass over."""
    root = tmp_path / "Anime"
    files = {
        "Dragon Ball/Dragon Ball - 001 - Secret of the Dragon Balls.mkv": b"episode one",
        "Dragon Ball/Dragon Ball - 001 - Secret of the Dragon Balls.en.srt": b"subtitles",
        "Dragon Ball/folder.jpg": b"art",
        "Broly the Legendary Super Saiyan.avi": b"a movie without a folder",
        "Kura quarantine/2026-10-10/old copy.mkv": b"set aside",
        ".thumbnails/preview.mp4": b"hidden",
        "Downloads/[Group] DBZ - 001 [480p].MKV": b"mixed in",
    }
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    return root
