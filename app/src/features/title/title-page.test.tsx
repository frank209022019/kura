import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type EpisodeState, type TitleDetail } from "@/lib/engine";
import { fakeEngine, READY } from "@/test/engine";
import { TitlePage } from "./title-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

function episodes(season: number, size: number, state: (n: number) => EpisodeState["state"]) {
  return Array.from({ length: size }, (_, index) => ({
    season,
    number: index + 1,
    name: index === 10 && season === 4 ? "The Ginyu Force" : `Episode ${index + 1}`,
    aired: "1991-01-01",
    state: state(index + 1),
    fileId: null,
  }));
}

const DBZ: TitleDetail = {
  id: 1,
  kind: "series",
  name: "Dragon Ball Z",
  year: 1989,
  released: "1989-04-26",
  airing: false,
  hasPoster: false,
  files: 70,
  added: null,
  aired: 72,
  present: 70,
  missing: 2,
  specialsMissing: 1,
  upcoming: 0,
  franchise: null,
  source: "tmdb",
  folder: "D:\\Anime\\TV\\Dragon Ball Z (1989)",
  seasons: [
    { season: 1, present: 39, aired: 39, total: 39 },
    { season: 4, present: 30, aired: 32, total: 32 },
  ],
  missingEpisodes: [],
  missingSpecials: [],
  upcomingEpisodes: [],
  episodes: [
    ...episodes(1, 39, () => "to convert"),
    ...episodes(4, 32, (n) => (n === 11 || n === 12 ? "missing" : n === 5 ? "broken" : "ready")),
    { season: 0, number: 1, name: "Bardock", aired: "1990-10-17", state: "ready", fileId: 9 },
    {
      season: 0,
      number: 2,
      name: "Plan to Eradicate",
      aired: "1993-08-06",
      state: "missing",
      fileId: null,
    },
  ],
  videos: [
    {
      id: 1,
      path: "D:\\Anime\\TV\\Dragon Ball Z (1989)\\Season 01\\Dragon Ball Z - S01E01.mkv",
      season: 1,
      episode: 1,
      episodeEnd: null,
      problem: null,
      height: 480,
      codec: "h264",
      duration: 1440,
    },
  ],
};

function renderTitle(title: TitleDetail, report: unknown = undefined, state: unknown = null) {
  fakeEngine({ [`/titles/${title.id}`]: title, [`/titles/${title.id}/report`]: report });
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[{ pathname: `/titles/${title.id}`, state }]}>
          <Routes>
            <Route path="/titles/:id" element={<TitlePage />} />
            <Route path="/match" element={<MatchSearch />} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

function MatchSearch() {
  return <p>Match {useLocation().search}</p>;
}

describe("TitlePage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("says what the title is and how much of it is there", async () => {
    renderTitle(DBZ);

    expect(
      await screen.findByRole("heading", { name: "Dragon Ball Z", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText("TV series")).toBeInTheDocument();
    expect(screen.getByText("Matched on TMDB and AniList")).toBeInTheDocument();
    expect(screen.getByText("1989 · 2 seasons · 72 episodes")).toBeInTheDocument();
    expect(screen.getByText("97%")).toBeInTheDocument();
    expect(screen.getByText("70 of 72 episodes")).toBeInTheDocument();
  });

  it("says when files didn't fit its new match, and leads to them", async () => {
    renderTitle(DBZ, undefined, { waiting: 2 });

    expect(
      await screen.findByText("2 files didn't fit this match. They wait for you in Need a match."),
    ).toBeInTheDocument();
    screen.getByRole("button", { name: "Match them" }).click();

    expect(await screen.findByText("Match")).toBeInTheDocument();
  });

  it("says why Explorer couldn't open its folder", async () => {
    renderTitle(DBZ);
    const gone = `Windows can't open ${DBZ.folder}: it isn't a folder that's there.`;
    shell.invoke.mockImplementation(async (command: string) => {
      if (command === "engine_status") return READY;
      if (command === "open_folder") throw gone;
      return undefined;
    });

    (await screen.findByRole("button", { name: "Open folder" })).click();

    expect(await screen.findByRole("alert")).toHaveTextContent(gone);
  });

  it("says which franchise it's part of, and leads back to it", async () => {
    renderTitle({ ...DBZ, franchise: { id: 7, name: "Dragon Ball" } });

    expect(
      await screen.findByText("1989 · 2 seasons · 72 episodes · part of Dragon Ball"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dragon Ball" })).toHaveAttribute(
      "href",
      "/franchises/7",
    );
  });

  it("opens its folder, and leads to changing its match", async () => {
    renderTitle(DBZ);

    (await screen.findByRole("button", { name: "Open folder" })).click();
    await waitFor(() =>
      expect(shell.invoke).toHaveBeenCalledWith("open_folder", { path: DBZ.folder }),
    );
    screen.getByRole("button", { name: "Change match" }).click();

    expect(await screen.findByText("Match ?title=1")).toBeInTheDocument();
  });

  it("shows its gap analysis in its folder, or copies it", async () => {
    const copied = vi.fn<(text: string) => Promise<void>>(async () => {});
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText: copied } });
    const report = { path: `${DBZ.folder}\\Kura - Gap analysis.md`, text: "# Dragon Ball Z" };
    renderTitle(DBZ, report);

    (await screen.findByRole("button", { name: "Show in folder" })).click();
    await waitFor(() =>
      expect(shell.invoke).toHaveBeenCalledWith("show_in_folder", { path: report.path }),
    );
    screen.getByRole("button", { name: "Copy" }).click();

    await waitFor(() => expect(copied).toHaveBeenCalledWith("# Dragon Ball Z"));
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("lists the seasons, the map, and the missing and broken episodes", async () => {
    renderTitle(DBZ);

    expect(await screen.findByText("2 missing")).toBeInTheDocument();
    expect(screen.getByText("complete")).toBeInTheDocument();
    expect(
      screen.getByRole("img", {
        name: "Episode map: 39 to convert, 29 ready, 1 broken, 2 missing",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Episode 51 · missing/)).toBeInTheDocument();
    expect(screen.getByText(/Episode 50 · The Ginyu Force · missing/)).toBeInTheDocument();
    expect(screen.getByText(/Episode 44 · won't play/)).toBeInTheDocument();
  });

  it("reads a long run of missing episodes as one range", async () => {
    renderTitle({
      ...DBZ,
      name: "Dragon Ball",
      year: 1986,
      aired: 153,
      present: 4,
      missing: 149,
      source: "anilist",
      seasons: [{ season: 1, present: 4, aired: 153, total: 153 }],
      episodes: episodes(1, 153, (n) => (n <= 3 || n === 6 ? "to convert" : "missing")),
    });

    expect(await screen.findByText("S01E07–E153")).toBeInTheDocument();
    expect(screen.getByText(/Episodes 7 to 153 · 147 missing/)).toBeInTheDocument();
    expect(screen.getByText(/Episode 4 · missing/)).toBeInTheDocument();
    expect(screen.getByText(/Episode 5 · missing/)).toBeInTheDocument();
    expect(screen.queryByText(/Episode 100 · missing/)).not.toBeInTheDocument();
    expect(screen.getByText("3%")).toBeInTheDocument();
  });

  it("keeps the specials and OVAs apart", async () => {
    renderTitle(DBZ);

    expect(await screen.findByRole("heading", { name: "Specials and OVAs" })).toBeInTheDocument();
    expect(screen.getByText("1 not in the library · never counted as missing")).toBeInTheDocument();
    expect(screen.getByText(/Plan to Eradicate/)).toBeInTheDocument();
  });

  it("shows the gap analysis as a reader sees it, not its Markdown", async () => {
    renderTitle(DBZ, {
      path: "D:\\Anime\\TV\\Dragon Ball Z (1989)\\Kura - Gap analysis.md",
      text: [
        "# Dragon Ball Z (1989) — gap analysis",
        "_Updated 10 Oct 2026, 14:20 · library D:\\Anime_",
        "",
        "## Summary",
        "- Present: **289 of 291** episodes (99%)",
        "",
        "## Missing",
        "| Episode | Absolute | Folder |",
        "| --- | --- | --- |",
        "| S01E51 | 51 | Season 01 |",
        "",
      ].join("\n"),
    });

    const report = await screen.findByRole("region", { name: "Gap Analysis" });
    expect(
      await within(report).findByRole("heading", { name: "Dragon Ball Z (1989) — gap analysis" }),
    ).toBeInTheDocument();
    expect(within(report).getByRole("heading", { name: "Missing" })).toBeInTheDocument();
    expect(within(report).getByRole("cell", { name: "S01E51" })).toBeInTheDocument();
    expect(within(report).getByText("289 of 291").tagName).toBe("STRONG");
    expect(report).not.toHaveTextContent("##");
    expect(report).not.toHaveTextContent("Plex");
  });

  it("a film shows its file, without seasons", async () => {
    renderTitle({
      ...DBZ,
      id: 3,
      kind: "movie",
      name: "Cowboy Bebop: The Movie",
      year: 2001,
      files: 1,
      aired: 0,
      present: 0,
      missing: 0,
      seasons: [],
      episodes: [],
    });

    expect(await screen.findByText("Movie")).toBeInTheDocument();
    expect(screen.getByText("2001 · 1 file")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Seasons" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Its file" })).toBeInTheDocument();
  });
});
