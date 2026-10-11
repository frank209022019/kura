"""Keeping the library current while Kura is open.

- At start, a scan catches up on what changed while Kura was closed (once setup is done).
- The library folders are watched: when a video is added, removed or renamed, a scan starts once
  the folder has been quiet for a moment (a season still copying waits until it's done).
- Episode lists are asked for again on schedule: every hour for shows still airing, every week
  for finished ones (kura/identify.py decides when one is due), and the gap reports follow.

Nothing here runs while a scan does, and a scan the owner paused stays paused.
"""

import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Protocol

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from kura import credentials, db
from kura.anilist import AniList
from kura.cache import Cache
from kura.config import DataPaths
from kura.core.catalog import TitleKind
from kura.core.extensions import is_video
from kura.identify import AIRING_EVERY, due, save_anilist_title, save_show
from kura.reports import write_reports
from kura.scan import ScanBusyError, ScanStatus
from kura.tmdb import Tmdb
from kura.web import Send, WebError

log = logging.getLogger(__name__)

QUIET = 10.0  # seconds without a change before a scan starts
TICK = 15.0  # how often the watcher looks around


class Scans(Protocol):
    """What the watcher needs of the scanner (kura/scan.py)."""

    def start(self) -> ScanStatus: ...

    def status(self) -> ScanStatus: ...


class Watcher:
    def __init__(
        self,
        paths: DataPaths,
        scanner: Scans,
        transport: Send,
        *,
        now: Callable[[], datetime],
        clock: Callable[[], float] = time.monotonic,
        anilist: AniList | None = None,
    ) -> None:
        self._paths = paths
        self._scanner = scanner
        self._transport = transport
        self._now = now
        self._anilist = anilist or AniList(transport, cache=Cache(paths.cache))
        self._clock = clock
        self._lock = threading.Lock()
        self._changed_at: float | None = None  # when a video last changed, not yet scanned
        self._watched: dict[str, BaseObserver] = {}
        self._resting_until: datetime | None = None  # after a failed refresh, asked again then
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Catches up, then watches until `stop`."""
        self.catch_up()
        self._thread = threading.Thread(target=self._loop, name="watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        for observer in self._watched.values():
            observer.stop()
        self._watched.clear()

    def catch_up(self) -> bool:
        """Starts a scan for what changed while Kura was closed. False when it didn't: setup isn't
        done, there are no folders, or a scan is running or paused."""
        with closing(db.connect(self._paths.database)) as conn:
            set_up = conn.execute("SELECT value FROM settings WHERE key = 'set_up'").fetchone()
            has_folders = conn.execute("SELECT 1 FROM folders LIMIT 1").fetchone() is not None
        if set_up is None or set_up["value"] != "true" or not has_folders:
            return False
        if self._scanner.status().state in ("running", "paused"):
            return False
        return self._start_scan()

    def notice(self) -> None:
        """A video changed in a library folder."""
        with self._lock:
            self._changed_at = self._clock()

    @property
    def pending(self) -> bool:
        """A change was noticed and hasn't been scanned yet."""
        with self._lock:
            return self._changed_at is not None

    def tick(self) -> None:
        """One look around: follow the folders, scan after changes, refresh due episode lists."""
        self._follow_folders()
        with self._lock:
            changed = self._changed_at
        if changed is not None and self._clock() - changed >= QUIET:
            state = self._scanner.status().state
            if state == "paused":
                return  # the owner paused it: the changes wait for them
            if self._start_scan():
                with self._lock:
                    if self._changed_at == changed:
                        self._changed_at = None
            return
        if self._scanner.status().state != "running":
            self.refresh()

    def refresh(self) -> int:
        """Asks again for the episode lists that are due, of the titles the library holds a
        video of, then refreshes the reports. Returns how many lists were asked for. Offline or
        refused, every list waits an hour; a show TMDB or AniList no longer has waits until it's
        due again."""
        if self._resting_until is not None and self._now() < self._resting_until:
            return 0
        key = credentials.load(self._paths, "tmdb")
        cache = Cache(self._paths.cache)
        tmdb = Tmdb(key, self._transport, cache=cache) if key else None
        asked = 0
        with closing(db.connect(self._paths.database)) as conn:
            rows = conn.execute(
                """SELECT * FROM titles AS t
                   WHERE kind != 'movie' AND checked_at IS NOT NULL
                     AND EXISTS (SELECT 1 FROM files AS f
                                 WHERE f.title_id = t.id AND f.gone_at IS NULL)"""
            ).fetchall()
            for row in rows:
                if not due(row, self._now()):
                    continue
                try:
                    found = self._ask(conn, row, tmdb)
                except WebError as error:
                    log.info("An episode list couldn't be refreshed now: %s", error)
                    self._resting_until = self._now() + AIRING_EVERY
                    break  # offline or busy: everything waits for the next hour
                if found:
                    asked += 1
                elif found is False:  # gone from TMDB or AniList: not again until it's due
                    with conn:
                        conn.execute(
                            "UPDATE titles SET checked_at = ? WHERE id = ?",
                            (self._now().isoformat(), row["id"]),
                        )
            if asked:
                write_reports(conn, now=self._now())
        return asked

    def _ask(self, conn: sqlite3.Connection, row: sqlite3.Row, tmdb: Tmdb | None) -> bool | None:
        """Asks again for one title's episode list: True when it came, False when TMDB or
        AniList no longer has the show, None when there's no one to ask (a TMDB show while Kura
        has no key, or an OVA that's a film on TMDB)."""
        if row["tmdb_type"] == "tv":
            if tmdb is None:
                return None
            show = tmdb.show(row["tmdb_id"])
            if show is None:
                return False
            save_show(conn, show, TitleKind(row["kind"]), row["anilist_id"], self._now())
            return True
        if row["tmdb_id"] is not None or row["anilist_id"] is None:
            return None
        entry = self._anilist.entry(row["anilist_id"], fresh=True)
        if entry is None:
            return False
        save_anilist_title(conn, entry, self._now())
        return True

    def _loop(self) -> None:
        while not self._stopping.wait(TICK):
            try:
                self.tick()
            except Exception:  # the watcher must outlive any one bad look around
                log.exception("Watching the library hit a problem")

    def _start_scan(self) -> bool:
        try:
            self._scanner.start()
        except ScanBusyError:
            return False
        return True

    def _follow_folders(self) -> None:
        """Watches every library folder that's there, stops watching forgotten ones, and watches
        a folder again when it comes back (a drive plugged in again): Windows stops telling
        about a folder once it goes."""
        with closing(db.connect(self._paths.database)) as conn:
            wanted = {row["path"] for row in conn.execute("SELECT path FROM folders")}
        for path, observer in list(self._watched.items()):
            if path not in wanted:
                self._watched.pop(path).stop()
            elif not Path(path).is_dir() or not all(e.is_alive() for e in observer.emitters):
                self._watched.pop(path).stop()
                self.notice()  # its videos went with it
        for path in wanted - set(self._watched):
            if not Path(path).is_dir():
                continue  # its drive is unplugged: watched once it's back
            observer = Observer()
            observer.schedule(Changes(self.notice, self._holds), path, recursive=True)
            try:
                observer.start()
            except OSError as error:
                log.warning("Kura can't watch %s: %s", path, error)
                continue
            self._watched[path] = observer

    def _holds(self, path: str) -> bool:
        """Whether the library has a video at this path, or in a folder there."""
        folder = path.rstrip("\\/") + "\\"
        with closing(db.connect(self._paths.database)) as conn:
            row = conn.execute(
                """SELECT 1 FROM files
                   WHERE gone_at IS NULL
                     AND (lower(path) = lower(?) OR lower(substr(path, 1, ?)) = lower(?))
                   LIMIT 1""",
                (path, len(folder), folder),
            ).fetchone()
        return row is not None


class Changes(FileSystemEventHandler):
    """Tells the watcher when a video, or a folder that holds or may hold videos, comes or goes.
    Something written inside a folder (Kura's own report, say) isn't a change: files tell for
    themselves. Windows tells of a folder moved out or deleted as a file gone, so a gone
    path counts when the library has videos there (`holds`)."""

    def __init__(self, notice: Callable[[], None], holds: Callable[[str], bool]) -> None:
        self._notice = notice
        self._holds = holds

    def on_any_event(self, event: FileSystemEvent) -> None:
        source = str(event.src_path)
        target = str(event.dest_path) if event.dest_path else ""
        match event.event_type:
            case "created":
                changed = event.is_directory or is_video(source)
            case "modified" | "closed":
                changed = not event.is_directory and is_video(source)
            case "deleted":
                changed = is_video(source) or self._holds(source)
            case "moved":
                changed = (
                    event.is_directory
                    or is_video(source)
                    or is_video(target)
                    or self._holds(source)
                )
            case _:
                changed = False  # opened, or closed without writing
        if changed:
            self._notice()
