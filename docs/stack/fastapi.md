# FastAPI, Uvicorn, Pydantic and Typer (the engine's API and CLI)

The engine answers the UI through a local HTTP API built with [FastAPI](https://fastapi.tiangolo.com)
and served by [Uvicorn](https://www.uvicorn.org); payloads are [Pydantic](https://docs.pydantic.dev)
models. Its command line is [Typer](https://typer.tiangolo.com).

## Files

| File | What it holds |
| --- | --- |
| `kura/cli.py` | The commands: `serve`, `export`, `openapi`, `version` |
| `kura/api/__init__.py` | `create_app()`: token check, CORS, host check, migrations at start, routers |
| `kura/api/common.py` | `ApiModel` and the shared dependencies `Paths` and `Database` |
| `kura/api/health.py` | `GET /health`, the first route and the template for the rest |
| `engine/openapi.json` | The API's schema, committed as the contract with the UI |

## The command line

```powershell
uv run kura --help
uv run kura serve --port 8765 --watch-stdin   # what the shell runs (port 0 picks a free one)
uv run kura export "D:\Backups"               # one zip of everything
uv run kura openapi openapi.json              # rewrite the API snapshot
```

Each command is a typed function in `cli.py`; Typer builds the help from the docstrings and
`Annotated` options. `serve` needs `KURA_TOKEN`; it binds `127.0.0.1`, prints the ready line as
JSON, logs to `logs/engine.log`, and with `--watch-stdin` stops when its stdin closes.

## The API

- **Every request needs the token**: `Authorization: Bearer <token>`, compared in constant time.
  `HTTPBearer` makes the scheme visible in the schema; anything else gets 401.
- **Only the app may call it**: CORS allows `http://tauri.localhost` (installed) and
  `http://localhost:1420` (development); `TrustedHostMiddleware` accepts only requests addressed to
  `127.0.0.1` or `localhost`.
- **Migrations run at start-up** (the lifespan), before the first request is answered.
- **JSON is camelCase.** Models inherit `ApiModel`, which keeps snake_case in Python and uses
  camelCase on the wire.

### Adding a route

1. Create `kura/api/<feature>.py` with an `APIRouter`, `ApiModel` response models and plain
   functions. Ask for what you need with the shared dependencies:

   ```python
   @router.get("/library")
   def library(conn: Database) -> Library: ...
   ```

2. Include the router in `create_app()`.
3. Test it through `TestClient` (the `client` fixture already sends the token).
4. Run `uv run kura openapi openapi.json`, then mirror the new types in `app/src/lib/engine.tsx`.

Keep route functions thin: read the request, call the core and the database, return a model. Use
`def` routes (FastAPI runs them in a thread pool); `async def` only for work that awaits.

## Upgrading

`uv lock --upgrade`, then `uv run pytest`. Starlette's test client now uses `httpx2` (the dev
dependency), not `httpx`. If the schema changes, the OpenAPI snapshot test says so.
