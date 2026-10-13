"""Preferences chosen during setup, and the graphics card check."""

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kura import system
from kura.system import best_card


def test_a_new_kura_starts_from_the_recommended_choices(client: TestClient):
    assert client.get("/settings").json() == {
        "standard": "cinema-1080",
        "naming": "plex",
        "upscaleSd": True,
        "upscale720": True,
        "setUp": False,
        "reports": True,
        "quarantineDays": 30,
        "originals": "quarantine",
        "artwork": False,
    }


def test_turning_the_pictures_off_takes_away_the_ones_kura_wrote(
    client: TestClient, conn: sqlite3.Connection, tmp_path: Path
):
    picture = tmp_path / "Trigun (1998)" / "poster.jpg"
    picture.parent.mkdir()
    picture.write_bytes(b"a poster")
    with conn:
        conn.execute("INSERT INTO titles (id, kind, name) VALUES (1, 'series', 'Trigun')")
        conn.execute(
            "INSERT INTO artwork_files (path, title_id, size, written_at) VALUES (?, 1, 8, 'now')",
            (str(picture),),
        )
    on = {**client.get("/settings").json(), "artwork": True}
    client.put("/settings", json=on)

    client.put("/settings", json={**on, "artwork": False})

    assert not picture.exists()


def test_choices_are_kept(client: TestClient, conn: sqlite3.Connection):
    chosen = {
        "standard": "compact-720",
        "naming": "jellyfin",
        "upscaleSd": True,
        "upscale720": False,
        "setUp": True,
        "reports": True,
        "quarantineDays": None,
        "originals": "delete",
        "artwork": True,
    }

    saved = client.put("/settings", json=chosen)

    assert saved.status_code == 200
    assert client.get("/settings").json() == chosen
    stored = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    assert json.loads(stored["standard"]) == "compact-720"  # what the export carries


def test_a_choice_kura_doesnt_offer_is_refused(client: TestClient):
    response = client.put("/settings", json={"standard": "8k-ultra"})

    assert response.status_code == 422


def test_a_stored_value_this_kura_doesnt_know_falls_back_to_the_default(
    client: TestClient, conn: sqlite3.Connection
):
    with conn:
        conn.execute("INSERT INTO settings VALUES ('naming', ?)", (json.dumps("emby"),))

    assert client.get("/settings").json()["naming"] == "plex"


@pytest.mark.parametrize(
    ("names", "card"),
    [
        (
            ["Intel(R) UHD Graphics 630", "NVIDIA GeForce GTX 1660 SUPER"],
            "NVIDIA GeForce GTX 1660 SUPER",
        ),
        (["AMD Radeon RX 7800 XT"], "AMD Radeon RX 7800 XT"),
        (["Intel(R) UHD Graphics 630"], "Intel(R) UHD Graphics 630"),
        ([" ", ""], None),
    ],
)
def test_the_card_kura_converts_with_is_the_dedicated_one(names: list[str], card: str | None):
    assert best_card(names) == card


def test_the_graphics_card_check_names_the_card(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(system, "graphics_card", lambda: "NVIDIA GeForce GTX 1660 SUPER")

    assert client.get("/system").json() == {"graphicsCard": "NVIDIA GeForce GTX 1660 SUPER"}
