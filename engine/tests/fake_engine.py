"""Stands in for the engine's own process in tests: python fake_engine.py <command> ...

- `check-model [--time]`: says whether the AI model runs, after a line of ONNX Runtime's own
  words, as `kura check-model` does;
- `upscale-frame W H`: reads a W by H frame of planar float RGB and writes it back twice as wide
  and tall, after its size as a JSON line, as `kura upscale-frame` does.

KURA_FAKE_MODEL says what happens: "runs" (the default); "no", the model doesn't run (the frame
fails, saying so); or "crash", the process ends the way a graphics driver failing ends one,
saying nothing.
"""

import json
import os
import sys

import numpy as np


def main() -> None:
    what = os.environ.get("KURA_FAKE_MODEL", "runs")
    if what == "crash":
        os._exit(3)  # as an abort does: no answer at all
    command = sys.argv[1]
    if command == "check-model":
        print("*************** EP Error ***************")  # ONNX Runtime talks on standard output
        runs = what == "runs"
        print(
            json.dumps({"runs": runs, "megapixels": 2.5 if runs and "--time" in sys.argv else None})
        )
        return
    width, height = int(sys.argv[2]), int(sys.argv[3])
    if what == "no":
        print("The graphics card couldn't run the AI model: it needs DirectX 12.", file=sys.stderr)
        sys.exit(1)
    frame = np.frombuffer(sys.stdin.buffer.read(), np.float32).reshape(1, 3, height, width)
    made = frame.repeat(2, axis=2).repeat(2, axis=3)
    out = sys.stdout.buffer
    out.write(json.dumps({"width": width * 2, "height": height * 2}).encode() + b"\n")
    out.write(made.tobytes())


if __name__ == "__main__":
    main()
