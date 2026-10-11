# ffmpeg (reading and converting video)

[ffmpeg](https://ffmpeg.org) 9.0.2 reads what each video holds (`ffprobe`) and does the conversion
work: decoding, deinterlacing, resizing, Anime4K through libplacebo, and encoding HEVC 10-bit with
NVENC. Kura doesn't ship it: it downloads one pinned build the first time it starts, from the list
in [engine/src/kura/downloads.json](../../engine/src/kura/downloads.json), the same list the
installer shows (see [releasing.md](../releasing.md)).

## Which build, and why

- **BtbN's LGPL shared build for Windows** (`ffmpeg-n9.0.2-…-win64-lgpl-shared-9.0.zip`,
  77 MB): the release branch, built with NVENC, libplacebo and Vulkan, and nothing under the GPL,
  so Kura's MIT code may drive it. The shared build keeps ffmpeg's libraries as separate DLLs.
- **Pinned to a month's last build.** BtbN keeps the last build of each month for two years, while
  "latest" changes daily. `downloads.json` names one such build with its size and SHA-256, and
  Kura uses the download only when both match.
- **Downloaded from BtbN, not from Kura.** The PC fetches it from where it's published, with
  its licence and source there.

The upscaling test of 2026-10-11 used this build: Anime4K through libplacebo, Lanczos and NVENC
HEVC 10-bit all ran without trouble on the GTX 1660 Super.

## Where it lives

`%LOCALAPPDATA%\Kura\tools\ffmpeg\` holds the build's `bin` folder (ffmpeg.exe, ffprobe.exe and
their DLLs) and `kura-download.json`, which names the build and every file unpacked from it. When
`downloads.json` moves to a new build, the next start sees the difference and offers the download
again; the new build replaces the old one. A file that goes missing (an antivirus, say) also makes
ffmpeg "missing" again, and so does an ffprobe that can't even say its version: a scan then stops
without marking any file, and Setup offers the download. A file that makes ffprobe crash while
ffprobe itself still works is that file's problem, so one bad file never blocks a scan.
[kura/tools.py](../../engine/src/kura/tools.py) does the downloading, checking and unpacking, and
finds the programs (`Tools.path("ffprobe")`).

In development, set `KURA_FFMPEG_DIR` to a folder holding `ffprobe.exe` and `ffmpeg.exe` to skip
the download.

## Running it

Kura runs ffmpeg and ffprobe as child processes with `CREATE_NO_WINDOW`, so no console window
flashes, and reads ffprobe's JSON (`-show_format -show_streams -show_chapters`), which
[kura/core/media.py](../../engine/src/kura/core/media.py) turns into a `MediaInfo`.

## Moving to a newer build

1. Pick the last build of a month on [BtbN's releases](https://github.com/BtbN/FFmpeg-Builds/releases)
   (`autobuild-YYYY-MM-<last day>-…`) and its `win64-lgpl-shared` zip for the newest release branch.
2. Put its address, size and SHA-256 (the release lists each asset's digest) in `downloads.json`.
3. Run the engine tests, and check a scan and a conversion on real files before releasing.
