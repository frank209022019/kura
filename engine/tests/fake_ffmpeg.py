"""Stands in for ffmpeg in tests: python fake_ffmpeg.py <ffmpeg's arguments>.

It answers the commands kura/core/convert.py builds, without converting anything:

- idet: reports a progressive picture, or an interlaced one for a file named "interlaced";
- the AI model's decoder: writes KURA_FAKE_FRAMES raw frames of KURA_FAKE_SIZE (4x2) to its
  output; its encoder: reads its input to the end and writes the file it's given;
- one whole conversion: writes the file, telling its progress the way -progress does;
- a test play: says nothing, as ffmpeg does when a file plays.

KURA_FAKE_FAIL names a step that fails instead: "encode", "play" or "frame", "decode" (once its
frames are out, as a decoder meeting damage), or "convert" (one command, 1,200 frames in).
KURA_FAKE_SLOW is the seconds the decoder takes over each frame (none), so a test can stop a
conversion mid-way. KURA_FAKE_ROUNDS makes a test play do what real ffmpeg does at some points of
a file that plays well: rounding the frames' times to the frame rate, it gives two the same one
and complains of it, unless the times are kept as the file has them (-enc_time_base demux).
"""

import os
import sys
import time
from pathlib import Path


def main() -> None:
    args = sys.argv[1:]
    fail = os.environ.get("KURA_FAKE_FAIL", "")
    if "idet" in args:
        source = Path(args[args.index("-i") + 1])
        tff = 420 if "interlaced" in source.name else 3
        print(
            f"[Parsed_idet_0 @ 0] Multi frame detection: TFF: {tff} BFF: 0 Progressive: 150",
            file=sys.stderr,
        )
        return
    if (
        args[-1] == "-"
        and "rawvideo" in args
        and "-i" in args
        and args[args.index("-i") + 1] != "-"
    ):
        width, height = (int(n) for n in os.environ.get("KURA_FAKE_SIZE", "4x2").split("x"))
        frames = int(os.environ.get("KURA_FAKE_FRAMES", "5"))
        if "-frames:v" in args:  # one frame, for a comparison
            frames = min(frames, int(args[args.index("-frames:v") + 1]))
        frame = bytes(width * height * 3 * 4)
        slow = float(os.environ.get("KURA_FAKE_SLOW", "0"))
        for _ in range(frames):
            time.sleep(slow)
            sys.stdout.buffer.write(frame)
            sys.stdout.buffer.flush()
        if fail == "decode":
            print("[h264 @ 0000] error while decoding MB 23 11", file=sys.stderr)
            print("Error while decoding stream #0:0: Invalid data found", file=sys.stderr)
            sys.exit(1)
        return
    if "-i" in args and args[args.index("-i") + 1] == "-":
        received = len(sys.stdin.buffer.read())
        if fail == "encode":
            print("hevc_nvenc: No capable devices found", file=sys.stderr)
            sys.exit(1)
        Path(args[-1]).write_bytes(f"converted {received} bytes of frames".encode())
        return
    if "-progress" in args:
        if fail == "encode":
            print("hevc_nvenc: No capable devices found", file=sys.stderr)
            sys.exit(1)
        if fail == "convert":
            print("frame=1200\nfps=24.0\nprogress=continue", flush=True)
            print("Error while decoding stream #0:0: Invalid data found", file=sys.stderr)
            sys.exit(1)
        source = Path(args[args.index("-i") + 1])
        for frame in (10, 20, 30):
            print(f"frame={frame}\nfps=24.0\nprogress=continue", flush=True)
        Path(args[-1]).write_bytes(b"converted " + source.read_bytes())
        print("frame=30\nprogress=end", flush=True)
        return
    if "-frames:v" in args and args[-1].endswith(".png"):  # a frame to compare
        if fail == "frame":
            print("Invalid data found when processing input", file=sys.stderr)
            sys.exit(1)
        Path(args[-1]).write_bytes(b"png of " + " ".join(args).encode())
        return
    if "null" in args:  # a test play
        if fail == "play":
            print("Invalid data found when processing input", file=sys.stderr)
            sys.exit(1)
        if os.environ.get("KURA_FAKE_ROUNDS") and "demux" not in args:
            print(
                "[null @ 0000] Application provided invalid, non monotonically increasing dts to "
                "muxer in stream 0: 6 >= 6",
                file=sys.stderr,
            )
        return
    print(f"fake_ffmpeg doesn't know {args}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
