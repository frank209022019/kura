"""The AI model's frame loop, with a stand-in for the model: no graphics card needed."""

import io
import sys
import threading
import types

import numpy as np
import pytest

from kura.upscale import Frame, UpscaleError, model, pipe, upscaled_size

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


class Session:
    """ONNX Runtime's session, standing in, running where `providers` says."""

    def __init__(self, providers: list[str]) -> None:
        self.providers = providers

    def get_providers(self) -> list[str]:
        return self.providers


def runtime(
    monkeypatch: pytest.MonkeyPatch, said: list[str], ran: list[str], asked: list[object]
) -> None:
    """ONNX Runtime standing in, its sessions running on `ran`: no graphics card needed."""

    class Options:
        def add_free_dimension_override_by_name(self, name: str, size: int) -> None: ...

    def session(path: str, options: Options, providers: object) -> Session:
        said.append("model loaded")
        asked.append(providers)
        return Session(ran)

    onnxruntime = types.ModuleType("onnxruntime")
    vars(onnxruntime).update(
        disable_telemetry_events=lambda: said.append("no reports"),
        SessionOptions=Options,
        GraphOptimizationLevel=types.SimpleNamespace(ORT_ENABLE_ALL=99),
        ExecutionMode=types.SimpleNamespace(ORT_SEQUENTIAL=0),
        InferenceSession=session,
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", onnxruntime)


def test_onnx_runtime_reports_nothing_to_microsoft(monkeypatch: pytest.MonkeyPatch):
    """Its Windows builds send usage reports through Windows unless told not to, first."""
    said: list[str] = []
    runtime(monkeypatch, said, ["DmlExecutionProvider", "CPUExecutionProvider"], [])

    model(WIDTH, HEIGHT)

    assert said == ["no reports", "model loaded"]


def test_the_model_runs_on_the_pcs_high_performance_card(monkeypatch: pytest.MonkeyPatch):
    """On a laptop with two, the card of its own rather than the processor's graphics."""
    asked: list[object] = []
    runtime(monkeypatch, [], ["DmlExecutionProvider", "CPUExecutionProvider"], asked)

    model(WIDTH, HEIGHT)

    assert asked == [[("DmlExecutionProvider", {"performance_preference": "high_performance"})]]


def test_a_card_without_directx_12_cant_run_the_model(monkeypatch: pytest.MonkeyPatch):
    """ONNX Runtime falls back to the processor by itself: far too slow, so it's refused."""
    runtime(monkeypatch, [], ["CPUExecutionProvider"], [])

    with pytest.raises(UpscaleError, match="it needs DirectX 12"):
        model(WIDTH, HEIGHT)


def test_a_model_that_fails_part_way_stops_it_with_the_reason():
    decoder, encoder = io.BytesIO(frames(200)), Encoder()  # far more than the buffers hold
    calls = 0

    def failing(frame: Frame) -> Frame:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("D3D12: the device was removed")
        return doubled(frame)

    outcome: list[BaseException | int] = []

    def run() -> None:
        try:
            outcome.append(pipe(decoder, encoder, failing, WIDTH, HEIGHT, done=lambda _: None))
        except BaseException as error:  # kept, to look at below
            outcome.append(error)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=10)

    assert not worker.is_alive(), "the pipe hung after the model failed"
    [error] = outcome
    assert isinstance(error, UpscaleError)
    assert "the device was removed" in str(error)
    assert encoder.closed


class Turns:
    """DirectML's lock, standing in: counts who's inside (kura/directml.py)."""

    def __init__(self) -> None:
        self.inside = 0

    def __enter__(self) -> None:
        self.inside += 1

    def __exit__(self, *_: object) -> None:
        self.inside -= 1


def test_the_model_is_loaded_and_run_taking_turns_on_the_card(monkeypatch: pytest.MonkeyPatch):
    """Two threads on DirectML at once crash the graphics driver: the PC check loading the model
    while Whisper heard a video ended the engine (2026-10-15)."""
    turns = Turns()
    seen: list[int] = []

    class Running(Session):
        def run(self, _outputs: object, feed: dict[str, Frame]) -> list[Frame]:
            seen.append(turns.inside)
            return [doubled(feed["frame"])]

    def session(path: str, options: object, providers: object) -> Running:
        seen.append(turns.inside)
        return Running(["DmlExecutionProvider"])

    runtime(monkeypatch, [], ["DmlExecutionProvider"], [])
    monkeypatch.setattr(sys.modules["onnxruntime"], "InferenceSession", session)
    monkeypatch.setattr("kura.directml.LOCK", turns)

    upscale = model(WIDTH, HEIGHT)
    upscale(np.zeros((1, 3, HEIGHT, WIDTH), np.float32))

    assert seen == [1, 1]  # loading, then the frame: each inside the lock
    assert turns.inside == 0
