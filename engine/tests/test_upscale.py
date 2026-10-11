"""The AI model's frame loop, with a stand-in for the model: no graphics card needed."""

import io
import threading

import numpy as np
import pytest

from kura.upscale import Frame, UpscaleError, pipe, upscaled_size

WIDTH, HEIGHT = 4, 2  # tiny frames
FRAME_BYTES = WIDTH * HEIGHT * 3 * 4  # planar float RGB


def doubled(frame: Frame) -> Frame:
    """Stands in for the model: every pixel twice as wide and tall."""
    return frame.repeat(2, axis=2).repeat(2, axis=3)


def frames(count: int) -> bytes:
    return b"".join(
        np.full((1, 3, HEIGHT, WIDTH), number / 10, np.float32).tobytes() for number in range(count)
    )


class Encoder(io.BytesIO):
    """An encoder's standard input that keeps what it's given, and remembers being closed."""

    def __init__(self) -> None:
        super().__init__()
        self.kept = b""

    def close(self) -> None:
        self.kept = self.getvalue()
        super().close()


def test_every_frame_goes_through_the_model_in_order():
    decoder, encoder = io.BytesIO(frames(5)), Encoder()
    seen: list[int] = []

    count = pipe(decoder, encoder, doubled, WIDTH, HEIGHT, done=seen.append)

    assert count == 5
    out = np.frombuffer(encoder.kept, np.float32).reshape(5, 3, HEIGHT * 2, WIDTH * 2)
    assert [round(float(frame.mean()), 2) for frame in out] == [0.0, 0.1, 0.2, 0.3, 0.4]
    assert seen[-1] == 5  # told how far it has got


def test_it_stops_when_asked_and_closes_the_encoder():
    decoder, encoder = io.BytesIO(frames(50)), Encoder()
    stop = threading.Event()

    def done(count: int) -> None:
        if count == 3:
            stop.set()

    count = pipe(decoder, encoder, doubled, WIDTH, HEIGHT, done=done, stop=stop.is_set)

    assert count < 50
    assert encoder.closed


def test_a_broken_encoder_stops_it_with_the_reason():
    class Broken(io.BytesIO):
        def write(self, data: object) -> int:
            raise BrokenPipeError(32, "The pipe is being closed")

    with pytest.raises(UpscaleError, match="The encoder stopped"):
        pipe(io.BytesIO(frames(5)), Broken(), doubled, WIDTH, HEIGHT, done=lambda _: None)


def test_a_cut_off_last_frame_is_left_out():
    decoder, encoder = io.BytesIO(frames(2) + b"\0" * (FRAME_BYTES // 2)), Encoder()

    assert pipe(decoder, encoder, doubled, WIDTH, HEIGHT, done=lambda _: None) == 2


def test_the_model_says_how_big_its_frames_come_out():
    assert upscaled_size(doubled, 720, 480) == (1440, 960)
