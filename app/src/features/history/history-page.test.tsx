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
  kind: "tidy",
  title: "Tidied 30 files: Cowboy Bebop, Death Note and 2 more",
  appliedAt: today(11, 40),
  undoneAt: null,
  moved: 29,
  quarantined: 1,
  failed: 0,
  undone: 0,
  deleted: false,
  conversion: null,
};
const CONVERTED: PlanDone = {
  ...TIDIED,
  id: 14,
  kind: "convert",
  title: "Converted Trigun · S01E03",
  appliedAt: today(14, 20),
  moved: 1,
  quarantined: 1,
  conversion: {
    jobId: 5,
    method: "best",
    before: { height: 480, codec: "h264", size: 233_000_000 },
    after: { height: 1080, codec: "hevc", size: 412_000_000 },
    seconds: 3480,
    restored: false,
  },
};
const RENAMED: PlanDone = {
  ...TIDIED,
  id: 12,
  title: "Renamed 287 Dragon Ball Z files",
  appliedAt: today(10, 58),
  moved: 287,
  quarantined: 0,
};
const UNDONE: PlanDone = {
  ...TIDIED,
  id: 9,
  title: "Renamed 3 Sailor Moon files",
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
      added: 2,
      gone: 1,
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
    expect(todayList).toHaveTextContent("10:58RenamedRenamed 287 Dragon Ball Z files");
    expect(todayList).toHaveTextContent(
      "10:51ScannedYour library foldersEvery folder looked at · 2 new, 1 gone",
    );
    expect(screen.getByRole("region", { name: "8 October" })).toHaveTextContent(
      "UndoneRenamed 3 Sailor Moon filesYou put 3 files back",
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

  it("says what was deleted, and puts it back", async () => {
    const deleted: PlanDone = {
      ...TIDIED,
      id: 15,
      title: "Deleted 2 Trigun files",
      moved: 0,
      quarantined: 2,
      deleted: true,
    };
    const fetch = fakeEngine({
      "/history": { plans: [deleted], scans: [] },
      "POST /plans/15/undo": { planId: 15, moved: 0, quarantined: 2, problems: [] },
    });
    renderHistory();

    const todayList = await screen.findByRole("region", { name: "Today" });
    expect(todayList).toHaveTextContent(
      "11:40Deleted2 Trigun files2 videos in quarantine · plan 15",
    );
    screen.getByRole("button", { name: "Put back what was deleted" }).click();

    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([input, init]) => init?.method === "POST" && String(input).endsWith("/plans/15/undo"),
        ),
      ).toBe(true),
    );
  });

  it("keeps Undo for a tidy-up not all put back", async () => {
    const partly: PlanDone = { ...TIDIED, moved: 1, quarantined: 0, undone: 29 };
    fakeEngine({ "/history": { plans: [partly], scans: [] } });
    renderHistory();

    const todayList = await screen.findByRole("region", { name: "Today" });
    expect(todayList).toHaveTextContent("1 file moved · 29 put back · plan 13");
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
  });

  it("lists each conversion with what it made, and puts an original back", async () => {
    const fetch = fakeEngine({
      "/history": { plans: [CONVERTED, TIDIED], scans: [] },
      "POST /plans/14/undo": { planId: 14, moved: 1, quarantined: 0, problems: [] },
    });
    renderHistory();

    const todayList = await screen.findByRole("region", { name: "Today" });
    expect(todayList).toHaveTextContent(
      "14:20ConvertedTrigun · S01E03480p H.264 233 MB → 1080p HEVC 412 MB · 58 min · checked",
    );
    screen.getByRole("button", { name: "Put back the original" }).click();
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([input, init]) => init?.method === "POST" && String(input).endsWith("/plans/14/undo"),
        ),
      ).toBe(true),
    );

    screen.getByRole("radio", { name: "Conversions" }).click();
    await waitFor(() => expect(screen.queryByText(/Tidied 30 files/)).not.toBeInTheDocument());
    expect(screen.getByText("Trigun · S01E03")).toBeInTheDocument();
  });

  it("says when a converted file's original is gone, and offers nothing to put back", async () => {
    const gone: PlanDone = { ...CONVERTED, quarantined: 0 }; // deleted, or cleared out
    fakeEngine({ "/history": { plans: [gone], scans: [] } });
    renderHistory();

    const todayList = await screen.findByRole("region", { name: "Today" });
    expect(todayList).toHaveTextContent(
      "Trigun · S01E03480p H.264 233 MB → 1080p HEVC 412 MB · 58 min · checked · original deleted",
    );
    expect(screen.queryByRole("button", { name: "Put back the original" })).not.toBeInTheDocument();
  });

  it("says when a converted file's original came back", async () => {
    const back: PlanDone = {
      ...CONVERTED,
      undoneAt: today(15, 0),
      conversion: CONVERTED.conversion && { ...CONVERTED.conversion, restored: true },
    };
    fakeEngine({ "/history": { plans: [back], scans: [] } });
    renderHistory();

    const todayList = await screen.findByRole("region", { name: "Today" });
    expect(todayList).toHaveTextContent(
      "15:00Put backTrigun · S01E03The original is in its place again",
    );
    expect(screen.queryByRole("button", { name: "Put back the original" })).not.toBeInTheDocument();
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
