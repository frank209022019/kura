import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  type ConvertOptions,
  EngineProvider,
  type FranchiseSummary,
  type QueueStatus,
  type TitleSummary,
} from "@/lib/engine";
import { convertible } from "@/test/convert";
import { fakeEngine, READY } from "@/test/engine";
import { ConvertPage } from "./convert-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const OPTIONS: ConvertOptions = {
  standard: "Cinema 1080p",
  files: [
    convertible(1),
    convertible(2),
    convertible(3, { season: 2, episode: 1, label: "Dragon Ball Z · S02E01" }),
    convertible(4, { titleId: 2, title: "Dragon Ball GT", broken: true, ways: {} }),
    convertible(
      5,
      { titleId: 2, title: "Dragon Ball GT", height: 720, aspect: "16:9" },
      { best: 600, fast: 600, reencode: 120 },
    ),
  ],
  free: { "D:": 931_000_000_000 },
};
OPTIONS.files[4] = {
  ...(OPTIONS.files[4] as (typeof OPTIONS.files)[number]),
  ways: {
    best: { method: "fast", gpuSeconds: 600 },
    fast: { method: "fast", gpuSeconds: 600 },
    reencode: { method: "reencode", gpuSeconds: 120 },
  },
};

const FRANCHISES = [
  {
    id: 1,
    name: "Dragon Ball",
    titles: [
      { id: 1, name: "Dragon Ball Z" },
      { id: 2, name: "Dragon Ball GT" },
    ] as TitleSummary[],
  },
] as FranchiseSummary[];

const QUEUE: QueueStatus = {
  paused: false,
  schedule: "now",
  waitsForNight: false,
  problem: null,
  running: null,
  queued: [],
  gpuSeconds: 0,
  today: [],
  gpu: null,
};

function renderConvert() {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={["/convert"]}>
          <Routes>
            <Route path="/convert" element={<ConvertPage />} />
            <Route path="/convert/queue" element={<p>The queue</p>} />
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

describe("ConvertPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("lists what isn't at the standard by franchise, title and season", async () => {
    fakeEngine({ "/convert": OPTIONS, "/franchises": FRANCHISES, "/queue": QUEUE });
    renderConvert();

    expect(
      await screen.findByRole("checkbox", { name: /Dragon Ball\s*franchise/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Dragon Ball Z\s*3 left/ })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Season 1\s*2 episodes/ })).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: /Dragon Ball GT\s*1 left, 1 broken skipped/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("Nothing chosen yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose what to convert" })).toBeDisabled();
  });

  it("adds up what's chosen, and what each way takes", async () => {
    fakeEngine({ "/convert": OPTIONS, "/franchises": FRANCHISES, "/queue": QUEUE });
    renderConvert();

    (await screen.findByRole("checkbox", { name: /Season 1/ })).click();

    expect(await screen.findAllByText("2 episodes")).toHaveLength(2); // the season, and the chip
    expect(screen.getByText("48 min of video")).toBeInTheDocument();
    expect(screen.getByText("SD 480p · 4:3")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Best quality/ })).toHaveTextContent(
      "≈ 1 h per episode",
    );
    expect(screen.getByRole("radio", { name: /Fast/ })).toHaveTextContent("≈ 12 min per episode");
    expect(screen.getByText("≈ 2 h")).toBeInTheDocument();
    expect(screen.getByText("466 MB → 900 MB")).toBeInTheDocument();
    expect(screen.getByText("free, plenty for this")).toBeInTheDocument();
    expect(
      screen.getByText("4:3 shows stay 4:3 at 1440 × 1080. Nothing is stretched or cropped."),
    ).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Dragon Ball Z\s*3 left/ })).toBePartiallyChecked();
  });

  it("says when a file gets less than the way chosen", async () => {
    fakeEngine({ "/convert": OPTIONS, "/franchises": FRANCHISES, "/queue": QUEUE });
    renderConvert();

    (await screen.findByRole("checkbox", { name: /Dragon Ball GT/ })).click();

    expect(
      await screen.findByText(/1 file gets Fast instead: the AI model is for SD/),
    ).toBeInTheDocument();
  });

  it("queues what's chosen to start now, then shows the queue", async () => {
    const fetch = fakeEngine({
      "/convert": OPTIONS,
      "/franchises": FRANCHISES,
      "/queue": QUEUE,
      "POST /queue": { added: 3 },
    });
    renderConvert();

    (await screen.findByRole("checkbox", { name: /Dragon Ball Z\s*3 left/ })).click();
    (await screen.findByRole("radio", { name: /Re-encode only/ })).click();
    (await screen.findByRole("button", { name: "Add 3 episodes to the queue" })).click();

    expect(await screen.findByText("The queue")).toBeInTheDocument();
    const [[, init]] = sent(fetch, "POST", "/queue") as [[unknown, RequestInit]];
    expect(JSON.parse(String(init.body))).toEqual({
      files: [1, 2, 3],
      method: "reencode",
      when: "now",
    });
  });

  it("can queue for the night instead, in one step", async () => {
    const fetch = fakeEngine({
      "/convert": OPTIONS,
      "/franchises": FRANCHISES,
      "/queue": QUEUE,
      "POST /queue": { added: 2 },
    });
    renderConvert();

    (await screen.findByRole("checkbox", { name: /Season 1/ })).click();
    (await screen.findByRole("radio", { name: /Nights only/ })).click();
    (await screen.findByRole("button", { name: "Add 2 episodes to the queue" })).click();

    expect(await screen.findByText("The queue")).toBeInTheDocument();
    const [[, init]] = sent(fetch, "POST", "/queue") as [[unknown, RequestInit]];
    expect(JSON.parse(String(init.body))).toMatchObject({ when: "nights" });
    expect(sent(fetch, "PUT", "/queue/schedule")).toHaveLength(0);
  });

  it("warns of a drive without room, though another has plenty", async () => {
    fakeEngine({
      "/convert": {
        ...OPTIONS,
        files: [convertible(1), convertible(2, { drive: "F:" })],
        free: { "D:": 931_000_000_000, "F:": 200_000_000 },
      },
      "/franchises": FRANCHISES,
      "/queue": QUEUE,
    });
    renderConvert();

    (await screen.findByRole("checkbox", { name: /Dragon Ball Z\s*2 left/ })).click();

    expect(await screen.findByText("Space on F:")).toBeInTheDocument();
    expect(screen.getByText("free: not enough, this needs 563 MB")).toBeInTheDocument();
  });

  it("shows a frame before and after, at three points of the file", async () => {
    const problem = "The graphics card couldn't run the AI model (DirectML needs DirectX 12).";
    const fetch = fakeEngine({
      "/convert": OPTIONS,
      "/franchises": FRANCHISES,
      "/queue": QUEUE,
      "/convert/1/preview/after": () => Response.json({ detail: problem }, { status: 422 }),
    });
    renderConvert();

    const panel = await screen.findByRole("region", { name: "See it first" });
    expect(panel).toHaveTextContent("Dragon Ball Z · S01E01 · drag the handle");
    expect(panel).toHaveTextContent("After · best quality 1080p");
    expect(screen.getByRole("button", { name: "12:00" })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText(problem)).toBeInTheDocument();

    screen.getByRole("button", { name: "3:36" }).click();

    await waitFor(() =>
      expect(
        fetch.mock.calls.some(([input]) =>
          String(input).endsWith("/convert/1/preview/after?way=best&point=0"),
        ),
      ).toBe(true),
    );
  });

  it("says when everything is at the standard", async () => {
    fakeEngine({
      "/convert": { ...OPTIONS, files: [] },
      "/franchises": FRANCHISES,
      "/queue": QUEUE,
    });
    renderConvert();

    expect(
      await screen.findByRole("heading", { name: "Everything is at your standard" }),
    ).toBeInTheDocument();
  });
});
