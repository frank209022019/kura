import json
import os
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import httpx2
import pytest
from typer.testing import CliRunner

from kura import __version__, db
from kura.cli import app
from kura.config import DataPaths
from kura.relocate import ask_to_move
from tests.conftest import TOKEN

runner = CliRunner()


def test_version_prints_the_engine_version():
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_serve_needs_the_token_from_the_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("KURA_TOKEN", raising=False)

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 2
    assert "KURA_TOKEN is not set" in result.stderr


def _engine() -> list[str]:
    """The engine from source, or the bundled build when KURA_ENGINE_EXE names it."""
    if bundled := os.environ.get("KURA_ENGINE_EXE"):
        return [str(Path(bundled).resolve())]
    return [sys.executable, "-m", "kura"]


def test_serve_announces_its_port_and_stops_when_the_app_goes_away(tmp_path: Path):
    """The handshake the app's shell relies on (see app/src-tauri/src/engine.rs)."""
    env = {**os.environ, "KURA_TOKEN": TOKEN, "KURA_DATA_DIR": str(tmp_path / "Kura")}
    command = [*_engine(), "serve", "--watch-stdin"]
    with subprocess.Popen(
        command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    ) as engine:
        assert engine.stdin is not None
        assert engine.stdout is not None
        ready = json.loads(engine.stdout.readline())
        assert ready["event"] == "ready"

        response = httpx2.get(
            f"http://127.0.0.1:{ready['port']}/health",
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=30,
        )
        assert response.status_code == 200

        engine.stdin.close()
        assert engine.wait(timeout=30) == 0


def test_an_engine_that_cant_start_says_so_and_ends_cleanly(tmp_path: Path):
    """Its records damaged past opening: it announced its port, then couldn't start."""
    home = tmp_path / "Kura"
    home.mkdir()
    (home / "kura.db").write_bytes(b"not a database at all" * 200)
    env = {**os.environ, "KURA_TOKEN": TOKEN, "KURA_DATA_DIR": str(home)}
    command = [*_engine(), "serve", "--watch-stdin"]
    with subprocess.Popen(
        command,
        env=env,
        stdin=subprocess.PIPE,  # held open, as the app holds it, while the engine ends
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as engine:
        assert engine.stdout is not None
        assert engine.stderr is not None
        engine.stdout.read()
        said = engine.stderr.read()
        code = engine.wait(timeout=60)

    assert code == 3  # uvicorn's for a start that failed: an ending, not a crash
    assert "Fatal Python error" not in said


def test_export_says_when_there_is_nothing_yet(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("KURA_DATA_DIR", str(tmp_path / "Kura"))

    result = runner.invoke(app, ["export", str(tmp_path / "exports")])

    assert result.exit_code == 0
    assert result.stdout.strip() == "Kura has no data yet, so there is nothing to export."


def test_export_says_where_it_saved_the_zip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("KURA_DATA_DIR", str(tmp_path / "Kura"))
    with closing(db.connect(DataPaths.default().database)) as conn:
        db.migrate(conn)

    result = runner.invoke(app, ["export", str(tmp_path / "exports")])

    assert result.exit_code == 0
    assert result.stdout.startswith(f"Saved Kura's data to {tmp_path / 'exports'}")


def test_serve_moves_the_data_asked_for_before_it_starts(tmp_path: Path):
    home, target = tmp_path / "Kura", tmp_path / "F" / "Kura data"
    paths = DataPaths(home)
    with closing(db.connect(paths.database)) as conn:
        db.migrate(conn)
    ask_to_move(paths, target)
    env = {**os.environ, "KURA_TOKEN": TOKEN, "KURA_DATA_DIR": str(home)}
    command = [*_engine(), "serve", "--watch-stdin"]
    with subprocess.Popen(
        command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    ) as engine:
        assert engine.stdin is not None
        assert engine.stdout is not None
        assert json.loads(engine.stdout.readline())["event"] == "ready"
        engine.stdin.close()
        assert engine.wait(timeout=30) == 0

    assert (target / "kura.db").is_file()
    assert (target / "logs" / "engine.log").is_file()  # it logged in the new place
    assert sorted(path.name for path in home.iterdir()) == ["location.txt"]


def test_serve_says_so_when_the_drive_the_data_moved_to_isnt_there(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    home = tmp_path / "Kura"
    home.mkdir()
    (home / "location.txt").write_text(str(tmp_path / "Unplugged" / "Kura data"), "utf-8")
    monkeypatch.setenv("KURA_DATA_DIR", str(home))
    monkeypatch.setenv("KURA_TOKEN", TOKEN)

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 1
    assert "which isn't there. Connect its drive, then try again." in result.stderr
