import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type History, type PlanDone } from "@/lib/engine";
import { fakeEngine, READY } from "@/test/engine";
import { HistoryPage } from "./history-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function today(hour: number, minute: number): string {
  const moment = new Date();
  moment.setHours(hour, minute, 0, 0);
  return moment.toISOString();
}

const TIDIED: PlanDone = {
  id: 13,
  title: "Tidied 30 files: Cowboy Bebop, Death Note and 2 more",
  appliedAt: today(11, 40),
  undoneAt: null,
  moved: 29,
  quarantined: 1,
  failed: 0,
  undone: 0,
};
const RENAMED: PlanDone = {
  ...TIDIED,
  id: 12,
  title: "Renamed 287 Dragon Ball Z files for Plex",
  appliedAt: today(10, 58),
  moved: 287,
  quarantined: 0,
};
const UNDONE: PlanDone = {
  ...TIDIED,
  id: 9,
  title: "Renamed 3 Sailor Moon files for Plex",
  appliedAt: "2026-10-08T18:30:00+00:00",
  undoneAt: "2026-10-08T19:02:00+00:00",
  moved: 0,
  quarantined: 0,
  undone: 3,
};
const HISTORY: History = {
  plans: [TIDIED, RENAMED, UNDONE],
  scans: [
    {
      id: 4,
      startedAt: today(10, 51),
      finishedAt: today(10, 53),
      state: "done",
      problem: null,
      note: null,
    },
  ],
};

function renderHistory() {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter>
          <HistoryPage />
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

describe("HistoryPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("lists what Kura did by day, newest first", async () => {
    fakeEngine({ "/history": HISTORY });
    renderHistory();

    const todayList = await screen.findByRole("region", { name: "Today" });
    expect(todayList).toHaveTextContent(
      "11:40MovedTidied 30 files: Cowboy Bebop, Death Note and 2 more29 files moved · 1 copy set aside · plan 13",
    );
    expect(todayList).toHaveTextContent("10:58RenamedRenamed 287 Dragon Ball Z files for Plex");
    expect(todayList).toHaveTextContent("10:51ScannedYour library folders");
    expect(screen.getByRole("region", { name: "8 October" })).toHaveTextContent(
      "UndoneRenamed 3 Sailor Moon files for PlexYou put 3 files back",
    );
    expect(screen.getAllByRole("button", { name: "Undo" })).toHaveLength(2);
  });

  it("undoes a tidy-up", async () => {
    const fetch = fakeEngine({
      "/history": HISTORY,
      "POST /plans/13/undo": { planId: 13, moved: 29, quarantined: 1, problems: [] },
    });
    renderHistory();

    (await screen.findAllByRole("button", { name: "Undo" }))[0]?.click();

    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([input, init]) => init?.method === "POST" && String(input).endsWith("/plans/13/undo"),
        ),
      ).toBe(true),
    );
  });

  it("shows only scans, or only renames and moves", async () => {
    fakeEngine({ "/history": HISTORY });
    renderHistory();

    (await screen.findByRole("radio", { name: "Scans" })).click();

    await waitFor(() => expect(screen.queryByText(/Tidied 30 files/)).not.toBeInTheDocument());
    expect(screen.getByText("Your library folders")).toBeInTheDocument();
  });

  it("says when there's nothing yet", async () => {
    fakeEngine({ "/history": { plans: [], scans: [] } });
    renderHistory();

    expect(await screen.findByRole("heading", { name: "Nothing yet" })).toBeInTheDocument();
  });
});
