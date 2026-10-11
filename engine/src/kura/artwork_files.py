"""Poster and background pictures next to each show and film, for media servers: `poster.jpg`
and `fanart.jpg` in the folder that holds a title's videos and nothing of another anime's (where
its gap analysis goes), when the owner turns them on in Settings > Your data. Kura never writes
over a file that's there, and takes away only the pictures it wrote, as it wrote them
(artwork_files keeps which): turned off, they go; a picture the owner changed stays theirs.
"""

import logging
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from kura.artwork import background_address, large_poster_address
from kura.preferences import artwork_wanted
from kura.reports import own_folder
from kura.web import Send, Service, WebError

log = logging.getLogger(__name__)

POSTER, BACKGROUND = "poster.jpg", "fanart.jpg"


def write_artwork(conn: sqlite3.Connection, transport: Send, *, now: datetime) -> int:
    """Writes the pictures still missing next to each title with a folder of its own, when the
    owner wants them. Returns how many it wrote. Offline, the rest wait for next time."""
    if not artwork_wanted(conn):
        return 0
    roots = [Path(row["path"]) for row in conn.execute("SELECT path FROM folders")]
    titles = conn.execute(
        """SELECT t.id, t.poster, t.backdrop FROM titles AS t
           WHERE EXISTS (SELECT 1 FROM files AS f WHERE f.title_id = t.id AND f.gone_at IS NULL)
           ORDER BY t.id"""
    ).fetchall()
    service = Service("Artwork", transport)
    written = 0
    for title in titles:
        folder = own_folder(conn, title["id"], roots)
        if folder is None:
            continue
        wanted = (
            (POSTER, large_poster_address(title["poster"])),
            (BACKGROUND, background_address(title["backdrop"])),
        )
        for name, address in wanted:
            target = folder / name
            if address is None or target.exists():  # Kura's from before, or the owner's own
                continue
            try:
                data = service.raw(address)
            except WebError as error:
                log.info("A picture for a show couldn't be fetched now: %s", error)
                return written  # offline or refused: the rest wait for next time
            if _write(target, data):
                with conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO artwork_files (path, title_id, size, written_at)"
                        " VALUES (?, ?, ?, ?)",
                        (str(target), title["id"], len(data), now.isoformat()),
                    )
                written += 1
    return written


def forget_artwork(conn: sqlite3.Connection, folders: Iterable[Path] | None = None) -> int:
    """Takes away the pictures Kura wrote (in `folders`, or everywhere), each only if it's still
    as Kura wrote it. Returns how many went."""
    rows = conn.execute("SELECT path, size FROM artwork_files").fetchall()
    within = [folder.resolve() for folder in folders] if folders is not None else None
    gone = 0
    for row in rows:
        path = Path(row["path"])
        if within is not None and path.parent.resolve() not in within:
            continue
        try:
            if path.stat().st_size == row["size"]:
                path.unlink()
                gone += 1
        except OSError:
            pass  # gone already, or can't be removed: either way no longer Kura's to keep
        with conn:
            conn.execute("DELETE FROM artwork_files WHERE path = ?", (row["path"],))
    return gone


def _write(target: Path, data: bytes) -> bool:
    """Writes a picture where no file is, never over one."""
    try:
        with target.open("xb") as picture:
            picture.write(data)
    except FileExistsError:
        return False
    except OSError as error:
        log.warning("Kura couldn't write %s: %s", target, error)
        target.unlink(missing_ok=True)
        return False
    return True
