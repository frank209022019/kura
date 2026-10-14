# Kura

Kura (蔵, "storehouse") is a personal Windows app for one person's anime library. It maps folders
in any layout, identifies every file, reports what is missing or broken, renames for Plex, and
converts the whole library to one standard, with AI upscaling for SD sources. It is the owner's
own tool: one user, one PC, never commercial, no sign-in. The code is shared under the MIT
licence: anyone may fork it, but the repo takes no contributions.

**Where it stands (2026-10-14):** design language chosen; repo, CI, installer and updater
pipeline set up, with semantic versions, a changelog and a downloads page. Built and tested end to
end: first-run setup with ffmpeg fetched from the list the installer shows; the scan (find, read
with ffprobe, identify on AniList and TMDB, check for gaps and write the reports); "Which anime is
this?"; the watcher; Home's shelf of franchises and series, a page per franchise and per title
(seasons, episode map, the gap analysis as a document, delete with put back); tidying up with
History's undo; converting with the queue (the AI model for SD, Anime4K for 720p, NVENC HEVC
10-bit, every result checked before it takes its original's place, nights only, full and
unplugged drives handled); Settings; nightly backups and restoring one; the quarantine cleared
out daily; the tray with "Start with Windows" and notifications; and the small-things board (a
file open in another app, a crash told on Home, a failed conversion's log and "Mark as broken",
offline, notes in the window, a name that's taken, not enough space, damaged records, the
overnight note); and light mode, Paper, as Windows is or as chosen. Kura 0.1.0, the first
release, went out on 2026-10-12; CHANGELOG.md has every release since. Everything in
[What's next](#whats-next) is built.

## Ground rules

- **One branch.** Work on `main` in `C:\GitHub\kura`. No feature branches, worktrees or PRs unless
  the owner asks. Commit and push to `main` once every check passes. If another session is working
  at the same time, stage only your own files (never `git add -A`).
- **Never change the Cinema look unasked.** Colours, type, shapes and motion come from the design
  canvas and live in [app/src/styles/tokens.css](app/src/styles/tokens.css). The owner: "do not
  change the color or anything".
- **Nothing changes until the owner reviews it.** Renames, moves, deletions and conversions are
  proposed first, applied only when approved, logged, and undoable. Duplicates and replaced
  originals go to quarantine (30 days), never straight to deletion; the one exception is the
  owner's own choice to delete converted files' originals once each result is checked and in
  place (2026-10-13). Anime files are never touched by uninstalling.
- **Kura is personal.** No email address, no company name (no employer, no organisation behind
  Kura) and no personal details beyond the owner's name (LICENSE, commit author), anywhere in
  the project: files, test data, commit messages, publisher, accounts, signing. The publisher
  name is "Kura". Commits carry only the owner's GitHub no-reply address (the clone's
  `user.email`), and Claude's co-author line has no address.
- **Only ship what Kura may share.** Kura is MIT. A dependency's licence must be on the allowed
  list in [engine/tools/third_party_notices.py](engine/tools/third_party_notices.py) (the
  installer build stops otherwise); code adapted from elsewhere keeps its notice (shadcn/ui:
  `app/src/components/ui/LICENSE-shadcn.txt`); no anime, artwork or other media in the repo or the
  installer, and titles appear only as example data. The one exception is TMDB's logo, which its
  terms ask for beside its credit line (the owner, 2026-10-12; `app/src/assets/README.md`).
  Microsoft's redistributable files the AI model needs (its C++ runtime, and DirectML inside ONNX
  Runtime) aren't open source but are Microsoft's to let programs carry: the notices list them
  apart, under Microsoft's terms.
- **Every change you'd notice goes in CHANGELOG.md**, in the same commit, under "Unreleased"
  (see [docs/releasing.md](docs/releasing.md)). Versions are semantic, and every release must be
  newer than the last so installed copies see it as an update.
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
CHANGELOG.md    every change you'd notice, by version
LICENSE         MIT
app/            the desktop app
  src/            React UI (TypeScript): components/, features/, lib/, styles/
  src-tauri/      Tauri shell (Rust): window, engine process, updates, installer config
engine/         the engine (Python): src/kura/, tests/, tools/ (build tools), kura-engine.spec,
                openapi.json
docs/           how it all works; docs/design/ holds the screens
scripts/        release.mjs (versions, notes, the downloads page), design-snapshot.mjs
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
node --test "scripts/*.test.mjs"
cd app; pnpm build:engine; pnpm build:notices
```

Fix formatting: `uv run ruff format` (engine), `pnpm fix` (app), `cargo fmt` (shell).
Build the installer locally: `cd app; pnpm build:installer` (needs the signing key, see
[docs/releasing.md](docs/releasing.md)). Release: on GitHub, Actions › Release › Run workflow on
`main` (patch, minor, major or an exact version); from a PC,
`node scripts/release.mjs patch|minor|major` (commits and tags), then
`git push --atomic origin main v1.2.3`. A release reaches every installed copy, so releasing is
the owner's call.

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
- It analyses every file, identifies it from free sources (TMDB and AniList) with artwork,
  reports gaps and health (a Markdown report per anime), renames for Plex, quarantines duplicates,
  and converts everything to one standard with a preview and estimates.
- Conversion history is kept "last modified" style. Installer, auto-updater, and an uninstaller that
  offers an export first.
- The pilot library is the whole Dragon Ball franchise (on the PC since 2026-10-12).
- Plex naming. Watched mostly on the PC; Plex or a phone maybe later.
- Kura's words never name Plex (the owner, 2026-10-11): the files keep the layout media servers
  read, but the app calls it "clean names" and says what it does, not who reads it. The naming
  choice is "Clean names" or "Keep my names". The release notes and the downloads page don't
  name it either (the owner, 2026-10-12), and they list every commit's title, so commit titles
  don't.
- Home shows the library (the owner, 2026-10-12): what this copy of Kura is up to (the engine,
  the data folder, the database, TMDB, updates) is in Settings › About. Its videos by picture
  are a summary at the top, and Scan again and Add a folder sit by the page's title with when
  the latest scan ran and what it found new or gone (the owner, 2026-10-13).
- Picture: crisp and clean; 720p or 1080p are both fine. **Every** file goes to the library standard,
  even 720p to 720p; a file already exactly at the standard is only renamed.
- The standard is chosen on Convert as in Settings, the estimates following at once (the owner,
  2026-10-13: "what if we want to convert later on to a different format?"). Changed, whatever
  isn't at the new one can be converted to it, Kura's own conversions too: from the converted
  file, or from its original if the owner puts that back from History first.
- Converted files' originals (the owner, 2026-10-13): kept in quarantine like any copy (the
  default), or deleted once each result is checked and in place, chosen on Convert and in
  Settings › Your data. A deleted original can't be put back, and History says so.
- Everything ends up neatly filed (the owner, 2026-10-11): seasons, specials and OVAs (Season 00)
  under their show, and every movie in a folder of its own, even one that arrived as a bare file.
  File and folder names match and stay clean and simple, nothing but the title, year, numbers and
  episode title: `TV\Show (Year)\Season 01\Show (Year) - S01E01 - Title.mkv` and
  `Movies\Title (Year)\Title (Year).mkv`, never release groups, resolutions or codecs. Folders a
  tidy-up leaves empty are removed (and come back on undo), and subtitle files beside a video move
  and rename with it.
- Only the page scrolls (the owner, 2026-10-11): the nav rail and the page's top (its title, or
  its breadcrumb) stay where they are, and so does a page's own section list beside it. A list
  that can run long inside a panel, as the queue's failed files, keeps to a height and scrolls in
  its place (the owner, 2026-10-14).
- The nav rail's tiles carry badges, as the boards show (the owner, 2026-10-13: "the little
  orange count badge is not showing over the convert side icon"): Convert, tinted, how far the
  file converting now has got, or how many files wait; Tidy up, solid amber, how many changes
  and files to match wait for the owner. Home, History and Settings have nothing that runs long
  enough to need one.
- The gap analysis shows in the app as a reader sees it, as an editor's Markdown preview would,
  under the title "Gap Analysis" (the owner, 2026-10-11).
- Deleting from Kura (the owner, 2026-10-11): a whole title, a season or one video, from the
  title's page, after Kura asks; and a file waiting for a match, or one set aside as not anime
  (listed there to match after all), from "Which anime is this?" (2026-10-13). It goes to
  quarantine like any copy set aside, never straight to deletion, and History (or the page,
  right after) puts it back until the clear-out.
- The queue works on several files at once (the owner, 2026-10-13: "batch selection to do
  certain actions like remove from queue", "we should be able to cancel all"): ticked files, or
  a whole season or title, go next, to the end or out of the queue together, and "Cancel all"
  empties it and stops the file converting, after asking. Files themselves never change.
- Not enough space (the owner, 2026-10-12): when a drive hasn't room for what's queued, the
  queue pauses and says what the files there need. The owner can empty that drive's quarantine
  first (with a second "are you sure": what's set aside there is deleted for good, before its
  days are up) or convert the files that fit now, the rest waiting for room. Kura doesn't write
  results to another drive. The Convert screen asks the same before queueing a choice that
  doesn't fit.
- Lists sort by release date by default, oldest first, on every page that lists series, movies,
  OVAs or specials, and can sort by name and other orders (the owner, 2026-10-11). They're
  grouped by type (the owner, 2026-10-13: "we need to order by type"): series first, then
  movies, OVAs and specials, each group in the order chosen; Home's shelf puts franchises first.
  "Recently added" and "Most missing" list every type together.
- A franchise's page shows what the library is missing of the whole franchise (the owner,
  2026-10-13): "Missing titles", beside the sort after a divider, puts in among its titles the
  series, films, OVAs and specials AniList ties to it by story that the library has no part of,
  each in its place as a dotted placeholder (the owner, 2026-10-13: "it should be a dotted
  placeholder for it in the library"), AniList's cover dimmed in it, with a hollow "Not in
  library" ("Coming" for one not out yet). One the library holds some of (a season TMDB keeps
  under a show it has, a special in a show's specials) isn't missing. A title's page has
  "Missing titles" too, leading to its franchise's page with them in, a title alone in the
  library included. Kura looks franchises up in the background, a few entries at a time,
  what the library lacks first, and asks about each again weekly, daily while it airs or is
  still to come, so a new one ("now there is a new Dragon Ball Super: Beerus out") appears by
  itself. Which titles make a franchise on Home doesn't change with what's looked up: only the
  links of entries the library holds tie titles together, as before.
- Everything says what it is (the owner, 2026-10-11): TV series, movie, OVA or special, as a word
  on its card, title page, review and report (status keeps the shapes), with counts by kind
  ("TV · 26 episodes · 2 OVAs · 1 movie"). Specials and OVAs are listed apart from missing
  episodes, so they never count as missing.
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
- Shortcuts: Space pauses the queue and 1 to 3 picks a guess on "Which anime is this?"; no others
  (no Ctrl K search, arrows through posters or Ctrl Z undo: the owner, 2026-10-14, "Dont worry
  about the shortcuts"). Everything still works from the keyboard.
- Light mode is Paper (the owner's pick of three, 2026-10-14): a warm paper ground #f3efe6,
  cream panels #fffcf6 with #e6dfd1 borders and a soft warm shadow, text #1d1912 and #5d564a,
  amber text #7f5200, to convert #5b7cc4, the same amber and the same blue featured panel with
  its orb. On paper a ready square gets a darker edge, as solid amber is faint on cream. Each
  colour token holds both values (`light-dark()`), and a part that stays dark (the featured
  panel, a video) carries `scheme-dark`.
- Light or dark (2026-10-14, proposed with the options and let stand): as Windows is, changing
  when it does (the default), or always one: "Same as Windows", "Light" or "Dark" in Settings ›
  General. The shell keeps the choice and makes the window in it, so the page is right from its
  first frame.
- Canvases: [Kura Workflows](https://claude.ai/artifact/XgGkfpW6doBUPcnrPqrbxb) (13 boards, the source
  of truth for screens), the [options record](https://claude.ai/artifact/NWe6abnPRYCn6BGTVK25za),
  and [Kura Light Mode Options](https://claude.ai/artifact/7Bdz7CoKjBbV8JrSLXfu4y) (Paper's Home
  and queue, the same in Cinema's dark beside them, and the two lights not chosen). Snapshots in
  [docs/design/](docs/design/).

**Architecture**
- Tauri 2 shell, React + Tailwind + shadcn/ui (restyled to Cinema) UI, Python engine sidecar built
  with PyInstaller as a folder (fast start; ships its own Python). Local API with a per-launch token,
  plus a CLI. SQLite for data.
- A pure core behind small interfaces: parse → match → plan → check → estimate.
- Identification: anitopy parses names (chosen over guessit and aniparse after testing them on
  real names, see docs/stack/anitopy.md), AniList's search matches titles (a name that finds
  nothing is asked again in shorter forms, with a series' initials written out, and as AniList
  writes it, docs/stack/anilist.md; what AniList still can't find is searched on TMDB, which
  knows more languages and spellings, and AniList is asked for TMDB's names for it,
  docs/stack/tmdb.md; built 2026-10-13 at the owner's word), results map to TMDB IDs, low
  confidence goes to a review screen, and manual fixes are pinned so a rescan never undoes
  them. A series' special its show's list doesn't name is looked up by its own name, as an OVA
  or special of its own. The manami offline database was the first plan, but its repository
  was archived in 2026 and stopped updating, so AniList's search, which is always current and
  needs no download, took its place (2026-10-11).
- Metadata from TMDB and AniList together, for full coverage (the owner, 2026-10-11). TMDB gives
  the episode lists (titles, air dates, Plex's seasons) and the artwork, with the owner's own key:
  Kura asks for it in Setup and Settings and keeps it on the PC, never in the code or an export.
  AniList, which needs no key, covers what TMDB lacks: obscure titles, how series, movies and
  specials connect, and airing dates. Missing episodes are those TMDB lists as aired that the
  library doesn't hold.
- When the missing-episode check runs (the owner, 2026-10-11): "Scan now" refreshes everything.
  While Kura is open it watches the library folders, so new and removed files are noticed at once
  (a scan starts five seconds after a folder goes quiet, and every screen catches up when it
  ends; the owner, 2026-10-13: "a single file removed ... picked up no changes"), and it catches
  up at start on what changed while it was closed. Every scan says what it found new and gone.
  Episode lists of shows still airing are refreshed every hour, finished shows' every week. A
  "Start with Windows" setting (off by default) keeps Kura in the tray so the checks carry on and
  it can notify; no scheduled task.
  Closing the window quits Kura unless "Keep Kura running when you close the window", a setting
  of its own under it, is on (the owner, 2026-10-12).
- Conversion is Kura's own pipeline: ffmpeg decodes (deinterlacing detected with idet), Python runs
  the AI model with ONNX Runtime on DirectML, ffmpeg resizes and encodes NVENC HEVC 10-bit. Kura's
  own final mux handles the audio policy, subtitles, fonts, chapters and a "processed" tag. Every
  output is verified (length, streams, a test play) before it replaces the original, which goes
  to quarantine for 30 days.
- Upscaling by source, the owner's pick after the test on 2026-10-11:
  - SD (480p, 576p): Real-ESRGAN's anime video model (`realesr-animevideov3`, BSD-3-Clause) as
    ONNX in full precision: about an hour per episode on the GTX 1660 Super.
  - 720p: Anime4K's high-quality mode A through ffmpeg's libplacebo: about 10 minutes.
  - 1080p: no upscaling; re-encoded only when it isn't HEVC 10-bit already (about 3 minutes),
    otherwise just renamed. Anything bigger comes down to 1080p.
  - DirectML, not CUDA: CUDA was no faster and adds more than a gigabyte to download, and half
    precision is slower on GTX 16 cards. Real-ESRGAN's bigger anime model ran at 0.6 frames a
    second, far too slow. ONNX Runtime, the model (2.5 MB) and the shaders (0.4 MB) ship inside
    Kura; the measured speeds are the defaults in `engine/src/kura/core/estimate.py`.

**Data**
- `%LOCALAPPDATA%\Kura`: kura.db, artwork cache, nightly backups (keep 7), logs (30 days), and
  `tools\` (ffmpeg, downloaded on first run; see docs/stack/ffmpeg.md). The folder can be moved to
  another drive.
- Next to the files: `Kura - Gap analysis.md` and `Kura - History.md` per anime (Plex ignores .md),
  a tag inside every converted MKV, and optional poster and fanart for media servers (built:
  off unless the owner turns it on).
- Export: one zip (SQLite, JSON, CSV, the .md reports, settings). Today it holds the database,
  settings, every file change (`changes.csv`) and a manifest; it grows with the schema.
- Kura deletes only its own files, whatever its records say (a damaged database, or one an
  imported export held): what's in a day's folder of a quarantine, its unfinished copies
  (`.kura-converting`, `.kura-partial`) and its own `poster.jpg` and `fanart.jpg`; and,
  finishing a move to another drive that a stop cut short, the original once the same file is
  in place.
- Records damaged past use (the owner, 2026-10-12): as the engine starts, Kura says so and
  offers the newest backup that opens (with none, new records, as on its first day), keeping the
  damaged file beside them as it is, never deleting it.
- Uninstall: offer the export first, keep the data folder unless the owner ticks "Delete the
  application data", never touch anime files.

**Tooling** (2026-10-10, all latest stable)
- Python 3.14 (uv-managed), uv, Ruff, Pyright (strict), pytest, FastAPI, Typer, PyInstaller.
- Node LTS, pnpm 12, Vite 8, React 19, TypeScript 7, Tailwind 4, Vitest 5, Biome 2 (lint and
  format). TypeScript 7 is the native compiler; typescript-eslint and openapi-typescript don't
  support it yet, hence Biome and hand-written API types.
- Rust stable (edition 2024), Tauri 2.12 with the single-instance, updater, dialog, opener,
  notification and autostart plugins, and its tray icon.
- No Dependabot: it opens branches. Dependencies are updated on `main` with the routine in
  [docs/development.md](docs/development.md).

**Delivery**
- GitHub repo `frankgrobbelaar/kura`, public under the MIT licence (the owner's call on
  2026-10-10, replacing private releases through the `gh` login); the app's identifier is
  `io.github.frankgrobbelaar.kura`. Anyone may fork; only collaborators can open pull requests
  (a repo setting) and issues are off: no contributions. Secret scanning with push protection is
  on: GitHub refuses a push that holds a known secret. CI on every push to `main` (Windows
  runners).
- Semantic versions and a changelog (the owner, 2026-10-11): patch for fixes, minor for features,
  major for a change to act on. `scripts/release.mjs` picks the version, moves CHANGELOG.md's
  "Unreleased" entries under it, commits and tags; it and the release workflow refuse a version
  that isn't newer than the last, so every release is an update.
- The owner releases from GitHub's site when happy with `main` (2026-10-11): Actions › Release ›
  Run workflow. On `main` it checks CI passed, runs `release.mjs`, builds and checks the
  installer, and only then pushes the release commit and tag together and publishes. The commit
  carries the name and no-reply address of whoever started the run. A tag pushed from a PC still
  releases too.
- A `v*` tag builds the NSIS installer, signs it for the updater, and publishes a public release
  with its notes (the changelog entries, every commit since the last release, a comparison link),
  `latest.json` (which carries the entries to the update card) and `THIRD-PARTY-NOTICES.txt`. The
  workflow then checks that `releases/latest/download/latest.json` names the new version, which
  installed copies check daily, no login needed, and refreshes the downloads page.
- Downloads page (the owner, 2026-10-11): https://frankgrobbelaar.github.io/kura/, the repo's
  website on GitHub Pages, lists every version newest first with its notes, installer, size and
  SHA-256. Kura's "Every version" buttons open it.
- `THIRD-PARTY-NOTICES.txt` lists everything that ships, with its licence, and goes next to Kura
  with `LICENSE.txt`. `engine/tools/third_party_notices.py` writes it from what was actually
  bundled (PyInstaller's records, Cargo's graph, Vite's licence report) and stops the build on
  a licence that isn't allowed.
- **Every download is listed in the installer** (the owner, 2026-10-11: "really important"). No
  one installs anything by hand except a graphics driver, which Kura checks and links to. What
  isn't inside the installer (WebView2 on a PC without it, ffmpeg) goes in one manifest,
  `engine/src/kura/downloads.json`: what it's for, version, size, licence, source and checksum.
  The installer's first page lists it (`scripts/installer-notes.mjs`), the first-run Tools step
  downloads Kura's part of it (`engine/src/kura/tools.py`), and Kura downloads nothing that isn't
  on it. Lookups (titles, episode lists, artwork from TMDB and AniList) aren't downloads of
  programs or data sets, and are named on the same page.
- Per-user install (no admin) into `%LOCALAPPDATA%\Programs\Kura`, apart from the data.
- The update-signing key is `%USERPROFILE%\.tauri\kura-updater.key` (no password) and the
  `TAURI_SIGNING_PRIVATE_KEY` repo secret. Lose it and installed copies can't update.
- Not code-signed (Windows SmartScreen warns once on first install); fine for a personal tool.

**The owner's PC**
- GTX 1660 Super 6 GB (Turing NVENC, no AV1 encode), i5-9600K (6 cores), 24 GB RAM, about 1.7 TB
  free on D: and F:. Graphics driver 617.42 (fine as it is; never install drivers). No ffmpeg
  installed: Kura fetches its own. GitHub CLI signed in as frankgrobbelaar.
- Its Windows SDK registry entry points at the wrong folder, so the user variable `RC` names
  rc.exe for Rust builds (see docs/development.md, "Troubleshooting").

## What's next

1. Identification and missing episodes: done (AniList and TMDB, the review screen, the gap
   check and its reports, the watcher, the scan's last three stages, and TMDB's credit line with
   its logo).
2. The library home and a page per title: done (the shelf of franchises and series sorted by
   release date, a page per franchise, "Needs your attention", the title page with "Open folder"
   and "Change match").
3. Tidy-up in the app: done (review title by title, apply, undo, quarantine on the same drive,
   History). Quarantine keeps copies for 30 days, then step 6's daily clear-out empties it.
4. Conversion, with the queue: done (the AI model and Anime4K, the encode and Kura's mux, checks,
   estimates and "See it first", nights only, full and unplugged drives, put back from History).
5. Settings: done (moving the data folder to another drive, and importing an export, too).
6. Background care: done (nightly backups with restore, the daily quarantine clear-out, the tray
   with "Start with Windows" and notifications).
7. Poster and background pictures next to each show, for media servers: done (optional, off
   unless turned on; the UI never names Plex).
8. The small-things board: done (a file open in another app, a crash or power cut, a failed
   conversion, a finished batch, being offline, a name that's taken: "(2)" beside it, "Compare
   the two" or "Skip"; not enough space: empty the drive's quarantine first, or convert what
   fits; records damaged past use: the newest backup that opens, or new records; and the
   overnight note: keeping the PC awake till 07:00, "Stop at 03:00" starting no file after 03:00
   that night, the one converting finishing).
9. Light mode: done (Paper, the owner's pick of three drafted on 2026-10-14, over A Daylight's
   cool grey and C Ink's white and black; as Windows is, or chosen in Settings › General).

Licences, all settled (the owner, 2026-10-14). ffmpeg: Kura doesn't ship it; the first run
downloads an LGPL build (LGPL-2.1-or-later) from the source `engine/src/kura/downloads.json`
names, with its licence, as the installer's first page lists it. AniList: its API is free for
non-commercial use within its rate limit, and Kura keeps to it (one client the engine shares, which
waits when AniList says the minute's requests are spent; the franchise look-ups ask about 12 a
minute). TMDB's terms are met in the app: its credit line with its logo, in Settings (About, and
Titles and artwork). Real-ESRGAN's model (BSD-3-Clause) and Anime4K's shaders (MIT) are in
`engine/src/kura/assets` with their licences, which the notices carry.

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
