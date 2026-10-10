# Releasing

How a change becomes an installed, self-updating Kura.

## The short version

```powershell
node scripts/set-version.mjs 0.2.0      # sets the version everywhere and refreshes what depends on it
git commit -am "Release 0.2.0"
git tag v0.2.0; git push origin main v0.2.0
```

The tag starts the [release workflow](../.github/workflows/release.yml). About fifteen minutes
later the release is on GitHub, and every installed Kura offers "Kura 0.2.0 is ready" within a day.

## Versions

Kura has one version, written in two places that must agree: `app/package.json` (the shell and UI;
Tauri reads it) and `engine/pyproject.toml`. `scripts/set-version.mjs` changes both, then refreshes
`engine/uv.lock` and `engine/openapi.json`, which carry it too. The release workflow refuses a tag
that doesn't match. Versions follow `major.minor.patch`; while Kura is young, bump the minor
version for features and the patch for fixes.

## What the release workflow does

1. Checks that the tag, `package.json` and `pyproject.toml` agree.
2. Builds the engine with PyInstaller, the UI with Vite, and the shell with Cargo.
3. Bundles them into `Kura_<version>_x64-setup.exe` (NSIS) and signs it for the updater, which
   writes `Kura_<version>_x64-setup.exe.sig`.
4. Creates a **draft** release with the installer and signature, writes `latest.json` (the update
   manifest: version, date, signature, and the installer's API address), uploads it, then
   publishes the release. Installed copies only ever see a complete release.

Starting the workflow by hand (Actions › Release › Run workflow) is a dry run: it builds and signs
the installer and keeps it as a downloadable workflow artifact, without releasing anything.

## How updates reach the PC

The repo is private, so its releases need a GitHub login to download. Kura borrows the GitHub CLI's
login on this PC instead of keeping one of its own (the owner's choice; the alternative was a
public releases-only repo).

1. Once a day, and at start, the shell runs `gh auth token` and
   `gh api repos/frankgrobbelaar/kura/releases/latest` to find the newest `latest.json`.
2. Tauri's updater reads the manifest with that token. If the version is newer, it downloads the
   installer in the background and checks its signature against the public key built into Kura.
3. The UI shows "Kura 0.2.0 is ready". "Restart and update" stops the engine, runs the installer
   in passive mode (a progress bar, no questions), and the installer opens Kura again.

If `gh` is missing or signed out, the Home page's "This copy of Kura" panel says so
("Can't check right now: …"); fix it with `gh auth login`. The code is
[app/src-tauri/src/updater.rs](../app/src-tauri/src/updater.rs).

## Installing for the first time

```powershell
gh release download v0.1.0 --repo frankgrobbelaar/kura --pattern "*.exe"
```

Run the installer. Kura isn't code-signed, so Windows SmartScreen warns once: choose More info ›
Run anyway. (Updates don't warn: the updater downloads them, not a browser.) Kura installs for this
user only, without admin rights, into `%LOCALAPPDATA%\Programs\Kura`; its data stays apart in
`%LOCALAPPDATA%\Kura`.

## The installer

Tauri builds it with NSIS; Kura adds three hooks in
[app/src-tauri/windows/hooks.nsh](../app/src-tauri/windows/hooks.nsh):

- Program files go to `%LOCALAPPDATA%\Programs\Kura`, not Tauri's default `%LOCALAPPDATA%\Kura`,
  which is the data folder.
- Uninstalling first asks "Export your Kura data before uninstalling?" and, if yes, runs
  `kura-engine export` into Documents. If the export fails, nothing is removed.
- The data folder stays unless "Delete the application data" is ticked. Anime files are never
  touched either way.

Updates skip both questions.

## The signing key

Updates are signed with a minisign key so a tampered installer never runs.

- Private key: `%USERPROFILE%\.tauri\kura-updater.key` (no password), and the
  `TAURI_SIGNING_PRIVATE_KEY` secret in the GitHub repo. **Keep a backup** (a password manager is
  fine). Without it, installed copies can't verify new versions and have to be reinstalled by hand.
- Public key: `plugins.updater.pubkey` in
  [app/src-tauri/tauri.conf.json](../app/src-tauri/tauri.conf.json).

To replace a lost or leaked key: `pnpm tauri signer generate -w <path>`, put the new public key in
`tauri.conf.json`, update the secret (`gh secret set TAURI_SIGNING_PRIVATE_KEY < <path>`), release,
and install that release by hand once.

## Building an installer locally

```powershell
$env:TAURI_SIGNING_PRIVATE_KEY = "$env:USERPROFILE\.tauri\kura-updater.key"
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""
cd app; pnpm build:installer
```

The result is in `app/src-tauri/target/release/bundle/nsis/`. `build:installer` uses
`tauri.bundle.conf.json` on top of `tauri.conf.json`, which adds the engine to the bundle and turns
on update signing; `pnpm tauri dev` and CI checks don't need either.
