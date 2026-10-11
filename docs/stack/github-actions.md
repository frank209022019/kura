# GitHub Actions (CI and releases)

Three workflows in `.github/workflows/`. CI and releases run on Windows runners (`windows-latest`),
because Kura is a Windows app and the checks should see what the owner's PC sees; the downloads
page is only a web page, so it builds on Linux.

| Workflow | Runs on | Does |
| --- | --- | --- |
| [ci.yml](../../.github/workflows/ci.yml) | every push to `main`, pull requests (only collaborators can open them), by hand | Engine: Ruff, Pyright, pytest. App: Biome, TypeScript, Vitest, the release scripts' tests, the UI build, rustfmt, Clippy, cargo test |
| [release.yml](../../.github/workflows/release.yml) | a `v*` tag, or by hand for a dry run | Writes the notes from CHANGELOG.md; builds, smoke-tests and signs the installer; publishes the release with its notes, `latest.json` and the third-party notices; checks installed copies see the update; refreshes the downloads page |
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
- **Least privilege.** CI can only read the repo. The release workflow may write contents (to create
  the release) and start workflows (the downloads page); the downloads page workflow may publish to
  Pages (`pages: write`, `id-token: write`). All use the built-in `GITHUB_TOKEN`, and the GitHub
  CLI is available on the runners. Workflows started by `GITHUB_TOKEN` events don't run others,
  which is why the release starts the downloads page explicitly.
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
gh workflow run release.yml        # a dry-run installer build; download it with gh run download
gh workflow run downloads.yml      # republish the downloads page
```

## Cost

The repo is public, so runs on GitHub's standard runners are free. A CI run takes a few minutes
once caches are warm; a release about fifteen. Forks don't get the signing key: secrets never
reach workflows that others start.
