"""GET /health: is the engine up, which version is it, and where is its data."""

from typing import Literal

from fastapi import APIRouter

from kura import __version__, db
from kura.api.common import ApiModel, Database, Paths

router = APIRouter()


class Health(ApiModel):
    status: Literal["ok"]
    version: str
    data_dir: str
    schema_version: int


@router.get("/health")
def health(paths: Paths, conn: Database) -> Health:
    return Health(
        status="ok",
        version=__version__,
        data_dir=str(paths.root),
        schema_version=db.schema_version(conn),
    )
