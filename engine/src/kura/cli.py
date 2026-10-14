"""Kura's command line. The app runs `kura serve`; the uninstaller runs `kura export`."""

import json
import logging
import os
import socket
import sys
import threading
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from kura import __version__, events
from kura.api import create_app, openapi_schema
from kura.config import DataPaths
from kura.export import export_data
from kura.player import Player
from kura.recovery import asked_to_stop
from kura.relocate import move_asked
from kura.system import end_programs_with_engine

app = typer.Typer(help="Kura's engine.", no_args_is_help=True, add_completion=False)


@app.command()
def version() -> None:
    """Print the engine's version."""
    typer.echo(__version__)


@app.command()
def serve(
    port: Annotated[int, typer.Option(help="Port on 127.0.0.1; 0 picks a free one.")] = 0,
    watch_stdin: Annotated[
        bool, typer.Option(help="Stop when stdin closes. The app holds it open while it runs.")
    ] = False,
) -> None:
    """Run the local API for the Kura app.

    Prints one JSON line, {"event": "ready", "port": N}, once it accepts connections.
    """
    token = os.environ.get("KURA_TOKEN")
    if not token:
        typer.echo(
            "KURA_TOKEN is not set. The Kura app sets it when it starts the engine.", err=True
        )
        raise typer.Exit(2)
    home = DataPaths.home()
    # Moved to another drive, if the owner asked, before anything opens a file there.
    paths = move_asked(home, datetime.now().astimezone())
    if paths.root != home and not paths.root.is_dir():
        missing = f"Kura's data is in {paths.root}, which isn't there."
        typer.echo(f"{missing} Connect its drive, then try again.", err=True)
        raise typer.Exit(1)
    _log_to_file(paths)
    end_programs_with_engine()  # no ffmpeg it starts outlives it, however it ends

    sock = socket.socket()
    sock.bind(("127.0.0.1", port))
    sock.listen()  # early requests wait in the queue until the server is up
    # While it runs, the engine keeps the library current and converts the queue.
    app = create_app(token, paths, watch=True, work=True, notify=events.notify)
    # A stop waits this long for open answers to end (a video playing), then ends them, so
    # Kura's care and queue stop cleanly before the app's patience runs out.
    config = uvicorn.Config(app, log_config=None, access_log=False, timeout_graceful_shutdown=2)
    server = uvicorn.Server(config)
    if watch_stdin:
        stop = threading.Thread(
            target=stop_when_stdin_closes, args=(server, paths, app.state.player), daemon=True
        )
        stop.start()
    typer.echo(json.dumps({"event": "ready", "port": sock.getsockname()[1]}))
    server.run(sockets=[sock])  # one that can't start (its records damaged) ends with 3


@app.command()
def export(folder: Annotated[Path, typer.Argument(help="Folder to write the zip into.")]) -> None:
    """Export everything Kura knows to one zip in FOLDER."""
    try:
        archive = export_data(DataPaths.default(), folder)
    except Exception as error:
        typer.echo(f"The export failed: {error}", err=True)
        raise typer.Exit(1) from error
    if archive is None:
        typer.echo("Kura has no data yet, so there is nothing to export.")
    else:
        typer.echo(f"Saved Kura's data to {archive}")


@app.command()
def openapi(path: Annotated[Path, typer.Argument(help="Where to write the schema.")]) -> None:
    """Write the API's OpenAPI schema: the contract the app's engine types follow."""
    path.write_text(json.dumps(openapi_schema(), indent=2) + "\n", encoding="utf-8", newline="\n")


def stop_when_stdin_closes(server: uvicorn.Server, paths: DataPaths, player: Player) -> None:
    """Stops the engine once the app exits and its end of the pipe closes, noting the stop was
    asked for: the app may end the engine before it's done. A video playing stops first: its
    stream would otherwise hold the stop up. Read straight from the pipe, with no buffer
    between: Python can't end cleanly while a thread holds one."""
    stdin = sys.stdin.fileno()
    while os.read(stdin, 4096):
        pass
    asked_to_stop(paths)
    player.stop()
    server.should_exit = True


def _log_to_file(paths: DataPaths) -> None:
    paths.logs.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        paths.logs / "engine.log", when="midnight", backupCount=30, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
