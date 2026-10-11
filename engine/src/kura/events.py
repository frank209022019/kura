"""What the engine tells the app besides the ready line, on its standard output: one JSON object
a line, which the shell reads (app/src-tauri/src/engine.rs). Before the ready line, that it's
still working at starting (moving the data takes minutes): the app waits rather than give up on
it. After it, notifications: something worth a Windows notification while Kura's window is in
the tray, such as a finished batch.
"""

import json
import sys
import threading
from collections.abc import Generator
from contextlib import contextmanager

_lock = threading.Lock()  # one line at a time, from whichever thread
_EVERY = 5.0  # seconds between the lines saying the engine is still working at starting


def notify(title: str, body: str) -> None:
    """Asks the app for a notification: a title and a line under it. In plain ASCII (JSON's
    escapes), so it reads the same whatever code page Windows gives the pipe."""
    _say({"event": "notify", "title": title, "body": body})


@contextmanager
def working(every: float = _EVERY) -> Generator[None]:
    """While it lasts, tells the app every few seconds that the engine is still working at
    starting, so it waits however long that takes (the app gives up on an engine silent for a
    minute)."""
    done = threading.Event()

    def tell() -> None:
        while not done.wait(every):
            _say({"event": "working"})

    teller = threading.Thread(target=tell, name="working", daemon=True)
    teller.start()
    try:
        yield
    finally:
        done.set()
        teller.join()


def _say(event: dict[str, str]) -> None:
    with _lock:
        try:
            sys.stdout.write(json.dumps(event) + "\n")
            sys.stdout.flush()
        except OSError, ValueError:  # the app has gone, or its pipe closed: nobody to tell
            pass
