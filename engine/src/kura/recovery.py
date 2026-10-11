"""What Kura tells after it closed unexpectedly (a crash, a power cut, Task Manager): what it
settled as it started again. Files that were converting start over from their beginning, a result
that was taking its original's place is finished or its original put back (kura/queue.py), and
file moves a tidy-up or a delete was making are settled (kura/changes.py). A clean stop leaves
none of these, so finding any is how Kura knows it closed unexpectedly. Home tells the owner,
until they've seen it, for a day.
"""

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

_KEY = "recovery"  # the settings row holding the last one
_TOLD_FOR = timedelta(days=1)


@dataclass(frozen=True)
class Recovery:
    """What Kura settled as it started again after closing unexpectedly."""

    at: str = ""  # when Kura started again
    restarted: int = 0  # files that were converting: in line again, from their beginning
    finished: int = 0  # results that were taking their original's place: in it now
    put_back: int = 0  # originals put back, their results never in place
    moves: int = 0  # a tidy-up's or a delete's file moves, settled

    def anything(self) -> bool:
        return any((self.restarted, self.finished, self.put_back, self.moves))


def note(conn: sqlite3.Connection, found: Recovery) -> None:
    """Keeps what a start settled, when it settled anything, for the owner to see."""
    if not found.anything():
        return
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (_KEY, json.dumps(asdict(found))),
        )


def last(conn: sqlite3.Connection, now: datetime) -> Recovery | None:
    """The last recovery, while it's news: not seen yet, and less than a day old."""
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (_KEY,)).fetchone()
    if row is None:
        return None
    found = Recovery(**json.loads(row["value"]))
    if now - datetime.fromisoformat(found.at) > _TOLD_FOR:
        return None
    return found


def seen(conn: sqlite3.Connection) -> None:
    """The owner has seen it: it isn't told again."""
    with conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (_KEY,))
