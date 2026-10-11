import type { Convertible } from "@/lib/engine";

/** A video the Convert screen lists: by default a 24-minute SD episode of Dragon Ball Z. */
export function convertible(
  fileId: number,
  more: Partial<Convertible> = {},
  gpu: { best?: number; fast?: number; reencode?: number } = {},
): Convertible {
  return {
    fileId,
    label: `Dragon Ball Z · S01E${String(fileId).padStart(2, "0")}`,
    titleId: 1,
    title: "Dragon Ball Z",
    season: 1,
    episode: fileId,
    seconds: 1440,
    height: 480,
    aspect: "4:3",
    size: 233_000_000,
    drive: "D:",
    ways: {
      best: { method: "best", gpuSeconds: gpu.best ?? 3600 },
      fast: { method: "fast", gpuSeconds: gpu.fast ?? 720 },
      reencode: { method: "reencode", gpuSeconds: gpu.reencode ?? 180 },
    },
    outputBytes: 450_000_000,
    waiting: false,
    broken: false,
    ...more,
  };
}
