import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ShelfCard } from "@/components/title-card";
import { EngineProvider, type FranchiseSummary, type TitleSummary } from "@/lib/engine";
import { fakeEngine, franchiseOf, READY } from "@/test/engine";
import { FranchisePage } from "./franchise-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const DRAGON_BALL: TitleSummary = {
  id: 7,
  kind: "series",
  name: "Dragon Ball",
  year: 1986,
  released: "1986-02-26",
  airing: false,
  hasPoster: false,
  files: 150,
  added: "2026-10-11T09:44:00+00:00",
  aired: 153,
  present: 150,
  missing: 3,
  specialsMissing: 0,
  upcoming: 0,
};
const DBZ: TitleSummary = {
  ...DRAGON_BALL,
  id: 8,
  name: "Dragon Ball Z",
  year: 1989,
  released: "1989-04-26",
  files: 291,
  aired: 291,
  present: 291,
  missing: 0,
};
const BATTLE_OF_GODS: TitleSummary = {
  ...DRAGON_BALL,
  id: 9,
  kind: "movie",
  name: "Dragon Ball Z: Battle of Gods",
  year: 2013,
  released: "2013-03-30",
  files: 1,
  aired: 0,
  present: 0,
  missing: 0,
};
const DRAGON_BALL_FRANCHISE = franchiseOf([DRAGON_BALL, DBZ, BATTLE_OF_GODS]);

function renderWithEngine(children: React.ReactNode, at: string) {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? READY : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <MemoryRouter initialEntries={[at]}>
          <Routes>
            <Route path="/franchises/:id" element={children} />
            <Route path="/titles/:id" element={<p>A title</p>} />
            <Route path="*" element={<p>Home</p>} />
          </Routes>
        </MemoryRouter>
      </EngineProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  shell.invoke.mockReset();
});

describe("ShelfCard", () => {
  it.each<[string, FranchiseSummary, string]>([
    ["a title on its own", franchiseOf([DRAGON_BALL]), "TV series · 1986 · 153 episodes"],
    [
      "one series and its film",
      franchiseOf([DBZ, BATTLE_OF_GODS]),
      "TV series · 291 episodes · 1 movie",
    ],
    ["several series", DRAGON_BALL_FRANCHISE, "Franchise · 2 series · 1 movie"],
    [
      "films alone",
      franchiseOf([BATTLE_OF_GODS, { ...BATTLE_OF_GODS, id: 10 }]),
      "Franchise · 2 movies",
    ],
  ])("says what %s is", (_, franchise, facts) => {
    fakeEngine({});
    renderWithEngine(<ShelfCard franchise={franchise} />, "/franchises/1");

    expect(screen.getByText(facts)).toBeInTheDocument();
  });
});

describe("FranchisePage", () => {
  it("shows the franchise and its titles, oldest release first", async () => {
    const fetch = fakeEngine({ "/franchises/7": DRAGON_BALL_FRANCHISE });
    renderWithEngine(<FranchisePage />, "/franchises/7");

    expect(
      await screen.findByRole("heading", { name: "Dragon Ball", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText("Franchise")).toBeInTheDocument();
    expect(screen.getByText("1986 · 2 series · 1 movie")).toBeInTheDocument();
    expect(screen.getByText("441 of 444 episodes")).toBeInTheDocument();
    expect(screen.getByText("3 titles · oldest release first")).toBeInTheDocument();
    const cards = screen.getAllByRole("link", { name: /Dragon Ball/ });
    expect(cards.map((card) => card.textContent)).toEqual([
      expect.stringContaining("TV series · 1986"),
      expect.stringContaining("TV series · 1989"),
      expect.stringContaining("Movie · 2013"),
    ]);
    expect(fetch.mock.calls.some(([input]) => String(input).endsWith("?sort=released"))).toBe(true);
  });

  it("sorts by name too, and leads to each title", async () => {
    const fetch = fakeEngine({ "/franchises/7": DRAGON_BALL_FRANCHISE });
    renderWithEngine(<FranchisePage />, "/franchises/7");

    (await screen.findByRole("radio", { name: "Name" })).click();
    await waitFor(() =>
      expect(fetch.mock.calls.some(([input]) => String(input).endsWith("?sort=name"))).toBe(true),
    );
    screen.getByRole("link", { name: /Battle of Gods/ }).click();

    expect(await screen.findByText("A title")).toBeInTheDocument();
  });

  it("says when the engine couldn't find it", async () => {
    fakeEngine({});
    renderWithEngine(<FranchisePage />, "/franchises/99");

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    screen.getByRole("link", { name: "Library" }).click();
    expect(await screen.findByText("Home")).toBeInTheDocument();
  });
});
