"""Settings > Your data > Backups: the nightly backups of Kura's records, one made now, and one
restored, which happens as the engine starts again (the app starts it again right after)."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from kura import backups
from kura.api.common import ApiModel, Database, Paths

router = APIRouter()


class Backup(ApiModel):
    name: str  # "kura 2026-10-11 0300.db"
    made: str  # local time, to the minute: "2026-10-11T03:00"
    size: int
    before_restoring: bool  # made just before another backup was restored


class Restored(ApiModel):
    name: str  # the backup
    at: str  # when
    problem: str | None  # why it couldn't be restored, if it couldn't


class Backups(ApiModel):
    backups: list[Backup]  # newest first
    restored: Restored | None  # how the last restore went


@router.get("/backups")
def list_backups(conn: Database, paths: Paths) -> Backups:
    last = backups.last_restore(conn)
    return Backups(
        backups=[_backup(backup) for backup in backups.backups(paths)],
        restored=Restored(name=last.name, at=last.at, problem=last.problem) if last else None,
    )


@router.post("/backups")
def back_up_now(paths: Paths) -> Backup:
    """Makes a backup now, checked like the nightly ones."""
    try:
        made = backups.back_up(paths, datetime.now().astimezone())
    except backups.BackupError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return _backup(made)


@router.post("/backups/{name}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_backup(name: str, paths: Paths) -> None:
    """Restores a backup as the engine starts again: the app starts it again right after."""
    try:
        backups.ask_to_restore(paths, name)
    except backups.BackupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None


def _backup(backup: backups.Backup) -> Backup:
    return Backup(
        name=backup.name,
        made=backup.made.isoformat(timespec="minutes"),
        size=backup.size,
        before_restoring=backup.before_restoring,
    )
