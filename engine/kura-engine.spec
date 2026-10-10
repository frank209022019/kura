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
    datas=copy_metadata("kura"),  # kura.__version__ reads the package's metadata
)
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
