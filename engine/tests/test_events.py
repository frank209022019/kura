"""What the engine tells the app on its standard output, after the ready line."""

import json

import pytest

from kura.events import notify


def test_a_notification_is_one_json_line_in_plain_ascii(capsys: pytest.CaptureFixture[str]):
    notify("Trigun, season 1 is done", "26 episodes · all checked · 6.1 GB → 11.7 GB")

    line = capsys.readouterr().out
    assert line.endswith("\n")
    assert line.isascii()  # whatever code page Windows gives the pipe
    assert json.loads(line) == {
        "event": "notify",
        "title": "Trigun, season 1 is done",
        "body": "26 episodes · all checked · 6.1 GB → 11.7 GB",
    }
