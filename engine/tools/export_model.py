"""Export Real-ESRGAN's anime video model to the ONNX file Kura ships (src/kura/assets).

Kura feeds the model one frame at a time as ffmpeg's planar float RGB (gbrpf32le: planes G, B, R,
values 0 to 1). The exported graph turns that into R, G, B, runs the model (4x), scales the result
down 2x with a box filter (720x540 becomes 1440x1080), and hands back planar G, B, R floats ready
to pipe into ffmpeg. Width and height stay free (named w and h), so one file serves every size.

Needs PyTorch and onnx, which the engine doesn't ship, and the model's weights from Real-ESRGAN's
release v0.2.5.0 (realesr-animevideov3.pth, BSD-3-Clause, Xintao Wang):

    cd engine
    uv run --with torch --with onnx python tools/export_model.py realesr-animevideov3.pth
"""

import hashlib
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from torch import nn
from torch.nn import functional

OUTPUT = Path(__file__).resolve().parents[1] / "src/kura/assets/realesr-animevideov3.onnx"
WEIGHTS = "b8a8376811077954d82ca3fcf476f1ac3da3e8a68a4f4d71363008000a18b75d"  # the .pth's SHA-256


class SRVGGNetCompact(nn.Module):
    """realesrgan/archs/srvgg_arch.py (BSD-3-Clause, Xintao Wang): the anime video model."""

    def __init__(self, num_feat: int = 64, num_conv: int = 16, upscale: int = 4) -> None:
        super().__init__()
        self.upscale = upscale
        self.body = nn.ModuleList(
            [nn.Conv2d(3, num_feat, 3, 1, 1), nn.PReLU(num_parameters=num_feat)]
        )
        for _ in range(num_conv):
            self.body.append(nn.Conv2d(num_feat, num_feat, 3, 1, 1))
            self.body.append(nn.PReLU(num_parameters=num_feat))
        self.body.append(nn.Conv2d(num_feat, 3 * upscale * upscale, 3, 1, 1))
        self.upsampler = nn.PixelShuffle(upscale)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = x
        for layer in self.body:
            out = layer(out)
        nearest = functional.interpolate(x, scale_factor=self.upscale, mode="nearest")
        return self.upsampler(out) + nearest


class Frame(nn.Module):
    """ffmpeg's G, B, R planes in, the model, a 2x box downscale, G, B, R planes out."""

    def __init__(self, net: nn.Module) -> None:
        super().__init__()
        self.net = net

    def forward(self, gbr: torch.Tensor) -> torch.Tensor:
        rgb = torch.cat([gbr[:, 2:3], gbr[:, 0:1], gbr[:, 1:2]], dim=1)
        out = functional.avg_pool2d(self.net(rgb), 2).clamp(0.0, 1.0)
        return torch.cat([out[:, 1:2], out[:, 2:3], out[:, 0:1]], dim=1)


def main() -> None:
    weights = Path(sys.argv[1])
    if hashlib.sha256(weights.read_bytes()).hexdigest() != WEIGHTS:
        sys.exit(f"{weights} isn't realesr-animevideov3.pth from Real-ESRGAN v0.2.5.0.")
    net = SRVGGNetCompact()
    net.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True)["params"])
    model = Frame(net.eval()).eval()
    example = torch.rand(1, 3, 64, 96)
    torch.onnx.export(
        model,
        (example,),
        str(OUTPUT),
        input_names=["frame"],
        output_names=["upscaled"],
        dynamic_axes={"frame": {2: "h", 3: "w"}, "upscaled": {2: "h2", 3: "w2"}},
        opset_version=18,
        dynamo=False,
    )
    with torch.no_grad():
        expected = model(example).numpy()
    session = ort.InferenceSession(str(OUTPUT), providers=["CPUExecutionProvider"])
    got = session.run(None, {"frame": example.numpy()})[0]
    print(f"{OUTPUT.name}: largest difference from PyTorch {np.abs(got - expected).max():.2e}")
    print(f"SHA-256 {hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
