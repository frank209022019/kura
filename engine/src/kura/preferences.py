"""The owner's preferences as the engine uses them (the API's Settings say how they're stored)."""

import json
import sqlite3
from dataclasses import replace

from kura.core.standard import CINEMA_1080, COMPACT_720, Standard


def library_standard(conn: sqlite3.Connection) -> Standard:
    """The standard the owner chose in setup, with their upscaling choices."""
    stored = {
        row["key"]: json.loads(row["value"]) for row in conn.execute("SELECT * FROM settings")
    }
    base = COMPACT_720 if stored.get("standard") == "compact-720" else CINEMA_1080
    return replace(
        base,
        ai_for_sd=stored.get("upscale_sd", True) is not False,
        fast_for_hd=stored.get("upscale_720", True) is not False,
    )
