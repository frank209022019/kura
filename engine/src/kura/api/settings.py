"""Kura's preferences, chosen during setup and changed later in Settings."""

import json
from typing import Literal

from fastapi import APIRouter
from pydantic import ValidationError

from kura.api.common import ApiModel, Database

router = APIRouter()


class Settings(ApiModel):
    standard: Literal["cinema-1080", "compact-720"] = "cinema-1080"
    naming: Literal["plex", "jellyfin", "keep"] = "plex"
    upscale_sd: bool = True  # 480p and 576p get the AI model
    upscale_720: bool = True  # 720p gets the fast upscale
    set_up: bool = False  # the first-run steps are done


@router.get("/settings")
def settings(conn: Database) -> Settings:
    stored = {
        row["key"]: json.loads(row["value"]) for row in conn.execute("SELECT * FROM settings")
    }
    chosen = Settings()
    for key in Settings.model_fields:
        if key in stored:
            try:
                values = {**chosen.model_dump(by_alias=False), key: stored[key]}
                chosen = Settings.model_validate(values)
            except ValidationError:
                pass  # a value this Kura doesn't know: keep the default
    return chosen


@router.put("/settings")
def save_settings(body: Settings, conn: Database) -> Settings:
    with conn:
        conn.executemany(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            [(key, json.dumps(value)) for key, value in body.model_dump(by_alias=False).items()],
        )
    return settings(conn)
