"""What this PC has to work with: today, its graphics card."""

import functools
import os
import subprocess
from collections.abc import Iterable

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_MAKERS = ("nvidia", "geforce", "quadro", "radeon", "amd", "intel arc")


def best_card(names: Iterable[str]) -> str | None:
    """The card Kura converts with: a dedicated one when there is one, else the first."""
    cards = [name.strip() for name in names if name.strip()]
    dedicated = [name for name in cards if any(maker in name.casefold() for maker in _MAKERS)]
    return (dedicated or cards or [None])[0]


@functools.cache
def graphics_card() -> str | None:
    """The PC's graphics card as Windows names it, asked once. None when Windows won't say."""
    if os.name != "nt":
        return None
    query = "Get-CimInstance Win32_VideoController | ForEach-Object Name"
    try:
        result = subprocess.run(  # noqa: S603 - a fixed command, no shell
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", query],  # noqa: S607
            stdin=subprocess.DEVNULL,  # the engine's own input is the app's
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    return best_card(result.stdout.splitlines())
