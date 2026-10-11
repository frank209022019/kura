"""What this PC has to work with (its graphics card), and what the engine asks of Windows."""

import ctypes
import functools
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_MAKERS = ("nvidia", "geforce", "quadro", "radeon", "amd", "intel arc")
_KILL_ON_JOB_CLOSE = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
_DELETE = 0x00010000  # the right to move or delete a file
_SHARE_READ_WRITE = 0x1 | 0x2  # FILE_SHARE_READ | FILE_SHARE_WRITE
_OPEN_EXISTING = 3
_SHARING_VIOLATION = 32  # ERROR_SHARING_VIOLATION
_DRIVE_REMOTE = 4  # what GetDriveTypeW says of a drive mapped to a network share
_EXTENDED_LIMITS = 9  # JobObjectExtendedLimitInformation


class _BasicLimits(ctypes.Structure):  # JOBOBJECT_BASIC_LIMIT_INFORMATION
    _fields_ = (
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    )


class _ExtendedLimits(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    _fields_ = (
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", ctypes.c_uint64 * 6),  # IO_COUNTERS
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    )


def end_programs_with_engine() -> bool:
    """Puts the engine in a Windows job that ends every program it starts (ffmpeg, say) when the
    engine ends, however it ends: the app stopping it, a crash, or Task Manager. Nothing then
    writes to a file or holds the graphics card after Kura is gone. True once that's so."""
    if sys.platform != "win32":
        return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
    kernel.SetInformationJobObject.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    )
    kernel.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return False
    limits = _ExtendedLimits(BasicLimitInformation=_BasicLimits(LimitFlags=_KILL_ON_JOB_CLOSE))
    size = ctypes.sizeof(limits)
    if not kernel.SetInformationJobObject(job, _EXTENDED_LIMITS, ctypes.byref(limits), size) or (
        not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess())
    ):
        kernel.CloseHandle(job)
        return False
    return True  # the job stays open till the engine ends: Windows closes it, ending the rest


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


def on_network(path: Path) -> bool:
    r"""Whether a path is on another computer: a network share (\\nas\anime) or a drive mapped
    to one. Asked without touching the network, so an unreachable one answers at once."""
    anchor = path.anchor
    if anchor.startswith("\\\\") and not anchor.startswith("\\\\?\\"):
        return True
    if sys.platform != "win32" or not anchor:
        return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetDriveTypeW.argtypes = (ctypes.c_wchar_p,)
    kernel.GetDriveTypeW.restype = ctypes.c_uint32
    return kernel.GetDriveTypeW(anchor) == _DRIVE_REMOTE


def in_use(path: Path) -> bool:
    """Whether another program has a file open so that it can't be moved now: a player playing
    it, say. Windows says so when asked for the right to move it, which this asks and gives
    straight back."""
    if sys.platform != "win32":
        return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CreateFileW.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel.CreateFileW(
        str(path), _DELETE, _SHARE_READ_WRITE, None, _OPEN_EXISTING, 0, None
    )
    if handle is None or handle == ctypes.c_void_p(-1).value:  # INVALID_HANDLE_VALUE
        return ctypes.get_last_error() == _SHARING_VIOLATION
    kernel.CloseHandle(handle)
    return False
