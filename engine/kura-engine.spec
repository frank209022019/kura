# PyInstaller recipe for the engine the installer ships: a folder holding
# kura-engine.exe and its own Python, so the PC needs nothing else installed.
#
#   uv run pyinstaller kura-engine.spec --noconfirm   ->   dist/kura-engine/
#
# See docs/stack/pyinstaller.md.
from PyInstaller.utils.hooks import copy_metadata

a = Analysis(
    ["src/kura/__main__.py"],
    pathex=["src"],
    datas=[
        *copy_metadata("kura"),  # kura.__version__ reads the package's metadata
        ("src/kura/downloads.json", "kura"),  # what Kura downloads on first run
    ],
    # Never used at run time, though optional imports would pull them in: setuptools (through
    # distutils) and pytest (anyio's test runner).
    excludes=["setuptools", "_distutils_hack", "distutils", "pkg_resources", "_pytest", "pytest"],
)
# Windows 10 and 11 have the Universal C Runtime built in. Without this, PyInstaller copies it from
# whichever folder on PATH happens to hold it (a JDK's, say), so builds would differ between PCs.
a.binaries = [b for b in a.binaries if not b[0].lower().startswith(("api-ms-win-", "ucrtbase"))]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="kura-engine",
    console=True,  # a console program; the app starts it without a window
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="kura-engine", upx=False)
