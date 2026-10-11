import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type Backup, type DataSizes, EngineProvider, type LibraryFolder } from "@/lib/engine";
import { fakeEngine, READY, SETTINGS } from "@/test/engine";
import { SettingsPage } from "./settings-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const FOLDERS: LibraryFolder[] = [
  {
    id: 1,
    path: "D:\\Anime",
    addedAt: "2026-10-10T10:00:00+02:00",
    available: true,
    files: 2941,
    unread: 0,
    problems: 9,
  },
  {
    id: 2,
    path: "F:\\More anime",
    addedAt: "2026-10-10T10:00:00+02:00",
    available: false,
    files: 12,
    unread: 0,
    problems: 0,
  },
];

const DATA: DataSizes = {
  folder: "C:\\Users\\Someone\\AppData\\Local\\Kura",
  database: 48_000_000,
  artwork: 610_000_000,
  cache: 20_000_000,
  logs: 12_000_000,
  backups: 0,
  tools: 180_000_000,
  quarantine: [{ folder: "D:\\Kura quarantine", bytes: 3_400_000_000, files: 14 }],
  moved: null,
};

/** A local time `daysAgo` days back, as the engine writes a backup's: "2026-10-11T03:00". */
function stamp(daysAgo: number, time: string): string {
  const day = new Date();
  day.setDate(day.getDate() - daysAgo);
  const date = [day.getFullYear(), day.getMonth() + 1, day.getDate()]
    .map((part) => String(part).padStart(2, "0"))
    .join("-");
  return `${date}T${time}`;
}

function backup(made: string): Backup {
  const [date, time] = made.split("T");
  const name = `kura ${date} ${time?.replace(":", "")}.db`;
  return { name, made, size: 47_000_000, beforeRestoring: false };
}

const TONIGHT = backup(stamp(0, "03:00"));
const LAST_NIGHT = backup(stamp(1, "03:00"));

function renderSettings(section = "libraries") {
  shell.invoke.mockImplementation(async (command: string, args?: { on?: boolean }) => {
    if (command === "engine_status") return READY;
    if (command === "pick_folder") return "D:\\Backups";
    if (command === "start_with_windows") return false;
    if (command === "set_start_with_windows") return args?.on;
    return undefined;
  });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[`/settings/${section}`]}>
          <Routes>
            <Route path="/settings/:section" element={<SettingsPage />} />
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

function body(fetch: ReturnType<typeof fakeEngine>, method: string, path: string): unknown {
  const [[, init]] = sent(fetch, method, path) as [[unknown, RequestInit]];
  return JSON.parse(String(init.body));
}

describe("SettingsPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("lists the library's folders, and forgets one", async () => {
    const fetch = fakeEngine({ "/folders": FOLDERS, "DELETE /folders/2": null });
    renderSettings();

    expect(await screen.findByText("2941 videos")).toBeInTheDocument();
    expect(
      screen.getByText("Not connected: its files wait till the drive is back"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Libraries\s*2/ })).toBeInTheDocument();
    screen.getAllByRole("button", { name: "Forget" })[1]?.click();

    await waitFor(() => expect(sent(fetch, "DELETE", "/folders/2")).toHaveLength(1));
  });

  it("changes the standard at once", async () => {
    const fetch = fakeEngine({
      "/folders": FOLDERS,
      "/settings": SETTINGS,
      "PUT /settings": SETTINGS,
    });
    renderSettings("standard");

    (await screen.findByRole("radio", { name: /Compact 720p/ })).click();

    await waitFor(() => expect(sent(fetch, "PUT", "/settings")).toHaveLength(1));
    expect(body(fetch, "PUT", "/settings")).toMatchObject({ standard: "compact-720" });
  });

  it("shows where the data lives and how big each part is", async () => {
    fakeEngine({ "/folders": FOLDERS, "/settings": SETTINGS, "/data": DATA });
    renderSettings("data");

    expect(await screen.findByText(DATA.folder)).toBeInTheDocument();
    expect(screen.getByText("610 MB")).toBeInTheDocument();
    expect(
      screen.getByText(
        "3.4 GB in 14 files: copies set aside and converted files' originals, each on its own drive.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "30 days" })).toHaveAttribute("aria-checked", "true");
  });

  it("turns the reports off, and keeps what's set aside longer", async () => {
    const fetch = fakeEngine({
      "/folders": FOLDERS,
      "/settings": SETTINGS,
      "/data": DATA,
      "PUT /settings": SETTINGS,
    });
    renderSettings("data");

    (await screen.findByRole("switch", { name: "A gap report in each anime's folder" })).click();
    await waitFor(() => expect(sent(fetch, "PUT", "/settings")).toHaveLength(1));
    expect(body(fetch, "PUT", "/settings")).toMatchObject({ reports: false });
  });

  it("exports everything to a folder the owner picks", async () => {
    const fetch = fakeEngine({
      "/folders": FOLDERS,
      "/settings": SETTINGS,
      "/data": DATA,
      "POST /export": { path: "D:\\Backups\\Kura export 2026-10-11.zip", size: 912_000_000 },
    });
    renderSettings("data");

    (await screen.findByRole("button", { name: "Export everything" })).click();

    expect(
      await screen.findByText("D:\\Backups\\Kura export 2026-10-11.zip · 912 MB"),
    ).toBeInTheDocument();
    expect(body(fetch, "POST", "/export")).toEqual({ folder: "D:\\Backups" });
  });

  it("shows last night's backup, and makes one now", async () => {
    const fetch = fakeEngine({
      "/folders": FOLDERS,
      "/settings": SETTINGS,
      "/data": DATA,
      "/backups": { backups: [TONIGHT, LAST_NIGHT], restored: null },
      "POST /backups": backup(stamp(0, "14:12")),
    });
    renderSettings("data");

    expect(await screen.findByText("Last backup today 03:00")).toBeInTheDocument();
    expect(screen.getByText("47 MB · checked")).toBeInTheDocument();
    screen.getByRole("button", { name: "Back up now" }).click();

    await waitFor(() => expect(sent(fetch, "POST", "/backups")).toHaveLength(1));
  });

  it("restores the backup the owner picks, as the engine starts again", async () => {
    const restore = `/backups/${encodeURIComponent(LAST_NIGHT.name)}/restore`;
    const fetch = fakeEngine({
      "/folders": FOLDERS,
      "/settings": SETTINGS,
      "/data": DATA,
      "/backups": { backups: [TONIGHT, LAST_NIGHT], restored: null },
      [`POST ${restore}`]: null,
    });
    renderSettings("data");

    await screen.findByText("Last backup today 03:00");
    screen.getByRole("button", { name: "Restore a backup" }).click();
    (await screen.findByRole("radio", { name: /Yesterday 03:00/ })).click();
    const go = screen.getByRole("button", { name: "Restore it" });
    await waitFor(() => expect(go).toBeEnabled());
    go.click();

    await waitFor(() => expect(sent(fetch, "POST", restore)).toHaveLength(1));
    await waitFor(() => expect(shell.invoke).toHaveBeenCalledWith("restart_engine"));
  });

  it("says how today's restore went", async () => {
    fakeEngine({
      "/folders": FOLDERS,
      "/settings": SETTINGS,
      "/data": DATA,
      "/backups": {
        backups: [TONIGHT, LAST_NIGHT],
        restored: { name: LAST_NIGHT.name, at: new Date().toISOString(), problem: null },
      },
    });
    renderSettings("data");

    expect(
      await screen.findByText("Restored the backup from yesterday 03:00."),
    ).toBeInTheDocument();
  });

  it("starts Kura with Windows, waiting in the tray, when asked", async () => {
    fakeEngine({ "/folders": FOLDERS });
    renderSettings("general");

    const start = await screen.findByRole("switch", { name: "Start Kura when Windows starts" });
    await waitFor(() => expect(start).toHaveAttribute("aria-checked", "false"));
    start.click();

    await waitFor(() =>
      expect(shell.invoke).toHaveBeenCalledWith("set_start_with_windows", { on: true }),
    );
    await waitFor(() => expect(start).toHaveAttribute("aria-checked", "true"));
  });

  it("moves the data to another drive, as the engine starts again", async () => {
    const fetch = fakeEngine({
      "/folders": FOLDERS,
      "/settings": SETTINGS,
      "/data": DATA,
      "/backups": { backups: [], restored: null },
      "POST /data/move": null,
    });
    renderSettings("data");

    (await screen.findByRole("button", { name: "Move to another drive" })).click();
    const asking = await screen.findByRole("group", {
      name: "Move Kura's data to D:\\Backups\\Kura?",
    });
    within(asking).getByRole("button", { name: "Move it" }).click();

    await waitFor(() => expect(shell.invoke).toHaveBeenCalledWith("restart_engine"));
    expect(body(fetch, "POST", "/data/move")).toEqual({ folder: "D:\\Backups\\Kura" });
  });

  it("takes an unknown section to the first", async () => {
    fakeEngine({ "/folders": FOLDERS });
    renderSettings("nowhere");

    expect(
      await screen.findByRole("switch", { name: "Start Kura when Windows starts" }),
    ).toBeInTheDocument();
  });
});
