"""What every API module shares: the payload base class and the dependencies."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from typing import Annotated

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from kura import db
from kura.config import DataPaths
from kura.scan import Scanner
from kura.tools import Tools
from kura.web import Send


class ApiModel(BaseModel):
    """Base for everything the API sends and receives: snake_case here, camelCase in JSON."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        serialize_by_alias=True,
    )


def _paths(request: Request) -> DataPaths:
    paths: DataPaths = request.app.state.paths
    return paths


def _database(paths: Annotated[DataPaths, Depends(_paths)]) -> Iterator[sqlite3.Connection]:
    with closing(db.connect(paths.database)) as conn:
        yield conn


def _toolbox(request: Request) -> Tools:
    toolbox: Tools = request.app.state.tools
    return toolbox


def _scanner(request: Request) -> Scanner:
    scanner: Scanner = request.app.state.scanner
    return scanner


def _transport(request: Request) -> Send:
    transport: Send = request.app.state.transport
    return transport


# Use these as parameter types in routes, e.g. `def route(conn: Database) -> ...`.
Paths = Annotated[DataPaths, Depends(_paths)]
Database = Annotated[sqlite3.Connection, Depends(_database)]
Toolbox = Annotated[Tools, Depends(_toolbox)]
Scans = Annotated[Scanner, Depends(_scanner)]
Web = Annotated[Send, Depends(_transport)]  # how Kura reaches TMDB and AniList
