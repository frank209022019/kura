import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { createContext, type ReactNode, use, useEffect, useState } from "react";

/** The engine as Kura's shell reports it. Mirrors `EngineStatus` in src-tauri/src/engine.rs. */
export type EngineStatus =
  | { state: "starting" }
  | { state: "ready"; url: string; token: string }
  | { state: "failed"; message: string; details: string };

type ReadyEngine = Extract<EngineStatus, { state: "ready" }>;

const EngineContext = createContext<EngineStatus>({ state: "starting" });

/** Follows the engine's status: asks the shell once, then listens for changes. */
export function EngineProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<EngineStatus>({ state: "starting" });

  useEffect(() => {
    let heardEvent = false;
    const stopListening = listen<EngineStatus>("engine-status", (event) => {
      heardEvent = true;
      setStatus(event.payload);
    });
    invoke<EngineStatus>("engine_status").then((current) => {
      if (!heardEvent) setStatus(current); // an event is always newer than this answer
    });
    return () => {
      stopListening.then((unlisten) => unlisten());
    };
  }, []);

  return <EngineContext value={status}>{children}</EngineContext>;
}

export function useEngine(): EngineStatus {
  return use(EngineContext);
}

/** Asks the shell to start the engine again, after it failed. */
export function restartEngine(): Promise<void> {
  return invoke("restart_engine");
}

export class EngineError extends Error {}

/** Calls the engine's HTTP API with this launch's token. */
export async function callEngine<T>(
  engine: ReadyEngine,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${engine.token}`);
  const response = await fetch(new URL(path, engine.url), { ...init, headers });
  if (!response.ok) {
    throw new EngineError(
      (await problemIn(response)) ??
        `The engine answered ${response.status} to ${init?.method ?? "GET"} ${path}.`,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** The sentence the engine sends with a refusal (FastAPI's `detail`), if it sent one. */
async function problemIn(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // not JSON: fall back to the status
  }
  return null;
}

function engineKey(engine: EngineStatus, path: string) {
  return ["engine", engine.state === "ready" ? engine.url : null, path];
}

/**
 * A query for one engine endpoint. It waits until the engine is ready. `poll` asks again every
 * that many milliseconds while it returns a number for the latest answer (a job in progress).
 */
export function useEngineQuery<T>(path: string, poll?: (data: T | undefined) => number | false) {
  const engine = useEngine();
  return useQuery({
    queryKey: engineKey(engine, path),
    queryFn: () => {
      if (engine.state !== "ready") throw new EngineError("The engine isn't ready yet.");
      return callEngine<T>(engine, path);
    },
    enabled: engine.state === "ready",
    refetchInterval: poll ? (query) => poll(query.state.data) : false,
  });
}

/**
 * A change sent to the engine: `send(path, body?)` posts it, then refreshes the queries for
 * `refreshes` so the screen shows the result.
 */
export function useEngineAction<T>(refreshes: string[], method: "POST" | "DELETE" = "POST") {
  const engine = useEngine();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) => {
      if (engine.state !== "ready") throw new EngineError("The engine isn't ready yet.");
      const init: RequestInit = { method };
      if (body !== undefined) {
        init.body = JSON.stringify(body);
        init.headers = { "Content-Type": "application/json" };
      }
      return callEngine<T>(engine, path, init);
    },
    onSettled: () =>
      Promise.all(
        refreshes.map((path) => queries.invalidateQueries({ queryKey: engineKey(engine, path) })),
      ),
  });
}

// The engine's API. These types mirror engine/openapi.json: change both together.

export interface Health {
  status: "ok";
  version: string;
  dataDir: string;
  schemaVersion: number;
}

export const useHealth = () => useEngineQuery<Health>("/health");

export type ToolState = "missing" | "downloading" | "unpacking" | "ready" | "failed";

/** Something Kura downloads to work with, such as ffmpeg (engine/src/kura/downloads.json). */
export interface Tool {
  id: string;
  name: string;
  version: string;
  purpose: string;
  licence: string;
  size: number;
  state: ToolState;
  done: number;
  problem: string | null;
}

const busy = (state: ToolState) => state === "downloading" || state === "unpacking";

/** Kura's tools, asked again every second while one is downloading. */
export const useTools = () =>
  useEngineQuery<Tool[]>("/tools", (tools) =>
    tools?.some((tool) => busy(tool.state)) ? 1000 : false,
  );

/** Starts downloading a tool: `download.mutate({ path: "/tools/ffmpeg/download" })`. */
export const useDownloadTool = () => useEngineAction<Tool>(["/tools"]);

/** A folder in the library. */
export interface LibraryFolder {
  id: number;
  path: string;
  addedAt: string;
  /** False while its drive is unplugged. */
  available: boolean;
  files: number;
  unread: number;
  problems: number;
}

/** The library at a glance. */
export interface Library {
  folders: number;
  files: number;
  size: number;
  unread: number;
  problems: number;
  sd: number;
  hd720: number;
  hd1080: number;
  larger: number;
}

export type ScanState = "idle" | "running" | "paused" | "done" | "failed";

/** The latest scan. */
export interface Scan {
  state: ScanState;
  stage: "finding" | "reading" | "done" | null;
  startedAt: string | null;
  finishedAt: string | null;
  found: number;
  toRead: number;
  read: number;
  problems: number;
  current: string | null;
  secondsLeft: number | null;
  unavailable: string[];
  problem: string | null;
}

const LIBRARY = ["/folders", "/library", "/scan"];

export const useFolders = () => useEngineQuery<LibraryFolder[]>("/folders");
export const useLibrary = () => useEngineQuery<Library>("/library");

/** The latest scan, asked again every second while it runs. */
export const useScan = () =>
  useEngineQuery<Scan>("/scan", (scan) => (scan?.state === "running" ? 1000 : false));

/** Adds a folder: `add.mutate({ path: "/folders", body: { path } })`. */
export const useAddFolder = () => useEngineAction<LibraryFolder>(LIBRARY);
/** Forgets a folder: `forget.mutate({ path: "/folders/3" })`. Its files stay put. */
export const useForgetFolder = () => useEngineAction<void>(LIBRARY, "DELETE");
/** Starts, pauses or resumes the scan: `/scan`, `/scan/pause` or `/scan/resume`. */
export const useScanAction = () => useEngineAction<Scan>(LIBRARY);
