# GitHub Actions (CI and releases)

Three workflows in `.github/workflows/`. CI and releases run on Windows runners (`windows-latest`),
because Kura is a Windows app and the checks should see what the owner's PC sees; the downloads
page is only a web page, so it builds on Linux.

| Workflow | Runs on | Does |
| --- | --- | --- |
| [ci.yml](../../.github/workflows/ci.yml) | every push to `main`, pull requests (only collaborators can open them), by hand | Engine: Ruff, Pyright, pytest. App: Biome, TypeScript, Vitest, the release scripts' tests, the UI build, rustfmt, Clippy, cargo test |
| [release.yml](../../.github/workflows/release.yml) | by hand on `main` (the owner releasing from the site), a `v*` tag pushed from a PC, or by hand on a tag to publish it again | On `main`: checks CI passed, then makes the release commit and tag with `scripts/release.mjs`. Writes the notes from CHANGELOG.md; builds, smoke-tests and signs the installer; pushes the release commit and tag; publishes the release with its notes, `latest.json` and the third-party notices; checks installed copies see the update; refreshes the downloads page. A dry run stops before pushing and keeps the installer |
| [downloads.yml](../../.github/workflows/downloads.yml) | after each release (started by release.yml), a push that changes the page's code, or by hand | Builds the downloads page from the releases and publishes it on GitHub Pages |

The jobs run the same commands as [../development.md](../development.md), so a green local run
means a green CI run.

## How they're set up

- **Pinned actions.** Every action is pinned to a full commit SHA with its version in a comment
  (`actions/checkout@3d3c… # v7.0.1`), so a moved tag can never change what runs. Updating one means
  changing both the SHA and the comment (see [Updating dependencies](../development.md#updating-dependencies)).
- **Tools.** `astral-sh/setup-uv` installs uv (which installs Python 3.14 from `.python-version`);
  `pnpm/action-setup` installs the pnpm version named in `app/package.json` and caches the store;
  `actions/setup-node` installs Node's current LTS; Rust comes from the runner's `rustup`, and
  `Swatinem/rust-cache` keeps compiled crates between runs.
- **Least privilege.** CI can only read the repo. The release workflow may write contents (to push
  the release commit and tag to `main` and create the release) and use Actions (to read `main`'s CI
  result and start the downloads page); the downloads page workflow may publish to Pages
  (`pages: write`, `id-token: write`). All use the built-in `GITHUB_TOKEN`, and the GitHub CLI is
  available on the runners. Pushes and events made with `GITHUB_TOKEN` don't start other workflows:
  the release commit doesn't start CI (CI passed on the commit before it, and the release checks
  the build itself), its tag doesn't start the release a second time, and the release starts the
  downloads page explicitly.
- **Who commits.** The release commit and tag made on GitHub carry the name and GitHub no-reply
  address of whoever started the run, looked up from the run (`GITHUB_ACTOR`, `GITHUB_ACTOR_ID`),
  so no address is written in the repo.
- **One run at a time.** A new push cancels a CI run still going for the same branch.

## Secrets

| Secret | Used by | Holds |
| --- | --- | --- |
| `TAURI_SIGNING_PRIVATE_KEY` | release.yml | The update-signing key (the contents of `kura-updater.key`) |

Set or replace it with `gh secret set TAURI_SIGNING_PRIVATE_KEY < "$env:USERPROFILE\.tauri\kura-updater.key"`.

## Watching runs

```powershell
gh run list --limit 5
gh run watch                       # follow the newest run
gh run view --log-failed           # what broke
gh workflow run release.yml -f dry_run=true   # a dry run; download the installer with gh run download
gh workflow run release.yml -f bump=minor     # release main (the owner's call)
gh workflow run downloads.yml      # republish the downloads page
```

## Cost

The repo is public, so runs on GitHub's standard runners are free. A CI run takes a few minutes
once caches are warm; a release about fifteen. Forks don't get the signing key: secrets never
reach workflows that others start.
