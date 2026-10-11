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


def artwork_wanted(conn: sqlite3.Connection) -> bool:
    """Whether Kura keeps poster and background pictures next to each show (off unless the owner
    turns it on: it writes into the anime folders)."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'artwork'").fetchone()
    return row is not None and json.loads(row["value"]) is True


def quarantine_days(conn: sqlite3.Connection) -> int | None:
    """How many days what's set aside is kept before it's cleared out (Settings > Your data), or
    None: for good."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'quarantine_days'").fetchone()
    days = json.loads(row["value"]) if row else 30
    return days if days is None or days in (7, 30, 90) else 30
