"""Backups through the API: listing them, making one now, and restoring one, which happens as
the engine starts again."""

from fastapi.testclient import TestClient

from kura.api import create_app
from kura.config import DataPaths
from tests.conftest import TOKEN


def settings(client: TestClient, **changed: object) -> None:
    client.put("/settings", json={**client.get("/settings").json(), **changed})


def test_backups_are_listed_and_one_can_be_made_now(client: TestClient):
    assert client.get("/backups").json() == {"backups": [], "restored": None}

    made = client.post("/backups").json()

    assert client.get("/backups").json()["backups"] == [made]
    assert made["name"].startswith("kura ")
    assert made["size"] > 0
    assert made["beforeRestoring"] is False


def test_a_backup_is_restored_as_the_engine_starts_again(client: TestClient, paths: DataPaths):
    settings(client, naming="keep")
    made = client.post("/backups").json()
    settings(client, naming="plex")

    asked = client.post(f"/backups/{made['name']}/restore")

    assert asked.status_code == 204
    assert client.get("/settings").json()["naming"] == "plex"  # not till the engine starts again
    headers = {"Authorization": f"Bearer {TOKEN}"}
    app = create_app(TOKEN, paths)
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as again:
        assert again.get("/settings").json()["naming"] == "keep"
        restored = again.get("/backups").json()["restored"]
        assert (restored["name"], restored["problem"]) == (made["name"], None)


def test_a_backup_that_isnt_there_cant_be_restored(client: TestClient):
    answer = client.post("/backups/kura 2026-01-01 0300.db/restore")

    assert answer.status_code == 404
    assert answer.json()["detail"] == "Kura has no such backup."
