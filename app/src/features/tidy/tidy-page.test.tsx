import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type ProposedChange, type TidyProposal } from "@/lib/engine";
import { fakeEngine, READY } from "@/test/engine";
import { TidyPage } from "./tidy-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const ROOT = "D:\\Anime";

function change(
  source: string,
  target: string,
  label: string,
  more: Partial<ProposedChange> = {},
): ProposedChange {
  return {
    kind: "move",
    source: `${ROOT}\\${source}`,
    target: `${ROOT}\\${target}`,
    root: ROOT,
    label,
    reason: "Named for Plex",
    category: "mixed",
    titleId: 1,
    title: "Cowboy Bebop",
    ...more,
  };
}

const BEBOP_1 = change(
  "Downloads\\[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv",
  "TV\\Cowboy Bebop (1998)\\Season 01\\Cowboy Bebop (1998) - S01E01 - Asteroid Blues.mkv",
  "Cowboy Bebop · S01E01",
);
const DUPLICATE: ProposedChange = {
  ...change("Downloads\\Death Note 07.avi", "", "Death Note · S01E07 · duplicate", {
    kind: "quarantine",
    category: "duplicate",
    titleId: 2,
    title: "Death Note",
    reason: "Kept [DB] Death_Note_07 (720p).mkv instead: higher resolution",
  }),
  target: "D:\\Kura quarantine\\2026-10-11\\Death Note 07.avi",
};
const DEATH_NOTE_7 = change(
  "Downloads\\[DB] Death_Note_07 (720p).mkv",
  "TV\\Death Note (2006)\\Season 01\\Death Note (2006) - S01E07 - Overcast.mkv",
  "Death Note · S01E07",
  { titleId: 2, title: "Death Note" },
);
const TRIGUN_3 = change(
  "Trigun\\trigun_03.mp4",
  "TV\\Trigun (1998)\\Season 01\\Trigun (1998) - S01E03 - Peace Maker.mp4",
  "Trigun · S01E03",
  { titleId: 3, title: "Trigun", category: "rename" },
);

const PROPOSAL: TidyProposal = {
  changes: [DUPLICATE, BEBOP_1, DEATH_NOTE_7, TRIGUN_3],
  skipped: [],
  duplicates: [
    {
      label: "Death Note · S01E07",
      keep: {
        path: DEATH_NOTE_7.source,
        height: 720,
        codec: "h264",
        audio: ["jpn", "eng"],
        subtitles: 1,
        size: 352_000_000,
        plays: true,
      },
      drop: [
        {
          path: DUPLICATE.source,
          height: 480,
          codec: "mpeg4",
          audio: ["jpn"],
          subtitles: 0,
          size: 175_000_000,
          plays: true,
        },
      ],
      reason: "Kept [DB] Death_Note_07 (720p).mkv instead: higher resolution",
    },
  ],
  waiting: 4,
  broken: 9,
};

function sent(fetch: ReturnType<typeof fakeEngine>, method: string, path: string) {
  return fetch.mock.calls.filter(
    ([input, init]) => (init?.method ?? "GET") === method && String(input).includes(path),
  );
}

function renderTidy() {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={["/tidy"]}>
          <Routes>
            <Route path="/tidy" element={<TidyPage />} />
            <Route path="/match" element={<p>Match</p>} />
            <Route path="/history" element={<p>History</p>} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

describe("TidyPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("shows what Kura proposes, a title at a time, and counts it up", async () => {
    fakeEngine({ "/tidy": PROPOSAL });
    renderTidy();

    expect(await screen.findByRole("region", { name: "Cowboy Bebop" })).toBeInTheDocument();
    expect(screen.getByText("[Hi10] Cowboy_Bebop_-_01_(BD_720p).mkv")).toBeInTheDocument();
    expect(
      screen.getByText(
        "TV\\Cowboy Bebop (1998)\\Season 01\\Cowboy Bebop (1998) - S01E01 - Asteroid Blues.mkv",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /2 Mixed folders/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /1 Renames for Plex/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /4 Need a match/ })).toBeInTheDocument();
    expect(
      screen.getByText("4 changes selected. 4 files stay where they are until matched."),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Apply 4 changes" })).toHaveLength(2);
  });

  it("compares two copies, and keeps the other one when asked", async () => {
    const fetch = fakeEngine({ "/tidy": PROPOSAL });
    renderTidy();

    const copies = await screen.findByRole("region", { name: "Copies of Death Note · S01E07" });
    expect(copies).toHaveTextContent("720p · H.264");
    expect(copies).toHaveTextContent("Japanese, English");
    expect(copies).toHaveTextContent("480p · MPEG-4");
    screen.getByRole("button", { name: "Swap which one is kept" }).click();

    await waitFor(() =>
      expect(
        fetch.mock.calls.some(([input]) =>
          String(input).includes(`keep=${encodeURIComponent(DUPLICATE.source)}`),
        ),
      ).toBe(true),
    );
  });

  it("applies the titles left in, then offers to undo", async () => {
    const fetch = fakeEngine({
      "/tidy": PROPOSAL,
      "POST /tidy": { planId: 13, moved: 2, quarantined: 1, problems: [] },
      "POST /plans/13/undo": { planId: 13, moved: 2, quarantined: 1, problems: [] },
    });
    renderTidy();

    (await screen.findByRole("checkbox", { name: /Trigun/ })).click();
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "Apply 3 changes" })).toHaveLength(2),
    );
    screen.getAllByRole("button", { name: "Apply 3 changes" })[0]?.click();

    expect(
      await screen.findByText("Done: 2 files filed for Plex, 1 copy set aside."),
    ).toBeInTheDocument();
    const [[, init]] = sent(fetch, "POST", "/tidy") as [[unknown, RequestInit]];
    expect(JSON.parse(String(init.body))).toEqual({
      sources: [DUPLICATE.source, BEBOP_1.source, DEATH_NOTE_7.source],
      keep: [],
    });

    screen.getByRole("button", { name: "Undo" }).click();
    await waitFor(() => expect(sent(fetch, "POST", "/plans/13/undo")).toHaveLength(1));
  });

  it("says when everything is filed", async () => {
    fakeEngine({ "/tidy": { ...PROPOSAL, changes: [], duplicates: [], waiting: 0 } });
    renderTidy();

    expect(await screen.findByRole("heading", { name: "Everything is filed" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Apply/ })).not.toBeInTheDocument();
  });

  it("leads to the files that need a match", async () => {
    fakeEngine({ "/tidy": PROPOSAL });
    renderTidy();

    (await screen.findByRole("button", { name: /4 Need a match/ })).click();

    expect(await screen.findByText("Match")).toBeInTheDocument();
  });
});
