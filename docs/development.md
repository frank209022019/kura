# Development

How to set up a Windows PC for Kura, run it, check it and keep it current.

## Set up once

| Tool | Why | Get it |
| --- | --- | --- |
| Visual Studio Build Tools 2022, "Desktop development with C++" | Rust's linker and the Windows SDK | `winget install Microsoft.VisualStudio.2022.BuildTools` |
| Rust (stable) | The shell | [rustup.rs](https://rustup.rs), then `rustup component add clippy rustfmt` |
| Node.js LTS | The UI's tooling | `winget install OpenJS.NodeJS.LTS` |
| pnpm 12 | UI packages | `npm install -g pnpm@latest` |
| uv | Python and the engine's packages | `winget install astral-sh.uv` (uv installs Python 3.14 itself) |
| GitHub CLI, signed in | Pushing, releases and watching CI | `winget install GitHub.cli`, then `gh auth login` |

Then, from the repo:

```powershell
cd engine; uv sync          # Python 3.14, the engine and its dev tools
cd ../app; pnpm install     # the UI, Tauri's CLI and Biome
```

WebView2, which draws the window, is part of Windows 11.

## Run Kura

```powershell
cd app; pnpm tauri dev
```

This starts Vite (the UI with hot reload), builds and opens the shell, and the shell starts the
engine from source with `uv run`. Engine data goes to `engine/.dev-data`, never to the real
`%LOCALAPPDATA%\Kura`. Rust and Python changes need a restart; UI changes appear as you save.

To work on the engine alone:

```powershell
cd engine
$env:KURA_TOKEN = "dev"; $env:KURA_DATA_DIR = ".dev-data"
uv run kura serve --port 8765        # then call http://127.0.0.1:8765/health with "Authorization: Bearer dev"
uv run kura --help                   # every command
```

## Check your work

CI runs exactly these; run them before every push.

```powershell
cd engine; uv run ruff format --check; uv run ruff check; uv run pyright; uv run pytest
cd app; pnpm check; pnpm build
cd app/src-tauri; cargo fmt --check; cargo clippy --all-targets -- -D warnings; cargo test
```

`pnpm check` runs Biome, the TypeScript compiler and Vitest. To fix formatting:
`uv run ruff format` and `uv run ruff check --fix` in `engine/`, `pnpm fix` in `app/`, `cargo fmt` in
`app/src-tauri/`.

## Common changes

**A new API endpoint.** Add a router module in `engine/src/kura/api/` (see `health.py`) and include
it in `api/__init__.py`. Test it in `engine/tests/`. Run `uv run kura openapi openapi.json`, then add
the matching type and hook to `app/src/lib/engine.tsx`. Commit both sides together.

**A schema change.** Append a migration to `engine/src/kura/migrations.py`; never edit one that has
shipped. Add a test, and include the new data in `export.py`.

**A new screen.** Build it in `app/src/features/<area>/` to its board in [design/](design/), using
the tokens and existing components. Add the route in `app/src/app.tsx`. Give it its empty, loading
and error states.

**A new tool or library.** Use its latest stable version and add a page (or a section) in
[stack/](stack/) saying how Kura uses it.

## Updating dependencies

Kura stays on the latest versions. There is no Dependabot (it would open branches), so update on
`main`, ideally every couple of weeks:

```powershell
uv self update; cd engine; uv lock --upgrade; uv sync    # Python packages
cd ../app; pnpm update --latest                          # npm packages
cd src-tauri; rustup update; cargo update                # Rust and crates
```

Raise the minimum versions in `pyproject.toml`, `package.json` and `Cargo.toml` to match, run every
check, skim the changelogs of anything that jumped a major version, and update the versions table in
[docs/README.md](README.md). Pinned GitHub Actions are updated the same way: look up each action's
latest release and change the SHA and the version comment. pnpm refuses packages younger than a day
(a supply-chain safeguard); if the newest release is that fresh, take the one before it.

## Troubleshooting

**"Are you sure you have RC.EXE in your $PATH" when building the shell.** Rust finds the Windows
SDK's resource compiler through the registry, and on some PCs that entry points at the wrong
folder. Set the user variable `RC` to rc.exe, then open a new terminal:

```powershell
[Environment]::SetEnvironmentVariable('RC', 'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\rc.exe', 'User')
```

**The window says "Kura's engine isn't running".** "Copy details" (when shown) has the engine's last error lines.
In development, run `uv sync` in `engine/`; the engine's own log is `engine/.dev-data/logs/engine.log`.

**Port 1420 is busy.** A previous `pnpm tauri dev` left Vite running; close it or end the `node`
process using that port.
