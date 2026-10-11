import { vi } from "vitest";
import type { EngineStatus, Library, Scan, Settings } from "@/lib/engine";

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
