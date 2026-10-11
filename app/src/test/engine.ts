import { vi } from "vitest";
import type {
  EngineStatus,
  FranchiseSummary,
  Library,
  Scan,
  Settings,
  TitleKind,
  TitleSummary,
} from "@/lib/engine";

/** The engine as tests see it: ready, on a made-up address. */
export const READY: EngineStatus = {
  state: "ready",
  url: "http://127.0.0.1:5000",
  token: "secret",
};

export const SETTINGS: Settings = {
  standard: "cinema-1080",
  naming: "plex",
  upscaleSd: true,
  upscale720: true,
  setUp: true,
};

export const NO_LIBRARY: Library = {
  folders: 0,
  files: 0,
  size: 0,
  unread: 0,
  problems: 0,
  sd: 0,
  hd720: 0,
  hd1080: 0,
  larger: 0,
};

export const NO_SCAN: Scan = {
  state: "idle",
  stage: null,
  startedAt: null,
  finishedAt: null,
  found: 0,
  toRead: 0,
  read: 0,
  problems: 0,
  current: null,
  secondsLeft: null,
  unavailable: [],
  problem: null,
  titles: 0,
  waiting: 0,
  note: null,
  mixed: 0,
};

type Answer = unknown | ((init: RequestInit | undefined) => unknown);

/**
 * Stands in for the engine's HTTP API: `answers` maps "GET /scan" (or just "/scan" for GET) to the
 * JSON to send back, or to a function of the request. Anything else gets a 404.
 */
export function fakeEngine(answers: Record<string, Answer>) {
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    const method = init?.method ?? "GET";
    const answer =
      answers[`${method} ${url.pathname}`] ??
      (method === "GET" ? answers[url.pathname] : undefined);
    if (answer === undefined) return Response.json({ detail: "Not found" }, { status: 404 });
    const body =
      typeof answer === "function" ? (answer as (init?: RequestInit) => unknown)(init) : answer;
    if (body instanceof Response) return body;
    return body === null ? new Response(null, { status: 204 }) : Response.json(body);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

/** A franchise as the engine sends it, made of these titles; its first series (or else its
 * first title) leads it. */
export function franchiseOf(titles: TitleSummary[], name?: string): FranchiseSummary {
  const lead = titles.find((title) => title.kind === "series") ?? titles[0];
  if (!lead) throw new Error("A franchise has a title at least.");
  type Counted = "files" | "aired" | "present" | "missing" | "specialsMissing" | "upcoming";
  const sum = (key: Counted) => titles.reduce((total, title) => total + title[key], 0);
  const count = (kind: TitleKind) => titles.filter((title) => title.kind === kind).length;
  const dates = titles.map((title) => title.released).filter((date) => date !== null);
  return {
    id: lead.id,
    name: name ?? lead.name,
    released: dates.sort()[0] ?? null,
    kinds: {
      series: count("series"),
      movie: count("movie"),
      ova: count("ova"),
      special: count("special"),
    },
    hasPoster: lead.hasPoster,
    airing: titles.some((title) => title.airing),
    files: sum("files"),
    added: lead.added,
    aired: sum("aired"),
    present: sum("present"),
    missing: sum("missing"),
    specialsMissing: sum("specialsMissing"),
    upcoming: sum("upcoming"),
    titles,
  };
}
