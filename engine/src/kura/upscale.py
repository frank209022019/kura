"""Real-ESRGAN on the graphics card, a frame at a time, between two ffmpegs.

ONNX Runtime runs the model through DirectML (see docs/stack/upscaling.md). One ffmpeg decodes the
source to raw frames of planar float RGB, the model upscales each, and a second ffmpeg encodes
them. The three run side by side, so the card never waits for a frame to be read or written.
kura/core/convert.py builds the two commands.
"""

import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import IO, Protocol

import numpy as np
import numpy.typing as npt
import onnxruntime as ort

MODEL = Path(__file__).parent / "assets" / "realesr-animevideov3.onnx"
_BUFFERED = 8  # frames waiting on either side of the model

type Frame = npt.NDArray[np.float32]  # (1, 3, height, width): planes G, B, R from 0 to 1


class Upscaler(Protocol):
    def __call__(self, frame: Frame, /) -> Frame: ...


class UpscaleError(Exception):
    """The model, or one of the ffmpegs around it, stopped. The message says which and why."""


def model(width: int, height: int, path: Path = MODEL) -> Upscaler:
    """The model on the graphics card, ready for frames of this size. Raises UpscaleError when
    the card can't run it (DirectML needs a DirectX 12 card)."""
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.enable_mem_pattern = False  # DirectML asks for both of these
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.add_free_dimension_override_by_name("w", width)  # a fixed size runs faster
    options.add_free_dimension_override_by_name("h", height)
    try:
        session = ort.InferenceSession(
            str(path), options, providers=[("DmlExecutionProvider", {"device_id": 0})]
        )
    except Exception as error:  # ONNX Runtime raises its own kinds, all of them plain Exceptions
        raise UpscaleError(f"The graphics card couldn't run the AI model ({error}).") from error

    def upscale(frame: Frame) -> Frame:
        return session.run(None, {"frame": frame})[0]

    return upscale


def upscaled_size(upscale: Upscaler, width: int, height: int) -> tuple[int, int]:
    """How big the model's frames come out from frames of this size, as (width, height)."""
    out = upscale(np.zeros((1, 3, height, width), np.float32))
    return out.shape[3], out.shape[2]


def pipe(
    decoder: IO[bytes],
    encoder: IO[bytes],
    upscale: Upscaler,
    width: int,
    height: int,
    *,
    done: Callable[[int], None],
    stop: Callable[[], bool] = lambda: False,
) -> int:
    """Upscales every frame the decoder writes into the encoder, in order, and returns how many.
    `done` hears how many frames are through after each one; `stop` ends it early. The encoder's
    input is closed at the end either way, so it can finish its file."""
    size = width * height * 3 * 4
    decoded: queue.Queue[Frame | None] = queue.Queue(maxsize=_BUFFERED)
    upscaled: queue.Queue[Frame | None] = queue.Queue(maxsize=_BUFFERED)
    problems: list[str] = []

    def read() -> None:
        try:
            while not stop() and not problems:
                chunk = decoder.read(size)
                if len(chunk) < size:
                    break  # the end (a cut-off last frame is left out)
                decoded.put(np.frombuffer(chunk, np.float32).reshape(1, 3, height, width))
        except OSError as error:
            problems.append(f"The decoder stopped ({error.strerror or error}).")
        finally:
            decoded.put(None)

    def write() -> None:
        try:
            while (frame := upscaled.get()) is not None:
                if not problems:
                    encoder.write(frame.tobytes())
        except OSError as error:
            problems.append(f"The encoder stopped ({error.strerror or error}).")
            while upscaled.get() is not None:
                pass  # let the model's side finish
        finally:
            encoder.close()

    reader = threading.Thread(target=read, name="frames in", daemon=True)
    writer = threading.Thread(target=write, name="frames out", daemon=True)
    reader.start()
    writer.start()
    count = 0
    try:
        while (frame := decoded.get()) is not None:
            if stop() or problems:
                continue  # drain what's left so the reader can finish
            upscaled.put(upscale(frame))
            count += 1
            done(count)
    finally:
        upscaled.put(None)
        reader.join()
        writer.join()
    if problems:
        raise UpscaleError(problems[0])
    return count
