"""Build the Anime4K shader Kura ships (src/kura/assets/anime4k-mode-a-hq.glsl) from Anime4K's
release v4.0 (Anime4K_v4.0.zip, MIT, bloc97).

It is Anime4K's "Mode A (HQ)" for 720p and similar sources, its six shaders one after another in
the order Anime4K's own instructions give them, with LF line endings:

    cd engine
    uv run python tools/build_shaders.py Anime4K_v4.0.zip
"""

import hashlib
import sys
import zipfile
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[1] / "src/kura/assets/anime4k-mode-a-hq.glsl"
RELEASE = "139cd282086457c5adc79caf7b75b8b825091d71c9b54958c18745fea62d7ed7"  # the zip's SHA-256
MODE_A_HQ = (
    "Anime4K_Clamp_Highlights.glsl",
    "Anime4K_Restore_CNN_VL.glsl",
    "Anime4K_Upscale_CNN_x2_VL.glsl",
    "Anime4K_AutoDownscalePre_x2.glsl",
    "Anime4K_AutoDownscalePre_x4.glsl",
    "Anime4K_Upscale_CNN_x2_M.glsl",
)


def main() -> None:
    release = Path(sys.argv[1])
    if hashlib.sha256(release.read_bytes()).hexdigest() != RELEASE:
        sys.exit(f"{release} isn't Anime4K_v4.0.zip.")
    with zipfile.ZipFile(release) as archive:
        shader = b"".join(archive.read(name) for name in MODE_A_HQ).replace(b"\r\n", b"\n")
    OUTPUT.write_bytes(shader)
    print(f"{OUTPUT.name}: {len(shader)} bytes, SHA-256 {hashlib.sha256(shader).hexdigest()}")


if __name__ == "__main__":
    main()
