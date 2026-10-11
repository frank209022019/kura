"""Clearing out the quarantine: what was set aside (copies of an episode, and converted files'
originals) goes once it has waited as many days as the owner keeps it (Settings > Your data; 30
unless they choose otherwise, or for good). Its change in the journal says when, and it can't be
put back after that; the rest of its tidy-up still can.
"""

import logging
import sqlite3
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


def clear_out(conn: sqlite3.Connection, *, days: int | None, now: datetime) -> int:
    """Deletes what was set aside more than `days` ago; nothing when `days` is None. Returns how
    many files went."""
    if days is None:
        return 0
    cutoff = now - timedelta(days=days)
    # A converted file's original goes only once the result took its place: if it never did,
    # the original is the only copy of the episode there is.
    rows = conn.execute(
        """SELECT c.id, c.target, p.applied_at FROM changes AS c
           JOIN plans AS p ON p.id = c.plan_id
           WHERE c.kind = 'quarantine' AND c.state = 'done' AND c.cleared_at IS NULL
             AND p.applied_at IS NOT NULL
             AND (p.kind = 'tidy' OR EXISTS (
                 SELECT 1 FROM changes AS m
                 WHERE m.plan_id = c.plan_id AND m.kind = 'move' AND m.state = 'done'))"""
    ).fetchall()
    cleared = 0
    emptied: set[Path] = set()
    for row in rows:
        if datetime.fromisoformat(row["applied_at"]) >= cutoff:
            continue
        target = Path(row["target"])
        try:
            target.unlink(missing_ok=True)
        except OSError as error:
            log.warning("Kura couldn't clear %s out of quarantine: %s", target, error)
            continue
        with conn:
            conn.execute(
                "UPDATE changes SET cleared_at = ? WHERE id = ?",
                (now.isoformat(timespec="seconds"), row["id"]),
            )
        cleared += 1
        emptied.add(target.parent)
    for day in emptied:  # a day's folder, then the quarantine itself, once nothing's in them
        with suppress(OSError):
            day.rmdir()
            day.parent.rmdir()
    if cleared:
        log.info("Cleared %d files set aside more than %d days ago", cleared, days)
    return cleared
