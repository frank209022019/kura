"""The owner's preferences as the engine uses them (the API's Settings say how they're stored)."""

import json
import sqlite3
from dataclasses import replace

from kura.core.standard import CINEMA_1080, COMPACT_720, Standard


def names_kept(conn: sqlite3.Connection) -> bool:
    """Whether files keep their own names when they're filed ("Keep my names"); Plex and
    Jellyfin both read Kura's names."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'naming'").fetchone()
    return row is not None and json.loads(row["value"]) == "keep"


def reports_wanted(conn: sqlite3.Connection) -> bool:
    """Whether Kura writes a gap analysis next to each anime (the owner can turn it off)."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'reports'").fetchone()
    return row is None or json.loads(row["value"]) is not False


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
