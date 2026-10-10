"""Shared test setup: every test gets its own empty data folder."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kura.api import create_app
from kura.config import DataPaths

TOKEN = "test-token"


@pytest.fixture
def paths(tmp_path: Path) -> DataPaths:
    return DataPaths(tmp_path / "Kura")


@pytest.fixture
def client(paths: DataPaths) -> Iterator[TestClient]:
    """A client that talks to the API the way the app does: on 127.0.0.1, with the token."""
    app = create_app(TOKEN, paths)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as test_client:
        yield test_client
