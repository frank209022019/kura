"""The local HTTP API the app talks to.

Only the app can use it: the engine listens on 127.0.0.1, and every request must
carry the per-launch token the app passes in KURA_TOKEN. Each feature adds its
routes as an APIRouter in its own module, included below.
"""

import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from kura import __version__, changes, db
from kura.api import health, library, scan, settings, system, titles, tmdb, tools
from kura.config import DataPaths
from kura.scan import Scanner
from kura.tools import Tools
from kura.web import Send, send

# The app's own pages: the installed app, and the Vite dev server in development.
APP_ORIGINS = ["http://tauri.localhost", "http://localhost:1420"]
LOCAL_HOSTS = ["127.0.0.1", "localhost"]

_bearer = HTTPBearer(auto_error=False)


def create_app(
    token: str,
    paths: DataPaths,
    toolbox: Tools | None = None,
    scanner: Scanner | None = None,
    transport: Send = send,
) -> FastAPI:
    """The API, with its parts. Tests pass their own tools, scanner and transport (the
    internet as TMDB and AniList see it)."""
    expected = token.encode()

    def require_token(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> None:
        given = credentials.credentials.encode() if credentials else b""
        if not secrets.compare_digest(given, expected):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Missing or wrong token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @asynccontextmanager
    async def lifespan(running: FastAPI) -> AsyncGenerator[None]:
        with closing(db.connect(paths.database)) as conn:
            db.migrate(conn)
            changes.recover(conn)  # settle file moves that a crash interrupted
        scans: Scanner = running.state.scanner
        scans.recover()  # carry on a scan that an exit or a crash stopped
        yield

    app = FastAPI(
        title="Kura engine",
        version=__version__,
        lifespan=lifespan,
        dependencies=[Depends(require_token)],
    )
    app.state.paths = paths
    app.state.transport = transport
    app.state.tools = toolbox or Tools(paths)
    app.state.scanner = scanner or Scanner(paths, app.state.tools, transport=transport)
    # The middleware added last runs first: CORS answers the webview's preflight
    # checks, then only requests addressed to this PC get through.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=APP_ORIGINS,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(tools.router)
    app.include_router(library.router)
    app.include_router(scan.router)
    app.include_router(settings.router)
    app.include_router(system.router)
    app.include_router(tmdb.router)
    app.include_router(titles.router)
    return app


def openapi_schema() -> dict[str, Any]:
    """The API's OpenAPI schema. It doesn't depend on the token or the data folder."""
    return create_app(secrets.token_hex(), DataPaths(Path())).openapi()
