import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type EngineStatus, type Health } from "@/lib/engine";
import { fakeEngine, NO_LIBRARY, NO_SCAN, READY, SETTINGS } from "@/test/engine";
import { HomePage } from "./home-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const health: Health = {
  status: "ok",
  version: "0.1.0",
  dataDir: "C:\\Users\\you\\AppData\\Local\\Kura",
  schemaVersion: 3,
};

const FOLDER = {
  id: 1,
  path: "D:\\Anime",
  addedAt: "2026-10-11T09:30:00+00:00",
  available: true,
  files: 3,
  unread: 0,
  problems: 1,
};

/** The engine's answers for a library that's empty and already set up. */
function engineWith(answers: Record<string, unknown> = {}) {
  return fakeEngine({
    "/health": health,
    "/settings": SETTINGS,
    "/folders": [],
    "/library": NO_LIBRARY,
    "/scan": NO_SCAN,
    ...answers,
  });
}

function renderHome(engine: EngineStatus) {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? engine : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter>
          <Routes>
            <Route index element={<HomePage />} />
            <Route path="/setup" element={<p>Setup</p>} />
            <Route path="/scan" element={<p>Scan</p>} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

describe("HomePage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("shows an empty shelf and where the data lives once the engine runs", async () => {
    engineWith();
    renderHome(READY);

    expect(await screen.findByRole("heading", { name: "Your shelf is empty" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add a folder" })).toBeEnabled();
    expect(await screen.findByText("Running · version 0.1.0")).toBeInTheDocument();
    expect(screen.getByText(health.dataDir)).toBeInTheDocument();
    expect(screen.getByText("Ready · schema version 3")).toBeInTheDocument();
  });

  it("opens setup on the very first run", async () => {
    engineWith({ "/settings": { ...SETTINGS, setUp: false } });
    renderHome(READY);

    expect(await screen.findByText("Setup")).toBeInTheDocument();
  });

  it("shows the library by picture size once a scan has read it", async () => {
    engineWith({
      "/folders": [FOLDER],
      "/library": { ...NO_LIBRARY, folders: 1, files: 3, size: 407_000_000, sd: 3, problems: 1 },
      "/scan": { ...NO_SCAN, state: "done", stage: "done", found: 3, toRead: 3, read: 3 },
    });
    renderHome(READY);

    expect(
      await screen.findByRole("heading", { name: "Your videos by picture" }),
    ).toBeInTheDocument();
    expect(screen.getByText("3 videos · 0.4 GB · 1 folder")).toBeInTheDocument();
    expect(screen.getByText("1 file couldn't be read.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Scan again" })).toBeEnabled();
  });

  it("says when the engine isn't running, and offers to try again", async () => {
    engineWith();
    renderHome({ state: "failed", message: "It stopped unexpectedly.", details: "Traceback…" });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Kura's engine isn't running. It stopped unexpectedly.");
    expect(alert).toHaveTextContent("Nothing in your folders was touched.");
    expect(screen.getByText("Not running")).toBeInTheDocument();

    screen.getByRole("button", { name: "Try again" }).click();

    expect(shell.invoke).toHaveBeenCalledWith("restart_engine");
  });

  it("offers the engine's error lines only when there are some", async () => {
    engineWith();
    renderHome({ state: "failed", message: "It stopped unexpectedly.", details: "" });

    await screen.findByRole("alert");

    expect(screen.queryByRole("button", { name: "Copy details" })).not.toBeInTheDocument();
  });

  it("opens the downloads page to show every version and what changed", async () => {
    engineWith();
    renderHome(READY);

    (await screen.findByRole("button", { name: "Every version and what changed" })).click();

    expect(shell.invoke).toHaveBeenCalledWith("open_downloads_page");
  });
});
