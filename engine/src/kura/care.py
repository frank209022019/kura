"""Looking after Kura while it's open, on a background thread: tonight's backup of its records
(from 03:00, or the first chance after: kura/backups.py), once a day clearing out of the
quarantine what has waited longer than the owner keeps it (kura/quarantine.py) and of History
what's older than the owner keeps it (kura/history.py), and the poster and background pictures
next to each show when the owner wants them (kura/artwork_files.py). The clear-out waits while
files move (Scanner.hold), so a tidy-up putting a copy back never meets it.
"""

import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager, closing
from datetime import date, datetime, timedelta

from kura import backups, db, history
from kura.artwork_files import write_artwork
from kura.backups import BackupError
from kura.config import DataPaths
from kura.preferences import history_days, quarantine_days
from kura.quarantine import clear_out
from kura.scan import ScanBusyError
from kura.web import Send

log = logging.getLogger(__name__)

EVERY = 300.0  # seconds between looks
_REST = timedelta(hours=1)  # after a backup fails, before it's tried again


class Care:
    def __init__(
        self,
        paths: DataPaths,
        hold: Callable[[], AbstractContextManager[None]],
        *,
        now: Callable[[], datetime],
        transport: Send | None = None,
    ) -> None:
        """`hold` holds scans and file moves off (Scanner.hold); `transport` fetches pictures."""
        self._paths = paths
        self._hold = hold
        self._now = now
        self._transport = transport
        self._wake = threading.Event()
        self._cleared_on: date | None = None  # the day the quarantine was last cleared out
        self._resting_until: datetime | None = None  # after a backup failed
        self._refused: dict[str, datetime] = {}  # pictures refused, and when to ask again
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Looks after what's due now, then every few minutes until `stop`."""
        self._thread = threading.Thread(target=self._loop, name="care", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def wake(self) -> None:
        """Looks after things now rather than at the next look (the owner turned the pictures
        on, say)."""
        self._wake.set()

    def look_after(self) -> None:
        """Does what's due: tonight's backup, the pictures next to each show, and today's
        clear-out."""
        now = self._now()
        resting = self._resting_until is not None and now < self._resting_until
        if not resting and backups.due(self._paths, now):
            try:
                backups.back_up(self._paths, now)
            except BackupError as error:
                log.warning("%s", error)
                self._resting_until = now + _REST
        if self._transport is not None:
            with closing(db.connect(self._paths.database)) as conn:
                write_artwork(conn, self._transport, now=now, refused=self._refused)
        if self._cleared_on != now.date():
            try:
                with self._hold(), closing(db.connect(self._paths.database)) as conn:
                    clear_out(conn, days=quarantine_days(conn), now=now)
                    # Then History, so what the clear-out just emptied can go from it too.
                    days = history_days(conn)
                    if days is not None:
                        history.clear(conn, keep=timedelta(days=days), now=now)
            except ScanBusyError:
                return  # a scan runs, or files move: next time
            self._cleared_on = now.date()

    def _loop(self) -> None:
        while True:
            try:
                self.look_after()
            except Exception:  # care must outlive any one problem
                log.exception("Looking after Kura hit a problem")
            self._wake.wait(EVERY)
            self._wake.clear()
            if self._stopping.is_set():
                return
