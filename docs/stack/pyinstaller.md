# PyInstaller (bundling the engine)

The installed Kura can't assume Python is on the PC, so [PyInstaller](https://pyinstaller.org)
bundles the engine with its own Python into a folder: `kura-engine.exe` plus `_internal/` (the
interpreter, the packages, about 35 MB, 60 files). The installer copies that folder next to
Kura's window as `engine\`.

A folder ("onedir") rather than a single exe because a single exe unpacks itself into a temporary
folder on every start: slower, and it upsets antivirus tools.

## Files

| File | What it holds |
| --- | --- |
| `engine/kura-engine.spec` | The recipe: entry point, package metadata, console program, no UPX |
| `engine/src/kura/__main__.py` | The entry point (also `python -m kura`) |
| `engine/dist/kura-engine/` | The output (ignored by git) |

## Building

```powershell
cd engine; uv run pyinstaller kura-engine.spec --noconfirm
dist\kura-engine\kura-engine.exe version
```

`pnpm build:installer` does this first, through `tauri.bundle.conf.json`.

## How the spec works

- `Analysis` starts at `__main__.py` and follows imports; `pathex=["src"]` finds the package.
- `copy_metadata("kura")` includes the package's metadata, which `kura.__version__` reads.
- Packages that load modules by name (Uvicorn) are covered by the hooks in
  `pyinstaller-hooks-contrib`, which comes with PyInstaller.
- `console=True`: the engine is a console program (the uninstaller and the CLI read its output);
  the shell starts it with no console window.
- UPX compression is off: it saves little and causes antivirus false alarms.
- `excludes` drops packages that only optional imports reach: setuptools (through `distutils`)
  and pytest (anyio's test runner). The filter after `Analysis` drops the Universal C Runtime
  DLLs, which Windows 10 and 11 have built in; otherwise PyInstaller copies whichever ones it
  finds on PATH (a JDK's, on the owner's PC), and builds would differ between PCs.
- PyInstaller's records of what it bundled (`build/kura-engine/*.toc`) feed the third-party
  notices (see [../releasing.md](../releasing.md#third-party-notices)).

## When something is missing

If the bundled engine fails with `ModuleNotFoundError` while `uv run kura` works, PyInstaller
didn't see an import made by name. Add it to `hiddenimports=[...]` in `Analysis`, or collect a
whole package with `collect_submodules("name")`, then rebuild and run
`dist\kura-engine\kura-engine.exe serve` with `KURA_TOKEN` set to check. Data files a package
reads at run time go in `datas`.

ffmpeg won't go in this bundle: Kura downloads it on first setup (the "Tools" step in the setup
screen), which keeps the installer and every update smaller. ONNX Runtime with DirectML, the
upscaling model and the Anime4K shaders are small and will ship inside Kura.

## Upgrading

`uv lock --upgrade` updates PyInstaller and its hooks. Rebuild, then run the engine's handshake test
against the bundle, as the release workflow does before publishing:

```powershell
cd engine; $env:KURA_ENGINE_EXE = "dist\kura-engine\kura-engine.exe"; uv run pytest tests/test_cli.py -k announces
```
