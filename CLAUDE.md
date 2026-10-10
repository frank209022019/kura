# Kura

Kura (蔵, "storehouse") is a personal Windows app for one person's anime library. It maps folders
in any layout, identifies every file, reports what is missing or broken, renames for Plex, and
converts the whole library to one standard, with AI upscaling for SD sources. It is the owner's
own tool: one user, one PC, never commercial, no sign-in. The code is shared under the MIT
licence: anyone may fork it, but the repo takes no contributions.

**Where it stands (2026-10-10):** design language chosen, repo, CI, installer and updater pipeline
set up, and the engine's pure core (names, Plex naming, standards, estimates, gap reports, tidy
plans) built test first. No library features in the app yet: the engine serves `/health` and
exports, the app shows its shell. The repo is about to go public; it stays private until the owner
decides how to clean old commits (they hold a personal email address). Next is the first build
step in [What's next](#whats-next).

## Ground rules

- **One branch.** Work on `main` in `C:\GitHub\kura`. No feature branches, worktrees or PRs unless
  the owner asks. Commit and push to `main` once every check passes. If another session is working
  at the same time, stage only your own files (never `git add -A`).
- **Never change the Cinema look unasked.** Colours, type, shapes and motion come from the design
  canvas and live in [app/src/styles/tokens.css](app/src/styles/tokens.css). The owner: "do not
  change the color or anything".
- **Nothing changes until the owner reviews it.** Renames, moves, deletions and conversions are
  proposed first, applied only when approved, logged, and undoable. Duplicates and replaced
  originals go to quarantine (30 days), never straight to deletion. Anime files are never touched
  by uninstalling.
- **Kura is personal.** No company names anywhere: publisher, docs, accounts, signing.
  The publisher name is "Kura".
- **Only ship what Kura may share.** Kura is MIT. A dependency's licence must be on the allowed
  list in [engine/tools/third_party_notices.py](engine/tools/third_party_notices.py) (the
  installer build stops otherwise); code adapted from elsewhere keeps its notice (shadcn/ui:
  `app/src/components/ui/LICENSE-shadcn.txt`); no anime, artwork or other media in the repo or the
  installer, and titles appear only as file-name examples.
- **Latest versions.** Use the newest stable release of every tool and library, and keep them
  current (see "Updating dependencies" in [docs/development.md](docs/development.md)).
- **Fix what you find.** A real fault found while working is fixed in the same piece of work, test
  first. Ask only about what is genuinely the owner's call: scope, money, anything irreversible or
  public.
- **Scoping means talking.** When the owner asks "is it possible…" or is scoping, answer in the
  conversation: no code, scripts or long checks.
- **Simple beats clever.** The bar is Revolut or Linear: few elements, one clear primary action,
  plain language, motion that explains. Code follows the same bar: small modules, obvious names.

## Layout

```
AGENTS.md       the guide for coding agents; each area below has its own AGENTS.md
LICENSE         MIT
app/            the desktop app
  src/            React UI (TypeScript): components/, features/, lib/, styles/
  src-tauri/      Tauri shell (Rust): window, engine process, updates, installer config
engine/         the engine (Python): src/kura/, tests/, tools/ (build tools), kura-engine.spec,
                openapi.json
docs/           how it all works; docs/design/ holds the screens
scripts/        set-version.mjs, design-snapshot.mjs
.github/        CI and release workflows
```

## Commands

Run the app (Vite, the Rust shell, and the engine from source):

```powershell
cd app; pnpm tauri dev
```

Check everything CI checks (each line from the repo root):

```powershell
cd engine; uv run ruff format --check; uv run ruff check; uv run pyright; uv run pytest
cd app; pnpm check; pnpm build
cd app/src-tauri; cargo fmt --check; cargo clippy --all-targets -- -D warnings; cargo test
```

Fix formatting: `uv run ruff format` (engine), `pnpm fix` (app), `cargo fmt` (shell).
Build the installer locally: `cd app; pnpm build:installer` (needs the signing key, see
[docs/releasing.md](docs/releasing.md)). Release: `node scripts/set-version.mjs 1.2.3`, commit,
then `git tag v1.2.3; git push origin main v1.2.3`. A tag reaches every installed copy, so
releasing is the owner's call.

## How it fits together

- **Shell** (`app/src-tauri`, Tauri 2, Rust): the window with its own title bar, one instance only.
  It starts the engine with a fresh token, tells the UI where it is, stops it on exit, and installs
  updates. Keep it thin.
- **UI** (`app/src`, React 19, Tailwind 4): talks to the engine over HTTP on 127.0.0.1 with the
  token. Server data goes through TanStack Query; screens live in `features/`.
- **Engine** (`engine/`, Python 3.14): everything else. A FastAPI app (`kura serve`) and a CLI
  (`kura export`, …), bundled by PyInstaller as a folder with its own Python. Library logic goes in
  `kura/core` as pure functions with no I/O; the code around it does files, network and database.
- **Data**: one SQLite file, `%LOCALAPPDATA%\Kura\kura.db`, upgraded by append-only migrations in
  `kura/migrations.py`. Development uses `engine/.dev-data` instead, never the real folder.
- **Contracts**: the engine's API is snapshotted in `engine/openapi.json` (a test fails when it
  drifts); the UI's types in `app/src/lib/engine.tsx` mirror it by hand. Change both together.

Details: [docs/architecture.md](docs/architecture.md).

## Decisions

Everything decided so far. Don't ask again; change only with the owner.

**The product**
- Point Kura at folders in any layout: one anime per folder, franchise sub-folders, or many anime
  mixed in one folder. Files live on local drives; the library is many episodes across many anime.
- It analyses every file, identifies it from free sources (TMDB, AniList, the offline manami
  database) with artwork, reports gaps and health (a Markdown report per anime), renames for Plex,
  quarantines duplicates, and converts everything to one standard with a preview and estimates.
- Conversion history is kept "last modified" style. Installer, auto-updater, and an uninstaller that
  offers an export first.
- The pilot library is the whole Dragon Ball franchise (not on the PC yet).
- Plex naming. Watched mostly on the PC; Plex or a phone maybe later.
- Picture: crisp and clean; 720p or 1080p are both fine. **Every** file goes to the library standard,
  even 720p to 720p; a file already exactly at the standard is only renamed.
- "A simple tool, but we don't want to struggle with small things": empty, error and recovery
  states are designed, not afterthoughts (see the "small things" screen).
- Order of work: design language (done), repo and pipelines (done), then building.

**Design: Cinema** (the owner's pick of three; tokens in `app/src/styles/tokens.css`)
- Dark first: window #0b0c0f, glass panels white at 4% with 8% borders, text #f4f5f7 and #a3a8b3.
- One amber accent #f2b33d (text on it #1d1300, amber text #ffd27a). Featured panel blue #13254f
  with an orange orb #f08a24.
- Manrope for words, Geist Mono for paths, sizes and times. Pill buttons; panels 16 to 24 px round.
- Status by shape first: ready solid amber, converting pulsing, to convert solid blue #4f73b3,
  broken hatched, missing hollow.
- Motion: 120 ms hover and press, 200 ms toggles, 320 ms panels, 600 to 900 ms charts, one curve
  `cubic-bezier(.2,.8,.2,1)`, and none at all when Windows' animation effects are off.
- Light mode has base tokens only; Kura runs dark until light mode is designed.
- Canvases: [Kura Workflows](https://claude.ai/artifact/XgGkfpW6doBUPcnrPqrbxb) (13 boards, the source
  of truth for screens) and the [options record](https://claude.ai/artifact/NWe6abnPRYCn6BGTVK25za).
  Snapshots in [docs/design/](docs/design/).

**Architecture**
- Tauri 2 shell, React + Tailwind + shadcn/ui (restyled to Cinema) UI, Python engine sidecar built
  with PyInstaller as a folder (fast start; ships its own Python). Local API with a per-launch token,
  plus a CLI. SQLite for data.
- A pure core behind small interfaces: parse → match → plan → check → estimate.
- Identification: anitopy parses names (chosen over guessit and aniparse after testing them on
  real names, see docs/stack/anitopy.md), the manami offline database matches titles, results map
  to TMDB IDs, low confidence goes to a review screen, and manual fixes are pinned so a rescan
  never undoes them.
- Conversion is Kura's own pipeline: ffmpeg decodes (deinterlacing detected with idet), Python runs
  the AI model with ONNX Runtime (DirectML or CUDA), ffmpeg resizes and encodes NVENC HEVC 10-bit.
  The fast tier is ffmpeg with libplacebo and Anime4K. Kura's own final mux handles the audio
  policy, subtitles, fonts, chapters and a "processed" tag. Every output is verified (length,
  streams, a test play) before it replaces the original, which goes to quarantine for 30 days.

**Data**
- `%LOCALAPPDATA%\Kura`: kura.db, artwork cache, nightly backups (keep 7), logs (30 days). The
  folder can be moved to another drive.
- Next to the files: `Kura - Gap analysis.md` and `Kura - History.md` per anime (Plex ignores .md),
  a tag inside every converted MKV, and optional Plex poster and fanart.
- Export: one zip (SQLite, JSON, CSV, the .md reports, settings). Today it holds the database,
  settings and a manifest; it grows with the schema.
- Uninstall: offer the export first, keep the data folder unless the owner ticks "Delete the
  application data", never touch anime files.

**Tooling** (2026-10-10, all latest stable)
- Python 3.14 (uv-managed), uv, Ruff, Pyright (strict), pytest, FastAPI, Typer, PyInstaller.
- Node LTS, pnpm 12, Vite 8, React 19, TypeScript 7, Tailwind 4, Vitest 5, Biome 2 (lint and
  format). TypeScript 7 is the native compiler; typescript-eslint and openapi-typescript don't
  support it yet, hence Biome and hand-written API types.
- Rust stable (edition 2024), Tauri 2.12 with the single-instance and updater plugins.
- No Dependabot: it opens branches. Dependencies are updated on `main` with the routine in
  [docs/development.md](docs/development.md).

**Delivery**
- GitHub repo `frankgrobbelaar/kura`, public under the MIT licence (the owner's call on
  2026-10-10, replacing private releases through the `gh` login). Anyone may fork; only
  collaborators can open pull requests (a repo setting) and issues are off: no contributions.
  CI on every push to `main` (Windows runners).
- A `v*` tag builds the NSIS installer, signs it for the updater, and publishes a public release
  with `latest.json` and `THIRD-PARTY-NOTICES.txt`. Installed copies check daily at
  `releases/latest/download/latest.json`, no login needed.
- `THIRD-PARTY-NOTICES.txt` lists everything that ships, with its licence, and goes next to Kura
  with `LICENSE.txt`. `engine/tools/third_party_notices.py` writes it from what was actually
  bundled (PyInstaller's records, Cargo's graph, Vite's licence report) and stops the build on
  a licence that isn't allowed.
- Per-user install (no admin) into `%LOCALAPPDATA%\Programs\Kura`, apart from the data.
- The update-signing key is `%USERPROFILE%\.tauri\kura-updater.key` (no password) and the
  `TAURI_SIGNING_PRIVATE_KEY` repo secret. Lose it and installed copies can't update.
- Not code-signed (Windows SmartScreen warns once on first install); fine for a personal tool.

**The owner's PC**
- GTX 1660 Super 6 GB (Turing NVENC, no AV1 encode), i5-9600K (6 cores), 24 GB RAM, about 1.7 TB
  free on D: and F:. No ffmpeg yet. GitHub CLI signed in as frankgrobbelaar.
- Its Windows SDK registry entry points at the wrong folder, so the user variable `RC` names
  rc.exe for Rust builds (see docs/development.md, "Troubleshooting").

## What's next

1. A one-day spike: measure AI upscaling fps on the GTX 1660 Super (ONNX Runtime with DirectML and
   CUDA, Real-ESRGAN anime model vs Anime4K) to settle the conversion pipeline and the estimates.
2. Scanning: add folders, find files, read them with ffprobe, the first-scan screen.
3. Identification and the library home, then tidy-up plans, then conversion.

Licences to settle as these arrive: ffmpeg (downloaded at setup, an LGPL build), each AI
model's licence, manami's offline database (ODbL: downloaded rather than shipped, and credited),
and the attribution TMDB's terms require inside the app.

Build each screen to its board in [docs/design/](docs/design/), with its empty, error and recovery
states.

## Guides and docs

- **Area guides.** [AGENTS.md](AGENTS.md) is the entry for any coding agent, and each area has its
  own: [engine/AGENTS.md](engine/AGENTS.md), [app/AGENTS.md](app/AGENTS.md) (the UI),
  [app/src-tauri/AGENTS.md](app/src-tauri/AGENTS.md) (the shell) and [docs/AGENTS.md](docs/AGENTS.md).
  Read the guide for an area before changing it: it says what belongs there, the patterns to copy,
  and what "done" means.
- **Docs.** [docs/README.md](docs/README.md) is the map: architecture, development, conventions,
  design, releasing, and one page per tool in [docs/stack/](docs/stack/). Read the stack page before
  changing how a tool is used, and update docs in the same commit as the code they describe.
