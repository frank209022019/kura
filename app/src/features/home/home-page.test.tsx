import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type EngineStatus, type Health, type TitleSummary } from "@/lib/engine";
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

const DBZ: TitleSummary = {
  id: 1,
  kind: "series",
  name: "Dragon Ball Z",
  year: 1989,
  released: "1989-04-26",
  airing: false,
  hasPoster: false,
  files: 287,
  added: "2026-10-11T09:44:00+00:00",
  aired: 291,
  present: 287,
  missing: 4,
  specialsMissing: 0,
  upcoming: 0,
};
const BEBOP: TitleSummary = {
  ...DBZ,
  id: 2,
  name: "Cowboy Bebop",
  year: 1998,
  released: "1998-04-03",
  files: 26,
  aired: 26,
  present: 26,
  missing: 0,
};
const MOVIE: TitleSummary = {
  ...DBZ,
  id: 3,
  kind: "movie",
  name: "Cowboy Bebop: The Movie",
  year: 2001,
  released: "2001-09-01",
  files: 1,
  aired: 0,
  present: 0,
  missing: 0,
};

/** The engine's answers for a library that's empty and already set up. */
function engineWith(answers: Record<string, unknown> = {}) {
  return fakeEngine({
    "/health": health,
    "/settings": SETTINGS,
    "/folders": [],
    "/library": NO_LIBRARY,
    "/scan": NO_SCAN,
    "/tmdb": { connected: false, keyEnd: null },
    "/titles": [],
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
            <Route path="/match" element={<p>Match</p>} />
            <Route path="/titles/:id" element={<p>A title</p>} />
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

  it("leaves out adding a folder while a scan runs", async () => {
    engineWith({
      "/folders": [FOLDER],
      "/library": { ...NO_LIBRARY, folders: 1, files: 3, size: 407_000_000, sd: 3 },
      "/scan": { ...NO_SCAN, state: "running", stage: "reading", found: 3, toRead: 3, read: 1 },
    });
    renderHome(READY);

    expect(
      await screen.findByRole("button", { name: "Scanning… see progress" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add a folder" })).not.toBeInTheDocument();
  });

  it("catches up with the library when the scan finishes", async () => {
    let asked = 0;
    let finished = false;
    engineWith({
      "/folders": [FOLDER],
      "/library": () => ({
        ...NO_LIBRARY,
        folders: 1,
        files: finished ? 3 : 1,
        size: 407_000_000,
        sd: finished ? 3 : 1,
      }),
      "/scan": () => {
        asked += 1;
        finished = asked > 1;
        return finished
          ? { ...NO_SCAN, state: "done", stage: "done", found: 3, toRead: 3, read: 3 }
          : { ...NO_SCAN, state: "running", stage: "reading", found: 3, toRead: 3, read: 1 };
      },
    });
    renderHome(READY);

    expect(await screen.findByText("1 video · 0.4 GB · 1 folder")).toBeInTheDocument();
    // The scan is asked again a second later, finds it done, and the library is asked again.
    expect(
      await screen.findByText("3 videos · 0.4 GB · 1 folder", undefined, { timeout: 3000 }),
    ).toBeInTheDocument();
  });

  it("says when the engine couldn't answer, and asks again", async () => {
    let asked = 0;
    engineWith({
      "/folders": () => {
        asked += 1;
        return asked === 1
          ? Response.json({ detail: "The database is locked." }, { status: 503 })
          : [FOLDER];
      },
      "/library": { ...NO_LIBRARY, folders: 1, files: 3, size: 407_000_000, sd: 3 },
    });
    renderHome(READY);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Kura couldn't load this screen. The database is locked. Nothing in your folders was touched.",
    );
    screen.getByRole("button", { name: "Try again" }).click();

    expect(
      await screen.findByRole("heading", { name: "Your videos by picture" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
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

  it("says whether TMDB is connected, and where to add the key", async () => {
    engineWith();
    renderHome(READY);

    expect(await screen.findByText(/AniList only: no episode titles yet/)).toBeInTheDocument();
    screen.getByRole("button", { name: "Add your TMDB key" }).click();

    expect(await screen.findByText("Setup")).toBeInTheDocument();
  });

  it("names the TMDB key in use", async () => {
    engineWith({ "/tmdb": { connected: true, keyEnd: "ab12" } });
    renderHome(READY);

    expect(await screen.findByText("TMDB connected · key ending ab12")).toBeInTheDocument();
    expect(screen.getByText(/not endorsed or certified by TMDB/)).toBeInTheDocument();
  });

  it("opens the downloads page to show every version and what changed", async () => {
    engineWith();
    renderHome(READY);

    (await screen.findByRole("button", { name: "Every version and what changed" })).click();

    expect(shell.invoke).toHaveBeenCalledWith("open_downloads_page");
  });

  it("lists the anime and films oldest release first, each saying what it is", async () => {
    const fetch = engineWith({
      "/folders": [FOLDER],
      "/library": { ...NO_LIBRARY, folders: 1, files: 314, size: 9e10 },
      "/scan": { ...NO_SCAN, state: "done", stage: "done" },
      "/titles": (init?: RequestInit) => {
        void init;
        return [DBZ, BEBOP, MOVIE];
      },
    });
    renderHome(READY);

    expect(await screen.findByRole("heading", { name: "Anime and films" })).toBeInTheDocument();
    expect(screen.getByText("3 titles · oldest release first")).toBeInTheDocument();
    expect(screen.getByText("TV series · 1989 · 291 episodes")).toBeInTheDocument();
    expect(screen.getByText("Movie · 2001")).toBeInTheDocument();
    expect(screen.getByText("4 missing")).toBeInTheDocument();
    expect(screen.getByText("287 of 291 · 99%")).toBeInTheDocument();
    expect(screen.getByText("3 anime · 314 videos · 90.0 GB · 1 folder")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Release date" })).toBeChecked();
    expect(
      fetch.mock.calls.some(([input]) => String(input).endsWith("/titles?sort=released")),
    ).toBe(true);

    screen.getByRole("radio", { name: "Name" }).click();
    await waitFor(() =>
      expect(fetch.mock.calls.some(([input]) => String(input).endsWith("/titles?sort=name"))).toBe(
        true,
      ),
    );

    (await screen.findByRole("link", { name: /Cowboy Bebop: The Movie/ })).click();
    expect(await screen.findByText("A title")).toBeInTheDocument();
  });

  it("says what needs attention, and leads to it", async () => {
    engineWith({
      "/folders": [FOLDER],
      "/library": { ...NO_LIBRARY, folders: 1, files: 314, problems: 9 },
      "/scan": { ...NO_SCAN, state: "done", stage: "done", waiting: 12, mixed: 1 },
      "/titles": [DBZ, BEBOP],
    });
    renderHome(READY);

    expect(await screen.findByText("12 files need a match")).toBeInTheDocument();
    expect(screen.getByText("4 episodes missing")).toBeInTheDocument();
    expect(screen.getByText("Across 1 anime · gap reports updated")).toBeInTheDocument();
    expect(screen.getByText("9 files won't play")).toBeInTheDocument();
    expect(screen.getByText("1 folder holds mixed anime")).toBeInTheDocument();

    screen.getByRole("button", { name: /12 files need a match/ }).click();
    expect(await screen.findByText("Match")).toBeInTheDocument();
  });
});
