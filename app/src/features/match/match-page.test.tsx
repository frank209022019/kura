import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useParams } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type Guess, type WaitingFile } from "@/lib/engine";
import { fakeEngine, READY } from "@/test/engine";
import { MatchPage } from "./match-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const TRIGUN: Guess = {
  anilistId: 6,
  title: "Trigun",
  kind: "series",
  year: 1998,
  episodes: 26,
  minutes: 24,
  cover: null,
  confidence: 41,
  reasons: ["The 6 Trigun files in this folder share the [subs] tag"],
};
const BEBOP: Guess = {
  ...TRIGUN,
  anilistId: 1,
  title: "Cowboy Bebop",
  confidence: 38,
  reasons: [],
};

function waiting(id: number, episode: number, alike: number[] = []): WaitingFile {
  return {
    id,
    path: `D:\\Anime\\Downloads\\[subs] ep0${episode} final.mkv`,
    size: 233_000_000,
    minutes: 24.17,
    height: 480,
    codec: "h264",
    audio: ["jpn", "eng"],
    subtitles: ["eng"],
    group: "subs",
    title: null,
    season: null,
    episode,
    kind: "episode",
    guesses: [TRIGUN, BEBOP],
    alike,
  };
}

const QUEUE = [waiting(3, 3, [4, 5]), waiting(4, 4, [3, 5]), waiting(5, 5, [3, 4])];

function sent(fetch: ReturnType<typeof fakeEngine>, method: string, path: string) {
  return fetch.mock.calls.filter(
    ([input, init]) => (init?.method ?? "GET") === method && String(input).includes(path),
  );
}

function renderMatch(at = "/match") {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[at]}>
          <Routes>
            <Route path="/match" element={<MatchPage />} />
            <Route path="/titles/:id" element={<ShownTitle />} />
            <Route path="*" element={<p>Home</p>} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

function ShownTitle() {
  const waiting = (useLocation().state as { waiting?: number } | null)?.waiting;
  return (
    <p>
      Title {useParams().id}
      {waiting !== undefined && `, ${waiting} waiting`}
    </p>
  );
}

describe("MatchPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("shows the file, what reading it showed, and Kura's best guesses", async () => {
    fakeEngine({ "/review": QUEUE });
    renderMatch();

    expect(
      await screen.findByRole("heading", { name: "[subs] ep03 final.mkv" }),
    ).toBeInTheDocument();
    expect(screen.getByText("File 1 of 3")).toBeInTheDocument();
    expect(screen.getByText("24:10")).toBeInTheDocument();
    expect(screen.getByText("480p · H.264")).toBeInTheDocument();
    expect(screen.getByText("Japanese, English")).toBeInTheDocument();
    expect(screen.getByText("[subs]")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Trigun \(1998\)/ })).toBeChecked();
    expect(screen.getByText("41%")).toBeInTheDocument();
    expect(screen.getByText("Use this for the 2 other [subs] files here")).toBeInTheDocument();
    expect(screen.getByText("Episodes 04 and 05, numbered from their names")).toBeInTheDocument();
  });

  it("confirms the choice for the file and the ones like it", async () => {
    const fetch = fakeEngine({ "/review": QUEUE, "POST /review/3": { placed: 3 } });
    renderMatch();

    (await screen.findByRole("button", { name: "Confirm Trigun, episode 3" })).click();

    await waitFor(() => expect(sent(fetch, "POST", "/review/3")).toHaveLength(1));
    const [[, init]] = sent(fetch, "POST", "/review/3") as [[unknown, RequestInit]];
    expect(JSON.parse(String(init.body))).toEqual({ anilistId: 6, kind: "episode", also: [4, 5] });
  });

  it("picks another guess with its number key, and the kind with the switch", async () => {
    const fetch = fakeEngine({ "/review": QUEUE, "POST /review/3": { placed: 1 } });
    renderMatch();
    await screen.findByRole("radio", { name: /Trigun/ });

    fireEvent.keyDown(window, { key: "2" });
    await waitFor(() => expect(screen.getByRole("radio", { name: /Cowboy Bebop/ })).toBeChecked());
    screen.getByRole("radio", { name: "Special or extra" }).click();
    screen.getByRole("checkbox").click();
    (await screen.findByRole("button", { name: "Confirm Cowboy Bebop" })).click();

    await waitFor(() => expect(sent(fetch, "POST", "/review/3")).toHaveLength(1));
    const [[, init]] = sent(fetch, "POST", "/review/3") as [[unknown, RequestInit]];
    expect(JSON.parse(String(init.body))).toEqual({ anilistId: 1, kind: "special", also: [] });
  });

  it("asks which episode a file is when its name doesn't say", async () => {
    const dvd: WaitingFile = {
      ...waiting(7, 1),
      path: "D:\\Anime\\Old DVDs\\VTS_01_1.VOB",
      episode: null,
      kind: "dvd",
    };
    const fetch = fakeEngine({ "/review": [dvd], "POST /review/7": { placed: 1 } });
    renderMatch();

    const number = await screen.findByRole("textbox", { name: "Which episode" });
    expect(screen.getByRole("button", { name: "Confirm Trigun" })).toBeInTheDocument();
    fireEvent.change(number, { target: { value: "15x0" } });
    (await screen.findByRole("button", { name: "Confirm Trigun, episode 150" })).click();

    await waitFor(() => expect(sent(fetch, "POST", "/review/7")).toHaveLength(1));
    const [[, init]] = sent(fetch, "POST", "/review/7") as [[unknown, RequestInit]];
    expect(JSON.parse(String(init.body))).toEqual({
      anilistId: 6,
      kind: "episode",
      also: [],
      episode: 150,
    });
  });

  it("searches when none of the guesses is right", async () => {
    fakeEngine({
      "/review": QUEUE,
      "/review/3/search": [{ ...TRIGUN, anilistId: 99, title: "Trigun Stampede", confidence: 70 }],
    });
    renderMatch();

    fireEvent.change(await screen.findByRole("searchbox", { name: "Search for the right anime" }), {
      target: { value: "Trigun Stampede" },
    });

    expect(await screen.findByRole("radio", { name: /Trigun Stampede/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Found" })).toBeInTheDocument();
  });

  it("skips to the next file, and leaves out what isn't anime", async () => {
    const fetch = fakeEngine({ "/review": QUEUE, "POST /review/4/ignore": null });
    renderMatch();

    (await screen.findByRole("button", { name: "Skip for now" })).click();
    expect(
      await screen.findByRole("heading", { name: "[subs] ep04 final.mkv" }),
    ).toBeInTheDocument();
    screen.getByRole("button", { name: "Not anime, ignore it" }).click();

    await waitFor(() => expect(sent(fetch, "POST", "/review/4/ignore")).toHaveLength(1));
  });

  it("keeps going round the files that were skipped", async () => {
    fakeEngine({ "/review": QUEUE });
    renderMatch();

    for (const shown of ["ep03", "ep04", "ep05", "ep03", "ep04"]) {
      expect(
        await screen.findByRole("heading", { name: `[subs] ${shown} final.mkv` }),
      ).toBeInTheDocument();
      screen.getByRole("button", { name: "Skip for now" }).click();
    }
  });

  it("searches once the owner stops typing", async () => {
    const fetch = fakeEngine({
      "/review": QUEUE,
      "/review/3/search": [{ ...TRIGUN, anilistId: 99, title: "Trigun Stampede", confidence: 70 }],
    });
    renderMatch();
    const box = await screen.findByRole("searchbox", { name: "Search for the right anime" });

    for (const typed of ["Tr", "Tri", "Trig", "Trigu", "Trigun"]) {
      fireEvent.change(box, { target: { value: typed } });
    }

    expect(await screen.findByRole("radio", { name: /Trigun Stampede/ })).toBeInTheDocument();
    expect(sent(fetch, "GET", "/review/3/search")).toHaveLength(1);
  });

  it("changes a title's match for all its files, then shows where they went", async () => {
    const fetch = fakeEngine({
      "/review": [{ ...waiting(3, 1, [4, 5]), guesses: [BEBOP, TRIGUN] }],
      "/titles/1": { name: "Cowboy Bebop" },
      "POST /review/3": { placed: 2, waiting: 1, titleId: 8 },
    });
    renderMatch("/match?title=1");

    expect(await screen.findByText("All 3 files of Cowboy Bebop")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cowboy Bebop" })).toHaveAttribute("href", "/titles/1");
    expect(screen.getByText("Use this for its other 2 files")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Skip for now" })).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([input]) => String(input).endsWith("/review?title=1"))).toBe(
      true,
    );
    fireEvent.keyDown(window, { key: "2" });
    (await screen.findByRole("button", { name: "Confirm Trigun, episode 1" })).click();

    expect(await screen.findByText("Title 8, 1 waiting")).toBeInTheDocument();
    const [[, init]] = sent(fetch, "POST", "/review/3") as [[unknown, RequestInit]];
    expect(JSON.parse(String(init.body))).toEqual({
      anilistId: TRIGUN.anilistId,
      kind: "episode",
      title: 1,
    });
  });

  it("says when every file is matched", async () => {
    fakeEngine({ "/review": [] });
    renderMatch();

    expect(
      await screen.findByRole("heading", { name: "Every file is matched" }),
    ).toBeInTheDocument();
    screen.getByRole("button", { name: "Go to Home" }).click();
    expect(await screen.findByText("Home")).toBeInTheDocument();
  });
});
