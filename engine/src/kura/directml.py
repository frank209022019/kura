"""DirectML, ONNX Runtime's way onto the graphics card: which card, and one call at a time.

In one process, DirectML breaks in two ways (the owner's PC, NVIDIA, 2026-10-15). Two threads
loading or running models at once crash the graphics driver: a test that loads the AI model on
one thread while another runs it crashed every time, and never once the calls took turns, so
every DirectML session in the engine is made and run under LOCK, a frame or a token at a time.
And a model loaded and let go of while Whisper is loaded crashes Whisper's next step, turns or
no turns: the PC check doing that while Whisper heard a video ended the engine. So the queue,
which works one job at a time, lets Whisper go before it loads the AI model, and AI work outside
the queue (the PC check, See it first) runs in a process of its own (`kura check-model`, `kura
upscale-frame`): a process of its own has DirectML to itself.
"""

import threading

# The PC's high-performance card: on a laptop with two, its own rather than the processor's
# graphics that drive the screen.
PROVIDER = ("DmlExecutionProvider", {"performance_preference": "high_performance"})
LOCK = threading.RLock()
