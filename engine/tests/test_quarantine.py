"""Clearing out what was set aside once the owner's days are up: copies, and converted files'
originals. What's cleared can't be put back; the rest of its tidy-up can."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kura.changes import ChangeState, apply_plan, changes_of, save_plan, undo_plan
from kura.core.library import QUARANTINE_FOLDER
from kura.core.plan import Change, ChangeKind, Plan
from kura.quarantine import clear_out

pytestmark = pytest.mark.usefixtures("quarantine")

NOW = datetime(2026, 10, 11, 9, 30, tzinfo=UTC)


def set_aside(conn: sqlite3.Connection, tmp_path: Path, name: str, days_ago: int) -> int:
    """A tidy-up, applied `days_ago`, that set a copy aside and filed the kept one."""
    copy, kept = tmp_path / f"{name} (copy).mkv", tmp_path / f"{name}.mkv"
    copy.write_bytes(b"copy")
    kept.write_bytes(b"kept")
    place = Path(tmp_path.anchor) / QUARANTINE_FOLDER / NOW.date().isoformat() / copy.name
    plan = Plan(
        (
            Change(ChangeKind.QUARANTINE, copy, place, f"{name} · duplicate", "Kept the other"),
            Change(ChangeKind.MOVE, kept, tmp_path / "Filed" / kept.name, name, "Named and filed"),
        )
    )
    plan_id = save_plan(conn, plan, f"Tidied {name}", now=NOW)
    when = NOW - timedelta(days=days_ago)
    apply_plan(conn, plan_id, now=when)
    return plan_id


def test_what_was_set_aside_longer_than_the_owner_keeps_it_goes(
    conn: sqlite3.Connection, tmp_path: Path
):
    old = set_aside(conn, tmp_path, "Old", days_ago=31)
    recent = set_aside(conn, tmp_path, "Recent", days_ago=10)

    cleared = clear_out(conn, days=30, now=NOW)

    assert cleared == 1
    [old_copy, _] = changes_of(conn, old)
    [recent_copy, _] = changes_of(conn, recent)
    assert not old_copy.target.exists()
    assert old_copy.cleared_at is not None
    assert recent_copy.target.exists()
    assert recent_copy.cleared_at is None


def test_kept_for_good_nothing_goes(conn: sqlite3.Connection, tmp_path: Path):
    set_aside(conn, tmp_path, "Old", days_ago=400)

    assert clear_out(conn, days=None, now=NOW) == 0


def test_undoing_puts_back_what_it_can_once_a_copy_is_cleared(
    conn: sqlite3.Connection, tmp_path: Path
):
    plan_id = set_aside(conn, tmp_path, "Old", days_ago=31)
    clear_out(conn, days=30, now=NOW)

    outcome = undo_plan(conn, plan_id, now=NOW)

    assert ([c.kind for c in outcome.changed], outcome.problems) == ([ChangeKind.MOVE], ())
    assert (tmp_path / "Old.mkv").exists()
    states = [c.state for c in changes_of(conn, plan_id)]
    assert states == [ChangeState.DONE, ChangeState.UNDONE]  # the copy is gone for good
    undone = conn.execute("SELECT undone_at FROM plans WHERE id = ?", (plan_id,)).fetchone()[0]
    assert undone is not None  # nothing more can come back


def test_an_original_whose_converted_file_never_went_in_is_kept(
    conn: sqlite3.Connection, tmp_path: Path
):
    original, work = tmp_path / "Ep01.mkv", tmp_path / "Ep01.kura-converting"
    original.write_bytes(b"the original")
    work.write_bytes(b"the result")
    (tmp_path / "Ep01 taken.mkv").write_bytes(b"in the way")
    place = Path(tmp_path.anchor) / QUARANTINE_FOLDER / NOW.date().isoformat() / original.name
    plan = Plan(
        (
            Change(ChangeKind.QUARANTINE, original, place, "Ep01 · original", "Converted"),
            Change(ChangeKind.MOVE, work, tmp_path / "Ep01 taken.mkv", "Ep01", "Converted"),
        )
    )
    plan_id = save_plan(conn, plan, "Converted Ep01", now=NOW, kind="convert")
    apply_plan(conn, plan_id, now=NOW - timedelta(days=40))  # the result couldn't go in

    assert clear_out(conn, days=30, now=NOW) == 0
    assert place.exists()  # the only copy of the episode now
