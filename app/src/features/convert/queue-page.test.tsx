import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type Job, type QueueStatus } from "@/lib/engine";
import { fakeEngine, READY } from "@/test/engine";
import { QueuePage } from "./queue-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function job(id: number, more: Partial<Job> = {}): Job {
  const code = `S01E${String(id).padStart(2, "0")}`;
  return {
    id,
    fileId: id,
    path: `D:\\Anime\\TV\\Dragon Ball Z (1989)\\Season 01\\Dragon Ball Z (1989) - ${code}.mkv`,
    label: `Dragon Ball Z · ${code}`,
    titleId: 1,
    title: "Dragon Ball Z",
    season: 1,
    episode: id,
    method: "best",
    state: "queued",
    gpuSeconds: 3600,
    addedAt: "2026-10-11T10:00:00+02:00",
    startedAt: null,
    finishedAt: null,
    problem: null,
    sourceSize: 233_000_000,
    outputSize: null,
    width: 1440,
    height: 1080,
    ...more,
  };
}

const RUNNING: QueueStatus = {
  paused: false,
  schedule: "now",
  waitsForNight: false,
  problem: null,
  running: {
    job: job(5, { state: "running" }),
    stage: "converting",
    frames: 22_000,
    total: 34_920,
    secondsLeft: 1080,
    fps: 11.4,
  },
  queued: [job(6), job(7), job(8, { season: 2, episode: 1, label: "Dragon Ball Z · S02E01" })],
  gpuSeconds: 3 * 3600 + 1080,
  today: [
    job(3, { state: "done", outputSize: 412_000_000, finishedAt: "2026-10-11T13:16:00+02:00" }),
    job(9, {
      state: "failed",
      label: "Trigun · S01E09",
      problem: "The source file is damaged at 04:12. The original is untouched.",
      finishedAt: "2026-10-11T12:00:00+02:00",
    }),
  ],
  gpu: { busy: 97, celsius: 71 },
};

function renderQueue() {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={["/convert/queue"]}>
          <Routes>
            <Route path="/convert/queue" element={<QueuePage />} />
            <Route path="/convert" element={<p>The choosing screen</p>} />
            <Route path="/history" element={<p>History</p>} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

function sent(fetch: ReturnType<typeof fakeEngine>, method: string, path: string) {
  return fetch.mock.calls.filter(
    ([input, init]) =>
      (init?.method ?? "GET") === method && new URL(String(input)).pathname === path,
  );
}

describe("QueuePage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("shows the file converting now, how far it is, and the card", async () => {
    fakeEngine({ "/queue": RUNNING });
    renderQueue();

    const now = await screen.findByRole("region", { name: "Now converting" });
    expect(now).toHaveTextContent("Dragon Ball Z · S01E05");
    expect(now).toHaveTextContent("63% · 18 min left");
    expect(now).toHaveTextContent("Real-ESRGAN → HEVC 10-bit · 1440 × 1080");
    expect(screen.getByRole("img", { name: "Graphics card 97 percent busy" })).toBeInTheDocument();
    expect(now).toHaveTextContent("71 °C");
    expect(now).toHaveTextContent("11.4 fps");
    expect(screen.getByText("Upscale").closest("li")).toHaveAttribute("aria-current", "step");
    expect(
      screen.getByText("Running · 3 in the queue · about 3 h of GPU time"),
    ).toBeInTheDocument();
  });

  it("pauses everything, by the button or the space bar", async () => {
    const fetch = fakeEngine({ "/queue": RUNNING, "POST /queue/pause": RUNNING });
    renderQueue();

    (await screen.findByRole("button", { name: /Pause all/ })).click();
    await waitFor(() => expect(sent(fetch, "POST", "/queue/pause")).toHaveLength(1));

    fireEvent.keyDown(document.body, { code: "Space" });
    await waitFor(() => expect(sent(fetch, "POST", "/queue/pause")).toHaveLength(2));
  });

  it("skips the file converting now", async () => {
    const fetch = fakeEngine({ "/queue": RUNNING, "POST /queue/5/skip": null });
    renderQueue();

    (await screen.findByRole("button", { name: "Skip this file" })).click();

    await waitFor(() => expect(sent(fetch, "POST", "/queue/5/skip")).toHaveLength(1));
  });

  it("lists what's next a season at a time, and moves a file up", async () => {
    const fetch = fakeEngine({ "/queue": RUNNING, "POST /queue/7/move": null });
    renderQueue();

    const next = await screen.findByRole("region", { name: "Up next" });
    expect(next).toHaveTextContent("Dragon Ball Z · Season 1 · 2 left");
    expect(next).toHaveTextContent("S01E06Dragon Ball Z (1989) - S01E06.mkvBest≈ 1 h");
    expect(next).toHaveTextContent("Dragon Ball Z · Season 21 · ≈ 1 h");

    fireEvent.keyDown(screen.getByRole("button", { name: "More for Dragon Ball Z · S01E07" }), {
      key: "Enter",
    });
    (await screen.findByRole("menuitem", { name: "Convert next" })).click();

    await waitFor(() => expect(sent(fetch, "POST", "/queue/7/move")).toHaveLength(1));
    const [[, init]] = sent(fetch, "POST", "/queue/7/move") as [[unknown, RequestInit]];
    expect(JSON.parse(String(init.body))).toEqual({ before: 6 });
  });

  it("counts today's results, and tries a failed file again", async () => {
    const fetch = fakeEngine({ "/queue": RUNNING, "POST /queue/9/retry": null });
    renderQueue();

    const today = await screen.findByRole("region", { name: "Today" });
    expect(today).toHaveTextContent("1converted1failed412 MBwritten");
    expect(today).toHaveTextContent(
      "Trigun · S01E09 failedThe source file is damaged at 04:12. The original is untouched.",
    );
    screen.getByRole("button", { name: "Try again" }).click();

    await waitFor(() => expect(sent(fetch, "POST", "/queue/9/retry")).toHaveLength(1));
  });

  it("converts at night only, when asked", async () => {
    const fetch = fakeEngine({
      "/queue": { ...RUNNING, running: null, schedule: "nights", waitsForNight: true },
      "PUT /queue/schedule": RUNNING,
    });
    renderQueue();

    expect(
      await screen.findByText("Files convert tonight, from 23:00 to 07:00."),
    ).toBeInTheDocument();
    expect(screen.getByText("Picks up again tonight at 23:00")).toBeInTheDocument();
    screen.getByRole("switch", { name: "Nights only, 23:00–07:00" }).click();

    await waitFor(() => expect(sent(fetch, "PUT", "/queue/schedule")).toHaveLength(1));
    const [[, init]] = sent(fetch, "PUT", "/queue/schedule") as [[unknown, RequestInit]];
    expect(JSON.parse(String(init.body))).toEqual({ schedule: "now" });
  });

  it("resumes a paused queue", async () => {
    const fetch = fakeEngine({
      "/queue": { ...RUNNING, running: null, paused: true },
      "POST /queue/resume": RUNNING,
    });
    renderQueue();

    expect(await screen.findByText(/The queue is paused/)).toBeInTheDocument();
    screen.getAllByRole("button", { name: /Resume/ })[0]?.click();

    await waitFor(() => expect(sent(fetch, "POST", "/queue/resume")).toHaveLength(1));
  });

  it("says when nothing waits, and leads to choosing", async () => {
    fakeEngine({ "/queue": { ...RUNNING, running: null, queued: [], today: [], gpuSeconds: 0 } });
    renderQueue();

    expect(await screen.findByRole("heading", { name: "Nothing waiting" })).toBeInTheDocument();
    screen.getByRole("link", { name: "Choose what to convert" }).click();
    expect(await screen.findByText("The choosing screen")).toBeInTheDocument();
  });

  it("says why nothing converts without ffmpeg", async () => {
    const problem = "Kura needs ffmpeg to convert. It's downloaded on the setup's Tools step.";
    fakeEngine({ "/queue": { ...RUNNING, running: null, problem } });
    renderQueue();

    expect(await screen.findByText(problem)).toBeInTheDocument();
  });
});
