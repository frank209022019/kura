"""Runs the command line for `python -m kura` and the bundled kura-engine.exe."""

from kura.cli import app

if __name__ == "__main__":
    app(prog_name="kura")
