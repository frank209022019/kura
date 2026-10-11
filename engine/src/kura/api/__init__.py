"""The local HTTP API the app talks to.

Only the app can use it: the engine listens on 127.0.0.1, and every request must
carry the per-launch token the app passes in KURA_TOKEN. Each feature adds its
routes as an APIRouter in its own module, included below.
"""

import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, closing
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from kura import __version__, changes, db
from kura.anilist import AniList
from kura.api import (
    backups,
    convert,
    data,
    health,
    library,
    review,
    scan,
    settings,
    system,
    tidy,
    titles,
    tmdb,
    tools,
)
from kura.backups import restore_asked
from kura.cache import Cache
from kura.care import Care
from kura.config import DataPaths
from kura.gpu import Gpu
from kura.queue import Queue, programs_from
from kura.scan import Scanner
from kura.tools import Tools
from kura.watch import Watcher
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
    *,
    watch: bool = False,
    work: bool = False,
) -> FastAPI:
    """The API, with its parts. Tests pass their own tools, scanner and transport (the
    internet as TMDB and AniList see it). `watch` keeps the library current while the engine
    runs (kura/watch.py), and `work` converts the queue (kura/queue.py): `kura serve` turns
    both on."""
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
        restore_asked(paths, _now())  # a backup the owner chose, before anything opens the database
        with closing(db.connect(paths.database)) as conn:
            db.migrate(conn)
            changes.recover(conn)  # settle file moves that a crash interrupted
        worker: Queue = running.state.queue
        if work:
            # A conversion a crash stopped while its result was taking the original's place is
            # finished or undone before any scan looks at the folders.
            worker.recover()
        scans: Scanner = running.state.scanner
        scans.recover()  # carry on a scan that an exit or a crash stopped
        anilist: AniList = running.state.anilist
        watcher = Watcher(paths, scans, transport, now=_now, anilist=anilist) if watch else None
        running.state.watcher = watcher
        if watcher is not None:
            watcher.start()
        care: Care = running.state.care
        if work:
            worker.start()  # converts what waits
            care.start()  # tonight's backup, and the quarantine cleared out daily
        yield
        if work:
            care.stop()
            worker.stop()  # the file converting now is first in line next time
        if watcher is not None:
            watcher.stop()

    app = FastAPI(
        title="Kura engine",
        version=__version__,
        lifespan=lifespan,
        dependencies=[Depends(require_token)],
    )
    app.state.paths = paths
    app.state.transport = transport
    app.state.tools = toolbox or Tools(paths)
    # One AniList client for the engine: its limit (about 30 requests a minute) is the engine's.
    app.state.anilist = AniList(transport, cache=Cache(paths.cache))
    app.state.scanner = scanner or Scanner(
        paths, app.state.tools, transport=transport, anilist=app.state.anilist
    )
    app.state.watcher = None  # set while it runs
    # What converting runs: Kura's ffmpeg, the AI model and Anime4K's shader (tests stand in).
    app.state.programs = lambda: programs_from(app.state.tools)
    app.state.queue = Queue(paths, app.state.scanner, lambda: app.state.programs(), now=_now)
    app.state.gpu = Gpu()
    app.state.care = Care(paths, app.state.scanner.hold, now=_now)
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
    app.include_router(review.router)
    app.include_router(tidy.router)
    app.include_router(convert.router)
    app.include_router(data.router)
    app.include_router(backups.router)
    return app


def _now() -> datetime:
    return datetime.now().astimezone()


def openapi_schema() -> dict[str, Any]:
    """The API's OpenAPI schema. It doesn't depend on the token or the data folder."""
    return create_app(secrets.token_hex(), DataPaths(Path())).openapi()
