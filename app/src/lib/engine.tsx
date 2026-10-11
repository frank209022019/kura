import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import {
  createContext,
  type ReactNode,
  use,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

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
  let response: Response;
  try {
    response = await fetch(new URL(path, engine.url), { ...init, headers });
  } catch {
    throw new EngineError("Kura's engine didn't answer.");
  }
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
 * A query for one engine endpoint. It waits until the engine is ready (and `enabled`). `poll`
 * asks again every that many milliseconds while it returns a number for the latest answer (a job
 * in progress). `keep` shows the last answer while a changed question loads (a list re-sorting),
 * instead of nothing.
 */
export function useEngineQuery<T>(
  path: string,
  poll?: (data: T | undefined) => number | false,
  enabled = true,
  keep = false,
) {
  const engine = useEngine();
  return useQuery({
    queryKey: engineKey(engine, path),
    queryFn: () => {
      if (engine.state !== "ready") throw new EngineError("The engine isn't ready yet.");
      return callEngine<T>(engine, path);
    },
    enabled: engine.state === "ready" && enabled,
    refetchInterval: poll ? (query) => poll(query.state.data) : false,
    placeholderData: keep ? keepPreviousData : undefined,
  });
}

/**
 * Asks the engine again for what these paths' queries show, so screens catch up with a change.
 * A path covers everything under it: "/titles" also refreshes "/titles?sort=name" and "/titles/3".
 */
function useRefresh() {
  const engine = useEngine();
  const queries = useQueryClient();
  return useCallback(
    (paths: string[]) => {
      const url = engine.state === "ready" ? engine.url : null;
      return queries.invalidateQueries({
        predicate: ({ queryKey: [scope, address, asked] }) =>
          scope === "engine" &&
          address === url &&
          typeof asked === "string" &&
          paths.some(
            (path) =>
              asked === path || asked.startsWith(`${path}?`) || asked.startsWith(`${path}/`),
          ),
      });
    },
    [engine, queries],
  );
}

/**
 * A change sent to the engine: `send(path, body?)` posts it, then refreshes the queries for
 * `refreshes` so the screen shows the result.
 */
export function useEngineAction<T>(
  refreshes: string[],
  method: "POST" | "PUT" | "DELETE" = "POST",
) {
  const engine = useEngine();
  const refresh = useRefresh();
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
    onSettled: () => refresh(refreshes),
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
  stage: "finding" | "reading" | "identifying" | "checking" | "done" | null;
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
  /** Anime and films identified in the library. */
  titles: number;
  /** Files that need the owner to say which anime they are. */
  waiting: number;
  /** What the scan couldn't do, though it finished (offline, say). */
  note: string | null;
  /** Folders holding more than one anime. */
  mixed: number;
}

const LIBRARY = ["/folders", "/library", "/scan"];

export const useFolders = () => useEngineQuery<LibraryFolder[]>("/folders");
export const useLibrary = () => useEngineQuery<Library>("/library");

/**
 * The latest scan, asked again every second while it runs. A scan fills in the library, so when
 * one stops, the library and its folders are asked again too.
 */
export function useScan() {
  const scan = useEngineQuery<Scan>("/scan", (now) => (now?.state === "running" ? 1000 : false));
  const refresh = useRefresh();
  const running = scan.data?.state === "running";
  const wasRunning = useRef(running);
  useEffect(() => {
    if (wasRunning.current && !running)
      void refresh(["/library", "/folders", "/titles", "/review"]);
    wasRunning.current = running;
  }, [running, refresh]);
  return scan;
}

/** Adds a folder: `add.mutate({ path: "/folders", body: { path } })`. */
export const useAddFolder = () => useEngineAction<LibraryFolder>(LIBRARY);
/** Forgets a folder: `forget.mutate({ path: "/folders/3" })`. Its files stay put. */
export const useForgetFolder = () => useEngineAction<void>(LIBRARY, "DELETE");
/** Starts, pauses or resumes the scan: `/scan`, `/scan/pause` or `/scan/resume`. */
export const useScanAction = () => useEngineAction<Scan>(LIBRARY);

/** Kura's preferences, chosen during setup. */
export interface Settings {
  standard: "cinema-1080" | "compact-720";
  naming: "plex" | "jellyfin" | "keep";
  upscaleSd: boolean;
  upscale720: boolean;
  /** The first-run steps are done. */
  setUp: boolean;
}

export const useSettings = () => useEngineQuery<Settings>("/settings");
/** Saves the preferences: `save.mutate({ path: "/settings", body: settings })`. */
export const useSaveSettings = () => useEngineAction<Settings>(["/settings"], "PUT");

/** Whether Kura has a TMDB key, for episode lists, episode titles and artwork. */
export interface TmdbStatus {
  connected: boolean;
  /** The key's last four characters, to tell which key it is. */
  keyEnd: string | null;
}

export const useTmdb = () => useEngineQuery<TmdbStatus>("/tmdb");
/** Checks a key with TMDB, then keeps it: `connect.mutate({ path: "/tmdb", body: { key } })`. */
export const useConnectTmdb = () => useEngineAction<TmdbStatus>(["/tmdb"], "PUT");
/** Forgets the key: `forget.mutate({ path: "/tmdb" })`. */
export const useForgetTmdb = () => useEngineAction<TmdbStatus>(["/tmdb"], "DELETE");

/** What this PC has to work with. */
export interface System {
  /** As Windows names it; null when Windows wouldn't say. */
  graphicsCard: string | null;
}

export const useSystem = () => useEngineQuery<System>("/system");

/** What a title is, in the words Kura shows: a TV series, a movie, an OVA or a special. */
export type TitleKind = "series" | "movie" | "ova" | "special";

/** The orders a list of titles can take; release date is the default everywhere. */
export type TitleSort = "released" | "name" | "added" | "missing";

/** An anime or film in the library, with how much of it is there. */
export interface TitleSummary {
  id: number;
  kind: TitleKind;
  name: string;
  year: number | null;
  /** The first episode, or the film's release (ISO date): lists sort by it. */
  released: string | null;
  airing: boolean;
  hasPoster: boolean;
  /** Videos in the library. */
  files: number;
  added: string | null;
  /** Numbered episodes out so far; 0 for a film. */
  aired: number;
  present: number;
  missing: number;
  /** Specials and OVAs the library lacks: listed apart, never counted as missing. */
  specialsMissing: number;
  upcoming: number;
}

export interface SeasonCount {
  season: number;
  present: number;
  aired: number;
  total: number;
}

export interface EpisodeRef {
  season: number;
  number: number;
  name: string | null;
  aired: string | null;
}

export interface TitleFile {
  id: number;
  path: string;
  season: number | null;
  episode: number | null;
  episodeEnd: number | null;
  problem: string | null;
  height: number | null;
  codec: string | null;
  duration: number | null;
}

/** How an episode stands; on screen each has its shape (see the status-* utilities). */
export type EpisodeStateName = "ready" | "to convert" | "broken" | "missing" | "upcoming";

export interface EpisodeState {
  /** 0 for the specials. */
  season: number;
  number: number;
  name: string | null;
  aired: string | null;
  state: EpisodeStateName;
  fileId: number | null;
}

/** One title in full: its seasons, every episode's state, what it's missing, and its videos. */
export interface TitleDetail extends TitleSummary {
  /** Where its episode list comes from. */
  source: "tmdb" | "anilist";
  /** Its own folder, when its videos have one. */
  folder: string | null;
  seasons: SeasonCount[];
  missingEpisodes: EpisodeRef[];
  missingSpecials: EpisodeRef[];
  upcomingEpisodes: EpisodeRef[];
  episodes: EpisodeState[];
  videos: TitleFile[];
}

/** The gap analysis Kura wrote next to a title. */
export interface Report {
  path: string;
  text: string;
}

/** The library's titles in `sort` order, asked again every two seconds while `poll`. */
export const useTitles = (sort: TitleSort = "released", poll = false) =>
  useEngineQuery<TitleSummary[]>(`/titles?sort=${sort}`, () => (poll ? 2000 : false), true, true);
export const useTitle = (id: number) => useEngineQuery<TitleDetail>(`/titles/${id}`);
export const useReport = (id: number) => useEngineQuery<Report>(`/titles/${id}/report`);

/** One of Kura's guesses for a file it couldn't place surely. */
export interface Guess {
  anilistId: number;
  title: string;
  kind: TitleKind | null;
  year: number | null;
  episodes: number | null;
  minutes: number | null;
  cover: string | null;
  /** 0 to 100. */
  confidence: number;
  reasons: string[];
}

/** A file waiting for the owner to say which anime it is. */
export interface WaitingFile {
  id: number;
  path: string;
  size: number;
  minutes: number | null;
  height: number | null;
  codec: string | null;
  audio: string[];
  subtitles: string[];
  group: string | null;
  title: string | null;
  season: number | null;
  episode: number | null;
  kind: "episode" | "special" | "movie" | "extra" | "dvd";
  guesses: Guess[];
  /** Other waiting files beside it from the same release. */
  alike: number[];
}

export const useReview = () => useEngineQuery<WaitingFile[]>("/review");
/** AniList's entries for `text`, scored against one file; asked only for two letters or more. */
export const useMatchSearch = (fileId: number, text: string) =>
  useEngineQuery<Guess[]>(
    `/review/${fileId}/search?q=${encodeURIComponent(text.trim())}`,
    undefined,
    text.trim().length >= 2,
  );
/** The owner's choice: `choose.mutate({ path: "/review/7", body: { anilistId, kind, also } })`. */
export const useChooseMatch = () =>
  useEngineAction<{ placed: number }>(["/review", "/titles", "/scan", "/library"]);
/** Not anime: `ignore.mutate({ path: "/review/7/ignore" })`. */
export const useIgnoreFile = () => useEngineAction<void>(["/review", "/scan"]);

/**
 * A picture the engine serves (a poster, a cover, a still) as an address the page can show (an
 * object URL), or null while there's none. Fetched with this launch's token, since the engine
 * answers nothing without it.
 */
export function useEngineImage(path: string | null): string | null {
  const engine = useEngine();
  const [shown, setShown] = useState<{ path: string; address: string } | null>(null);
  useEffect(() => {
    if (path === null || engine.state !== "ready") return;
    let address: string | null = null;
    let cancelled = false;
    const headers = { Authorization: `Bearer ${engine.token}` };
    fetch(new URL(path, engine.url), { headers })
      .then((response) => (response.ok ? response.blob() : null))
      .then((blob) => {
        if (!blob || cancelled) return;
        address = URL.createObjectURL(blob);
        setShown({ path, address });
      })
      .catch(() => {}); // no picture: the placeholder stays
    return () => {
      cancelled = true;
      if (address) URL.revokeObjectURL(address);
    };
  }, [engine, path]);
  return shown !== null && shown.path === path ? shown.address : null;
}

/** A title's poster, when it has one. */
export const usePoster = (titleId: number, has: boolean) =>
  useEngineImage(has ? `/titles/${titleId}/poster` : null);
/** A guess's cover from AniList, through the engine. */
export const useCover = (address: string | null) =>
  useEngineImage(address ? `/artwork?address=${encodeURIComponent(address)}` : null);
/** One of a waiting file's three stills (0, 1 or 2). */
export const useStill = (fileId: number, index: number) =>
  useEngineImage(`/review/${fileId}/stills/${index}`);
