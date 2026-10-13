# Kura

Kura (蔵, "storehouse") is a personal Windows app for one anime library. It maps folders in any
layout, identifies every file, reports what is missing or broken, gives it all clean names and
folders, and converts the whole library to one standard, with AI upscaling for SD sources.
Nothing changes until you review it, and everything stays on your PC: no accounts, no cloud.

![Kura's library home, from the design](docs/design/preview.png)

## What it does

- **Reads your library as it is.** Point Kura at your folders, in any layout: one anime per
  folder, a franchise in sub-folders, or many anime mixed together. It reads every video (its
  length, picture, sound and subtitles) and keeps watching, so new and removed files show at once.
- **Knows every file.** Each anime, movie, OVA and special is identified with AniList, and with
  your own free TMDB key also its seasons, episode titles and posters. What Kura isn't sure of
  waits for you on "Which anime is this?", and your answers stay through every rescan.
- **Says what's missing.** Each anime gets a gap analysis: the episodes that have aired that you
  don't have, and the files that won't play. Home shows the whole shelf, oldest first.
- **Tidies up.** Clean names and folders (`TV\Show (Year)\Season 01\…`, `Movies\Title (Year)\…`),
  or your own names kept, proposed title by title and changed only when you say. History undoes
  any of it.
- **Converts to one standard.** HEVC 10-bit on the graphics card, with AI upscaling for SD and
  Anime4K for 720p, at night if you like. See it first shows a frame before and after, and every
  result is checked before it takes the original's place.
- **Loses nothing.** Replaced originals, duplicates and whatever you delete wait 30 days in a
  quarantine on their own drive, unless you'd rather converted originals went at once. Kura's
  records are backed up every night, and an export takes them to another PC.
- **Looks after itself.** It can start with Windows and wait in the tray, tells you when a batch
  is done, and updates itself, showing what's new first.

Kura is built in the open and ready for everyday use. Everything planned is built except light
mode, which waits for its design: [What's next](CLAUDE.md#whats-next) says where it stands.

## Download

Get Kura from the [downloads page](https://frankgrobbelaar.github.io/kura/): the latest version and
every earlier one, with what changed (the same installers are on the
[releases page](https://github.com/frankgrobbelaar/kura/releases)). It runs on Windows 10 or 11,
64-bit, and an installed Kura updates itself, showing what's new first. Kura isn't code-signed, so
Windows SmartScreen warns on the first install: choose More info › Run anyway.

## Licence

Kura is free software under the [MIT licence](LICENSE): you may use, copy, change and share it,
in your own projects too, as long as the licence and copyright notice go with it. It comes with no
warranty.

Kura is built on other open-source software, each part under its own licence. The installer puts
`THIRD-PARTY-NOTICES.txt` next to Kura and every release carries it: it lists everything that
ships inside Kura, with its licence. The build stops if a part's licence isn't one Kura can meet.
Components adapted from shadcn/ui keep their notice in
[LICENSE-shadcn.txt](app/src/components/ui/LICENSE-shadcn.txt).

## Fork it; contributions aren't taken

Kura is one person's tool, shared as it is. You're welcome to download it, fork it and make your
fork your own. This repository doesn't take contributions: only the owner can open pull requests,
issues are turned off, and there's no support.

## No media, no affiliation

Kura contains no anime, artwork or other media, and it never downloads or shares video: it
organises files you already have. Titles such as Dragon Ball and Death Note appear in the docs,
designs and tests only as example data. They, and names such as Plex, TMDB and AniList, are
trademarks of their owners, and Kura isn't affiliated with or endorsed by any of them.

## Working on Kura

- [CLAUDE.md](CLAUDE.md): the decisions so far and the ground rules.
- [CHANGELOG.md](CHANGELOG.md): every change you'd notice, by version.
- [AGENTS.md](AGENTS.md): how coding agents work here, with a guide in each area.
- [docs/](docs/README.md): architecture, development, conventions, design, releasing, and a page
  for every tool in the stack.
- [docs/design/](docs/design/README.md): every screen, as pages you can open.

Set up the tools in [docs/development.md](docs/development.md) (Rust, Node LTS, pnpm, uv), then:

```powershell
cd engine; uv sync
cd ../app; pnpm install; pnpm tauri dev
```

| Folder | Holds |
| --- | --- |
| `app/` | The desktop app: React UI in `src/`, Tauri shell in `src-tauri/` |
| `engine/` | The Python engine: local API, command line, database; build tools in `tools/` |
| `docs/` | How it works, how to work on it, and the designs |
| `scripts/` | Releasing (versions, notes, the downloads page), the installer's first page, the design snapshot |
| `.github/` | CI and the release workflow |
