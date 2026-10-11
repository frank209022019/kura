"""The tools Kura downloads on first run: ffmpeg, checked, unpacked and found again."""

import hashlib
import io
import re
import zipfile
from dataclasses import replace
from pathlib import Path
from urllib.error import URLError

import pytest

from kura.config import DataPaths
from kura.tools import Download, Tools, manifest

PROGRAM = "ffprobe.exe"


def archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        for name, data in files.items():
            zipped.writestr(name, data)
    return buffer.getvalue()


BUILD = archive(
    {
        "ffmpeg-n9.0-win64-lgpl-shared/bin/ffprobe.exe": b"probe",
        "ffmpeg-n9.0-win64-lgpl-shared/bin/ffmpeg.exe": b"mpeg",
        "ffmpeg-n9.0-win64-lgpl-shared/bin/avcodec-63.dll": b"codecs",
        "ffmpeg-n9.0-win64-lgpl-shared/doc/ffmpeg.html": b"docs",
    }
)


def listing(data: bytes, version: str = "9.0.2") -> Download:
    """The ffmpeg entry, pointing at `data` instead of the real build."""
    ffmpeg = next(item for item in manifest() if item.id == "ffmpeg")
    return replace(ffmpeg, version=version, size=len(data), sha256=hashlib.sha256(data).hexdigest())


def serving(data: bytes):
    def fetch(url: str) -> io.BytesIO:
        return io.BytesIO(data)

    return fetch


def offline(url: str) -> io.BytesIO:
    raise URLError("No connection could be made")


def downloaded(tools: Tools, tool: str = "ffmpeg") -> None:
    tools.start(tool)
    tools.wait(tool, timeout=10)


def test_the_list_says_what_each_download_is_and_where_it_comes_from():
    items = manifest()

    assert [item.id for item in items] == ["webview2", "ffmpeg"]
    for item in items:
        assert item.url.startswith("https://")
        assert all((item.name, item.purpose, item.licence, item.home))
    for item in (item for item in items if item.by == "kura"):
        assert (item.size or 0) > 0
        assert re.fullmatch(r"[0-9a-f]{64}", item.sha256 or "")
        assert item.keep


def test_ffmpeg_is_pinned_to_one_build_that_stays_online():
    ffmpeg = next(item for item in manifest() if item.id == "ffmpeg")

    # BtbN keeps each month's last build for two years; "latest" changes every day.
    assert "/autobuild-" in ffmpeg.url
    assert "latest" not in ffmpeg.url
    assert ffmpeg.licence == "LGPL-2.1-or-later"


def test_only_kuras_own_downloads_are_offered_by_the_engine(paths: DataPaths):
    tools = Tools(paths, fetch=serving(BUILD))

    assert [item.id for item, _ in tools.status()] == ["ffmpeg"]
    with pytest.raises(KeyError):
        tools.start("webview2")


def test_a_tool_is_downloaded_checked_and_unpacked_into_the_data_folder(paths: DataPaths):
    tools = Tools(paths, items=(listing(BUILD),), fetch=serving(BUILD))
    assert tools.path("ffprobe") is None

    downloaded(tools)

    [(_, progress)] = tools.status()
    assert progress.state == "ready"
    assert progress.done == len(BUILD)
    assert tools.path("ffprobe") == paths.tools / "ffmpeg" / PROGRAM
    assert (paths.tools / "ffmpeg" / "avcodec-63.dll").read_bytes() == b"codecs"
    assert not (paths.tools / "ffmpeg" / "ffmpeg.html").exists()  # only the bin folder is kept
    assert [file.name for file in paths.tools.iterdir()] == ["ffmpeg"]  # no download left behind


def test_a_download_that_doesnt_match_the_list_is_thrown_away(paths: DataPaths):
    tampered = BUILD + b"!"
    tools = Tools(paths, items=(listing(BUILD),), fetch=serving(tampered))

    downloaded(tools)

    [(_, progress)] = tools.status()
    assert progress.state == "failed"
    assert progress.problem == (
        "The ffmpeg download didn't match what Kura expects, so Kura didn't use it. "
        "Try again; if it happens again, the file online has changed."
    )
    assert tools.path("ffprobe") is None
    assert not any(paths.tools.iterdir())


def test_no_connection_says_so_and_a_retry_works(paths: DataPaths):
    item = listing(BUILD)
    tools = Tools(paths, items=(item,), fetch=offline)

    downloaded(tools)

    [(_, progress)] = tools.status()
    assert progress.state == "failed"
    assert progress.problem == (
        "Kura couldn't download ffmpeg: No connection could be made. "
        "Check the internet connection, then try again."
    )

    retry = Tools(paths, items=(item,), fetch=serving(BUILD))
    downloaded(retry)
    assert retry.path("ffprobe") is not None


def test_an_archive_cant_write_outside_the_tools_folder(paths: DataPaths):
    sneaky = archive({"ffmpeg/bin/ffprobe.exe": b"probe", "ffmpeg/bin/../../../escaped.txt": b"x"})
    tools = Tools(paths, items=(listing(sneaky),), fetch=serving(sneaky))

    downloaded(tools)

    [(_, progress)] = tools.status()
    assert progress.state == "failed"
    assert "unsafe" in (progress.problem or "")
    assert not (paths.root / "escaped.txt").exists()
    assert not (paths.root.parent / "escaped.txt").exists()


def test_a_newer_build_in_the_list_replaces_the_one_installed(paths: DataPaths):
    downloaded(Tools(paths, items=(listing(BUILD),), fetch=serving(BUILD)))
    newer = archive({"ffmpeg-n9.1/bin/ffprobe.exe": b"newer probe"})
    tools = Tools(paths, items=(listing(newer, version="9.1.0"),), fetch=serving(newer))

    [(_, before)] = tools.status()
    assert before.state == "missing"  # the installed build isn't the one listed any more
    downloaded(tools)

    assert (paths.tools / "ffmpeg" / PROGRAM).read_bytes() == b"newer probe"
    assert not (paths.tools / "ffmpeg" / "avcodec-63.dll").exists()


def test_a_development_copy_of_ffmpeg_can_stand_in(
    paths: DataPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    own = tmp_path / "ffmpeg-bin"
    own.mkdir()
    (own / PROGRAM).write_bytes(b"probe")
    monkeypatch.setenv("KURA_FFMPEG_DIR", str(own))

    tools = Tools(paths, items=(listing(BUILD),), fetch=offline)

    [(_, progress)] = tools.status()
    assert progress.state == "ready"
    assert tools.path("ffprobe") == own / PROGRAM
