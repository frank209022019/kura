"""What the engine tells the app beyond the ready line, on its standard output: one JSON object a
line, which the shell reads (app/src-tauri/src/engine.rs). Today, notifications: something worth
a Windows notification while Kura's window is in the tray, such as a finished batch.
"""

import json
import sys
import threading

_lock = threading.Lock()  # one line at a time, from whichever thread


def notify(title: str, body: str) -> None:
    """Asks the app for a notification: a title and a line under it. In plain ASCII (JSON's
    escapes), so it reads the same whatever code page Windows gives the pipe."""
    line = json.dumps({"event": "notify", "title": title, "body": body})
    with _lock:
        try:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except OSError, ValueError:  # the app has gone, or its pipe closed: nobody to tell
            pass
