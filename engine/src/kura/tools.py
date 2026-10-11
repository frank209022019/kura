"""The tools Kura downloads on first run, as listed in downloads.json: today, ffmpeg.

A download is used only when its size and SHA-256 match the list. It is unpacked into the data
folder's tools folder, replacing an older build, keeping only the listed folder of the archive.
Downloads run on a background thread and say how far they are. In development,
KURA_FFMPEG_DIR can point at an ffmpeg that's already on the PC instead.
"""

import errno
import hashlib
import json
import logging
import os
import shutil
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Literal, Protocol, Self
from urllib.error import URLError
from urllib.request import urlopen

from kura.config import DataPaths

log = logging.getLogger(__name__)

_CHUNK = 1 << 20
_MARKER = "kura-download.json"  # which build is unpacked, to notice when the list moves on


@dataclass(frozen=True)
class Download:
    """One entry of downloads.json."""

    id: str
    name: str
    version: str
    purpose: str
    licence: str
    home: str
    url: str
    size: int | None
    sha256: str | None
    keep: str | None  # the folder inside the archive that Kura keeps
    by: Literal["kura", "installer"]  # who fetches it: Kura on first run, or the installer


def manifest() -> tuple[Download, ...]:
    """Everything Kura downloads to a PC, in the order the installer lists it."""
    text = resources.files("kura").joinpath("downloads.json").read_text(encoding="utf-8")
    return tuple(Download(**item) for item in json.loads(text)["downloads"])


type State = Literal["missing", "downloading", "unpacking", "ready", "failed"]


@dataclass(frozen=True)
class Progress:
    state: State
    done: int = 0  # bytes downloaded
    total: int = 0
    problem: str | None = None


class Response(Protocol):
    def read(self, amount: int, /) -> bytes: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
        /,
    ) -> object: ...


type Fetch = Callable[[str], Response]


def _fetch(url: str) -> Response:
    if not url.startswith("https://"):
        raise DownloadError(f"Kura only downloads over HTTPS, and {url} isn't.")
    # The address comes from downloads.json and is HTTPS. urlopen follows GitHub's redirect.
    return urlopen(url, timeout=30)  # noqa: S310


class DownloadError(Exception):
    """A download Kura won't use, with a sentence saying why."""


class Tools:
    """Kura's downloaded tools: which are ready, fetching the rest, and where each program is."""

    def __init__(
        self, paths: DataPaths, items: tuple[Download, ...] | None = None, fetch: Fetch = _fetch
    ) -> None:
        listed = manifest() if items is None else items
        self._paths = paths
        self._items = {item.id: item for item in listed if item.by == "kura"}
        self._fetch = fetch
        self._lock = threading.Lock()
        self._progress: dict[str, Progress] = {}
        self._threads: dict[str, threading.Thread] = {}

    def status(self) -> list[tuple[Download, Progress]]:
        with self._lock:
            return [(item, self._now(item)) for item in self._items.values()]

    def start(self, tool: str) -> None:
        """Starts downloading a tool unless it's ready or already on its way."""
        item = self._items[tool]  # KeyError: not one of Kura's downloads
        with self._lock:
            running = self._threads.get(tool)
            if (running and running.is_alive()) or self._now(item).state == "ready":
                return
            self._progress[tool] = Progress("downloading", 0, item.size or 0)
            thread = threading.Thread(
                target=self._download, args=(item,), name=f"download-{tool}", daemon=True
            )
            self._threads[tool] = thread
        thread.start()

    def wait(self, tool: str, timeout: float | None = None) -> None:
        if thread := self._threads.get(tool):
            thread.join(timeout)

    def path(self, program: str) -> Path | None:
        """Where one of the tools' programs is, once its tool is ready: `path("ffprobe")`."""
        name = f"{program}.exe" if os.name == "nt" else program
        for item in self._items.values():
            folder = self._override(item)
            if folder is None and self._installed(item):
                folder = self._folder(item)
            if folder is not None and (folder / name).is_file():
                return folder / name
        return None

    def _now(self, item: Download) -> Progress:
        progress = self._progress.get(item.id)
        if progress and progress.state in ("downloading", "unpacking", "failed"):
            return progress
        total = item.size or 0
        if self._override(item) or self._installed(item):
            return Progress("ready", total, total)
        return Progress("missing", 0, total)

    def _folder(self, item: Download) -> Path:
        return self._paths.tools / item.id

    def _installed(self, item: Download) -> bool:
        try:
            text = (self._folder(item) / _MARKER).read_text(encoding="utf-8")
            sha256: object = json.loads(text)["sha256"]
        except OSError, ValueError, KeyError, TypeError:
            return False
        return sha256 == item.sha256

    @staticmethod
    def _override(item: Download) -> Path | None:
        folder = os.environ.get(f"KURA_{item.id.upper()}_DIR")
        return Path(folder) if folder and Path(folder).is_dir() else None

    def _set(self, item: Download, state: State, done: int = 0, problem: str | None = None) -> None:
        with self._lock:
            self._progress[item.id] = Progress(state, done, item.size or 0, problem)

    def _download(self, item: Download) -> None:
        try:
            archive = self._fetch_checked(item)
            try:
                self._set(item, "unpacking", item.size or 0)
                self._unpack(item, archive)
            finally:
                archive.unlink(missing_ok=True)
        except DownloadError as error:
            self._set(item, "failed", problem=str(error))
        except URLError as error:
            self._set(item, "failed", problem=_offline(item, error))
        except OSError as error:
            self._set(item, "failed", problem=_unsaved(item, error, self._paths.tools))
        else:
            with self._lock:
                self._progress.pop(item.id, None)
            log.info("Downloaded %s %s", item.name, item.version)

    def _fetch_checked(self, item: Download) -> Path:
        self._paths.tools.mkdir(parents=True, exist_ok=True)
        part = self._paths.tools / f"{item.id}.download"
        digest = hashlib.sha256()
        done = 0
        try:
            with self._fetch(item.url) as response, part.open("wb") as out:
                while chunk := response.read(_CHUNK):
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    self._set(item, "downloading", done)
            if done != item.size or digest.hexdigest() != item.sha256:
                raise DownloadError(
                    f"The {item.name} download didn't match what Kura expects, so Kura didn't "
                    "use it. Try again; if it happens again, the file online has changed."
                )
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        return part

    def _unpack(self, item: Download, archive: Path) -> None:
        staging = self._paths.tools / f"{item.id}.unpacking"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        try:
            with zipfile.ZipFile(archive) as zipped:
                for member in zipped.infolist():
                    name = member.filename.replace("\\", "/")
                    parts = PurePosixPath(name).parts
                    if ".." in parts or name.startswith("/") or ":" in name:
                        raise DownloadError(
                            f"The {item.name} download holds an unsafe file name, so Kura didn't "
                            "use it."
                        )
                    if member.is_dir() or len(parts) < 3 or parts[1] != item.keep:
                        continue  # only the listed folder, below the archive's top folder
                    target = staging.joinpath(*parts[2:])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zipped.open(member) as source, target.open("wb") as out:
                        shutil.copyfileobj(source, out)
            marker = {"version": item.version, "sha256": item.sha256}
            (staging / _MARKER).write_text(json.dumps(marker), encoding="utf-8")
            final = self._folder(item)
            shutil.rmtree(final, ignore_errors=True)
            staging.rename(final)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise


def _offline(item: Download, error: URLError) -> str:
    return (
        f"Kura couldn't download {item.name}: {error.reason}. "
        "Check the internet connection, then try again."
    )


def _unsaved(item: Download, error: OSError, folder: Path) -> str:
    if error.errno == errno.ENOSPC:
        size = f" ({(item.size or 0) / 1e6:.0f} MB)" if item.size else ""
        return (
            f"There isn't enough space for {item.name}{size} in {folder}. "
            "Free some, then try again."
        )
    return f"Kura couldn't save {item.name} in {folder}: {error.strerror or error}."
