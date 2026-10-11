# Tauri (the shell)

[Tauri 2](https://v2.tauri.app) turns the web UI into a Windows app: a native window drawn by
WebView2, a small Rust program around it, and the installer and updater. Kura uses Tauri 2.12 with
Rust stable (edition 2024).

## Files

| File | What it holds |
| --- | --- |
| `app/src-tauri/src/main.rs` | The app: plugins, state, commands, start and exit |
| `app/src-tauri/src/engine.rs` | Starting, watching and stopping the engine |
| `app/src-tauri/src/updater.rs` | Updates from the GitHub releases |
| `app/src-tauri/src/tray.rs` | The tray icon, starting with Windows, and notifications |
| `app/src-tauri/src/process.rs` | Running console programs without a console window |
| `app/src-tauri/tauri.conf.json` | Name, version source, window, security policy, bundle, updater address and key |
| `app/src-tauri/tauri.bundle.conf.json` | Extra settings for building the installer (see below) |
| `app/src-tauri/capabilities/default.json` | What the window may ask of the shell |
| `app/src-tauri/windows/hooks.nsh` | Kura's additions to the installer |
| `app/src-tauri/icons/` | App icons, generated from `kura.svg` |

## The window

One window, `main`, 1280 × 832 (at least 720 × 560), with `decorations: false`: Kura draws its own
title bar (`app/src/components/shell/title-bar.tsx`) as the design shows. Elements marked
`data-tauri-drag-region` move the window and maximise it on double-click; the buttons call
`getCurrentWindow().minimize()`, `.toggleMaximize()` and `.close()`. Windows' snap layouts menu
doesn't appear when hovering our maximise button; Win+Z and dragging to the screen's edges still
work.

The background colour is set in the config too, so the window is dark before the UI loads.

## Commands and events

The UI calls the shell through four commands and listens to one event:

| Name | Kind | Does |
| --- | --- | --- |
| `engine_status` | command | The engine's status now: `starting`, `ready` (with address and token) or `failed` |
| `restart_engine` | command | Start again after a failure |
| `prepare_update` | command | Check for an update and download it; returns its version or nothing |
| `install_update` | command | Stop the engine, run the installer, let it reopen Kura |
| `engine-status` | event | Sent whenever the engine's status changes |

A new command is a `#[tauri::command]` function, listed in `generate_handler!` in `main.rs`, with
its types mirrored in `app/src/lib/`. Commands return `Result<T, String>`; the string is shown to
the person, so write it as a sentence.

## Security

- **Capabilities** (`capabilities/default.json`): the window gets `core:default` plus the title bar
  permissions (minimise, maximise, close, dragging). Add a permission only for a feature that needs
  it, and say why in the description.
- **Content security policy** (`app.security.csp`): scripts and styles from the app only,
  connections to the app, Tauri's IPC and the engine on `http://127.0.0.1:*`, images also from the
  engine (for artwork later).
- The installed window's origin is `http://tauri.localhost`; in development it is
  `http://localhost:1420`. The engine allows exactly these two (see [fastapi.md](fastapi.md)).

## Plugins

- **single-instance**: opening Kura again focuses the open window, because two copies would share
  one database.
- **updater**: downloads and verifies updates. Configured under `plugins.updater`: the address of
  the newest release's `latest.json`, the public key, and passive install mode. Kura drives it
  from Rust (`updater.rs`), so the window needs no updater permission and the downloaded
  installer waits in the shell until "Restart and update". See [../releasing.md](../releasing.md).
- **dialog**: Windows' folder picker, for "Add a folder". Kura opens it from Rust too
  (`dialogs.rs`, `pick_folder`), so the window needs no dialog permission.
- **opener**: opens web pages in the default browser. Kura drives it from Rust too (`links.rs`):
  the window asks for a page by name (`open_downloads_page`), so it needs no opener permission and
  can't be steered to any other address.
- **The tray** (Tauri's `tray-icon` feature, `tray.rs`): an icon in the notification area while
  Kura runs, with Open Kura and Quit Kura; a click opens the window.
- **autostart**: "Start with Windows" in Settings > General, which Windows keeps in its own list
  of startup apps (the shell asks it, so the switch is always true to it). Windows starts Kura
  with `--in-tray`: the window stays hidden (it's created hidden and shown at start otherwise),
  and with the setting on, closing the window keeps Kura in the tray instead of quitting. Don't
  turn it on from a development build: Windows would start that build at sign-in.
- **notification**: Windows notifications for what the engine tells of on its stdout after the
  ready line (`{"event":"notify",...}`: a finished batch, a queue that paused itself), and for an
  engine that can't run (it's then tried again by itself), shown only while the window is away
  (in the tray or minimized); a click on one opens the window. All from Rust, so the window needs
  no permission for either.

## The engine process

In development the shell runs `uv run --project engine kura serve --watch-stdin` and points
`KURA_DATA_DIR` at `engine/.dev-data`. Installed, it runs `engine\kura-engine.exe` from the
resource folder. Either way it hides the console window, reads the ready line (waiting on while
the engine says it's still working, giving up on one silent for a minute), keeps the last 40
error lines for the failure screen, notices if the engine stops on its own, and closes its
stdin on exit. See
[../architecture.md](../architecture.md#start-run-stop).

## Installer

`bundle.targets` is `nsis`: one `Kura_<version>_x64-setup.exe`, installed per user without admin
rights (`installMode: currentUser`). Publisher: Kura. WebView2 is downloaded by the installer if a
PC lacks it (Windows 11 always has it).

`tauri.bundle.conf.json` is merged in only by `pnpm build:installer`. It builds the engine, the UI
and the third-party notices first; adds `engine/dist/kura-engine/` as the `engine/` resource
folder, with `LICENSE.txt` and `THIRD-PARTY-NOTICES.txt` beside Kura; and turns on
`createUpdaterArtifacts` (the `.sig` file). Keeping these out of the main config means
`pnpm tauri dev` and `cargo clippy` work without a PyInstaller build or the signing key.

`windows/hooks.nsh` is included by Tauri's NSIS template:

- `KuraUseProgramsFolder` (run as the installer's window opens) changes the default folder from
  `%LOCALAPPDATA%\Kura`, which is the data folder, to `%LOCALAPPDATA%\Programs\Kura`.
- `NSIS_HOOK_PREUNINSTALL` offers the export and stops if it fails.
- `NSIS_HOOK_POSTUNINSTALL` deletes the data folder only if "Delete the application data" was ticked.
  Data moved to another drive (its home's `location.txt` names it, in UTF-16, read with
  `FileReadUTF16LE`) goes too, but only Kura's own
  parts of it (`kura.db`, `artwork`, `backups`, `cache`, `logs`, `tools`…), and only when it holds
  `kura.db`; its folder goes only if nothing else is left in it.

Hooks can use the template's variables (`$UpdateMode`, `$PassiveMode`, `$DeleteAppDataCheckboxState`).
After a Tauri upgrade, build an installer and test an install, an update and an uninstall.

## Commands you'll use

```powershell
cd app
pnpm tauri dev                      # run Kura
pnpm tauri icon src-tauri/icons/kura.svg   # regenerate icons (then delete the non-Windows ones)
pnpm build:installer                # build the installer (needs the signing key)
cd src-tauri; cargo clippy --all-targets -- -D warnings; cargo test
```

## Upgrading

Keep `@tauri-apps/cli` and `@tauri-apps/api` (npm) and `tauri`, `tauri-build` and the plugins
(Cargo) on the same minor version. Read the [release notes](https://v2.tauri.app/release/) for
config changes, rebuild the installer, and test install, update and uninstall.
