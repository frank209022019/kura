# Shell: guide for coding agents

The shell is Kura's Rust side (Tauri 2): the window, the engine process, single-instance,
updates, and the installer. It is thin on purpose. Anything that isn't about the window, the
process or updating belongs in the engine. Start with [../../AGENTS.md](../../AGENTS.md) and
[../../CLAUDE.md](../../CLAUDE.md).

## Where things go

| What | Where |
| --- | --- |
| App setup: plugins, state, commands, exit | `src/main.rs` |
| Starting, watching and stopping the engine | `src/engine.rs` |
| Private updates through the GitHub CLI | `src/updater.rs` |
| Running console programs without a window | `src/process.rs` |
| Window, security policy, bundle, updater key | `tauri.conf.json` (installer-only extras: `tauri.bundle.conf.json`) |
| What the window may call | `capabilities/default.json` |
| Installer additions | `windows/hooks.nsh` |

## Rules

- **A new command** is a `#[tauri::command]` returning `Result<T, String>` (the string is a sentence
  for the person), registered in `generate_handler!`, with its types mirrored in `app/src/lib/`.
  Unit-test the parts that don't need a window.
- **Least privilege.** Add a permission to `capabilities/default.json` only for a feature that needs
  it. Loosen the content security policy only with a reason in the commit.
- **Never block the main thread.** Waiting and process work go on their own threads or async tasks.
- **Start programs with `process::hidden()`** so no console window flashes.
- **The engine handshake is a contract**: the ready line, `KURA_TOKEN`, stdin closing. Change
  `engine.rs` and `engine/tests/test_cli.py` together.
- **No secrets in the binary.** Updates authenticate with the PC's `gh` login at run time; the
  signing key never leaves `%USERPROFILE%\.tauri` and the GitHub secret; only the public key is in
  the config.
- **Installer changes** (`hooks.nsh`, bundle settings): build an installer, then test a fresh
  install, an update over it, and an uninstall, keeping the owner's real data folder out of it
  (launch the test install with `KURA_DATA_DIR` set).
- Keep the Rust crates (`tauri`, `tauri-build`, plugins) and the npm packages (`@tauri-apps/*`) on
  the same minor version.

## Commands

```powershell
cargo fmt; cargo clippy --all-targets -- -D warnings; cargo test
cd ..; pnpm tauri dev           # run Kura
cd ..; pnpm build:installer     # build the installer (signing key in the environment)
```

## Done means

`cargo fmt --check`, Clippy (no warnings) and `cargo test` are green; the app runs; for installer or
updater changes, install, update and uninstall were tried. Guides:
[tauri.md](../../docs/stack/tauri.md), [releasing.md](../../docs/releasing.md).
