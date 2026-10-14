# Kura

Kura (蔵, "storehouse") is a personal Windows app for one anime library. It maps folders in any
layout, identifies every file, reports what is missing or broken, gives it all clean names and
folders, and converts the whole library to one standard, with AI upscaling for SD sources.
Nothing changes until you review it, and everything stays on your PC: no accounts, no cloud.

![Kura's library home, from the design](docs/design/preview.png)

## What it does

### Knows your library

- **Reads it as it is.** Point Kura at your folders, in any layout: one anime per folder, a
  franchise in sub-folders, or many anime mixed together. It reads every video (length, picture,
  sound and subtitles) and keeps watching the folders: a video added or removed shows within
  seconds, and every scan says what it found new and what's gone.
- **Identifies every file.** Each series, movie, OVA and special is found on AniList, and with
  your own free TMDB key also its seasons, episode titles, air dates and posters. Names AniList
  can't find are searched on TMDB too, in other languages and spellings, and a special is found
  by its own name. What Kura isn't sure of waits for you on "Which anime is this?", with stills
  from the file; your answer, or "not anime", stays through every rescan.

### Shows what's there, and what isn't

- **Home is your shelf.** A summary of your videos by picture (SD, 720p, 1080p) on top, what
  needs you, and every franchise and series by type, oldest first, or by name, newest added or
  most missing.
- **A page for every franchise and title.** Seasons and an episode map with each episode's state,
  the episodes that aired that you don't have, specials and OVAs listed apart, the files that won't
  play, and a gap analysis you can read in the app or beside the files.
- **Missing titles.** A franchise's page can also show the series, films, OVAs and specials you
  have none of, as dotted placeholders among your own (for Dragon Ball: Kai, DAIMA, the first
  four films). Kura keeps the list current in the background, so a new one appears by itself,
  marked "Coming" until it's out. Any title's page leads there.

### Tidies and converts, when you say

- **Tidies up.** Clean names and folders (`TV\Show (Year)\Season 01\…`, `Movies\Title (Year)\…`),
  subtitles moving with their video, or your own names kept. Every change is proposed title by
  title and made only when you apply it, and History undoes any of it.
- **Converts to one standard.** Choose 1080p or 720p and see the time and space it takes at once.
  Kura encodes HEVC 10-bit on the graphics card, upscaling SD with an AI model and 720p with
  Anime4K, and "See it first" shows a frame before and after. The queue runs at night if you like,
  says how far along it is, and waits when a drive is full or unplugged. Every result is checked
  before it takes its original's place, and you can convert again later to a new standard.

### Keeps it safe

- **Loses nothing.** Replaced originals, duplicates and whatever you delete wait 30 days in a
  quarantine on their own drive, and History puts them back; converted originals can go at once
  instead, if you choose. Kura's records are backed up every night and can be restored, and an
  export takes them to another PC.
- **Looks after itself.** It can start with Windows and wait in the tray, tells you when a batch is
  done, says what happened after a crash or power cut, and updates itself, showing what's new
  first. It's dark or light as Windows is, or as you choose.

Kura is built in the open and ready for everyday use. Everything planned is built:
[What's next](CLAUDE.md#whats-next) says where it stands.

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
