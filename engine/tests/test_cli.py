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
