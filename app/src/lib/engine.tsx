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
 * one stops, the library, its folders and what Kura proposes from them are asked again too.
 */
export function useScan() {
  // Every second while a scan runs; every ten seconds otherwise, so a scan Kura starts on its own
  // (when a video arrives) shows too.
  const scan = useEngineQuery<Scan>("/scan", (now) => (now?.state === "running" ? 1000 : 10_000));
  const refresh = useRefresh();
  const running = scan.data?.state === "running";
  const wasRunning = useRef(running);
  useEffect(() => {
    if (wasRunning.current && !running)
      void refresh([
        "/library",
        "/folders",
        "/titles",
        "/franchises",
        "/review",
        "/tidy",
        "/history",
      ]);
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
  /** A gap analysis next to each anime that has a folder of its own. */
  reports: boolean;
  /** Days copies set aside and converted files' originals are kept, or null: for good. */
  quarantineDays: 7 | 30 | 90 | null;
  /** Poster and background pictures next to each show, for media servers. */
  artwork: boolean;
}

export const useSettings = () => useEngineQuery<Settings>("/settings");
/** Saves the preferences: `save.mutate({ path: "/settings", body: settings })`. The standard
 * decides what's left to convert, so the Convert screen is asked again too. */
export const useSaveSettings = () =>
  useEngineAction<Settings>(["/settings", "/convert", "/queue", "/data"], "PUT");

/** A drive's quarantine folder: copies set aside and converted files' originals. */
export interface Quarantined {
  folder: string;
  bytes: number;
  files: number;
}

/** How big each part of Kura's data is (Settings > Your data). */
export interface DataSizes {
  /** The data folder. */
  folder: string;
  database: number;
  artwork: number;
  /** Answers from TMDB and AniList, stills and comparison frames. */
  cache: number;
  logs: number;
  backups: number;
  tools: number;
  /** On each drive the library is on. */
  quarantine: Quarantined[];
  /** How the last move to another folder went. */
  moved: { source: string; target: string; at: string; problem: string | null } | null;
}

export const useDataSizes = () => useEngineQuery<DataSizes>("/data");
/**
 * Asks for Kura's data to move to another folder as the engine starts again, which the caller
 * asks the shell for next: `move.mutate({ path: "/data/move", body: { folder } })`.
 */
export const useMoveData = () => useEngineAction<void>([]);
/** Writes the export zip: `exporting.mutate({ path: "/export", body: { folder } })`. */
export const useExport = () => useEngineAction<{ path: string; size: number }>(["/data"]);

/** A backup of Kura's records, made each night (Settings > Your data). */
export interface Backup {
  /** "kura 2026-10-11 0300.db" */
  name: string;
  /** Local time, to the minute: "2026-10-11T03:00". */
  made: string;
  size: number;
  /** Made just before another backup was restored. */
  beforeRestoring: boolean;
  /** The database an imported export held. */
  fromExport: boolean;
  /** Made when the owner asked ("Back up now"); kept apart from the nightly ones. */
  byHand: boolean;
}

export interface Backups {
  /** Newest first. */
  backups: Backup[];
  /** How the last restore went. */
  restored: { name: string; at: string; problem: string | null } | null;
}

export const useBackups = () => useEngineQuery<Backups>("/backups");
/** Makes a backup now: `backUp.mutate({ path: "/backups" })`. */
export const useBackUp = () => useEngineAction<Backup>(["/backups", "/data"]);
/**
 * Asks for a backup to be restored as the engine starts again, which the caller asks the shell
 * for next: `restore.mutate({ path: "/backups/<name>/restore" })`.
 */
export const useRestoreBackup = () => useEngineAction<void>([]);
/**
 * Asks for an export's records to be put in place as the engine starts again, the way a backup
 * is restored: `importing.mutate({ path: "/backups/import", body: { path } })`.
 */
export const useImportExport = () => useEngineAction<void>([]);

/** Whether Kura has a TMDB key, for episode lists, episode titles and artwork. */
export interface TmdbStatus {
  connected: boolean;
  /** The key's last four characters, to tell which key it is. */
  keyEnd: string | null;
}

export const useTmdb = () => useEngineQuery<TmdbStatus>("/tmdb");
/**
 * Checks a key with TMDB, then keeps it: `connect.mutate({ path: "/tmdb", body: { key } })`. A
 * scan then places what AniList alone matched by TMDB's lists, so the scan is asked about again.
 */
export const useConnectTmdb = () => useEngineAction<TmdbStatus>(["/tmdb", "/scan"], "PUT");
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
  /** In bytes. */
  size: number;
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
  /** The franchise it's one of, when it's one of several. */
  franchise: FranchiseRef | null;
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
export const useTitle = (id: number, enabled = true) =>
  useEngineQuery<TitleDetail>(`/titles/${id}`, undefined, enabled);
export const useReport = (id: number) => useEngineQuery<Report>(`/titles/${id}/report`);

export interface FranchiseRef {
  /** Its lead title's. */
  id: number;
  name: string;
}

/**
 * Titles AniList ties together by story: a franchise's series, films, OVAs and specials. A title
 * on its own is a franchise of one.
 */
export interface FranchiseSummary extends FranchiseRef {
  /** Its first release (ISO date). */
  released: string | null;
  kinds: Record<TitleKind, number>;
  /** Its lead's. */
  hasPoster: boolean;
  airing: boolean;
  files: number;
  added: string | null;
  aired: number;
  present: number;
  missing: number;
  specialsMissing: number;
  upcoming: number;
  /** In the order asked for. */
  titles: TitleSummary[];
}

/** Every franchise with its titles, in `sort` order: Home's shelf. */
export const useFranchises = (sort: TitleSort = "released") =>
  useEngineQuery<FranchiseSummary[]>(`/franchises?sort=${sort}`, undefined, true, true);
/** The franchise a title belongs to (any of its titles finds it), its titles in `sort` order. */
export const useFranchise = (id: number, sort: TitleSort = "released") =>
  useEngineQuery<FranchiseSummary>(`/franchises/${id}?sort=${sort}`, undefined, true, true);

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

/**
 * The files waiting for a match; with `title`, that title's files as one, to change its match (its
 * first file, with the others alike).
 */
export const useReview = (title: number | null = null) =>
  useEngineQuery<WaitingFile[]>(title === null ? "/review" : `/review?title=${title}`);
/**
 * AniList's entries for `text`, scored against one file; asked only for two letters or more. The
 * last answer stays on screen while the next loads.
 */
export const useMatchSearch = (fileId: number, text: string) =>
  useEngineQuery<Guess[]>(
    `/review/${fileId}/search?q=${encodeURIComponent(text.trim())}`,
    undefined,
    text.trim().length >= 2,
    true,
  );
/** What the owner's choice did: files placed, files that didn't fit it and wait now, and where
 * the file went. */
export interface Chosen {
  placed: number;
  waiting: number;
  titleId: number | null;
}

/**
 * The owner's choice: `choose.mutate({ path: "/review/7", body: { anilistId, kind, also, episode } })`,
 * or with `title` instead of `also`, a whole title's new match (each file keeps its kind).
 */
export const useChooseMatch = () =>
  useEngineAction<Chosen>(["/review", "/titles", "/franchises", "/scan", "/library"]);
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

/**
 * A picture the engine makes on asking (a frame to compare), with why it couldn't when it
 * couldn't: `address` while it's there, `problem` in the engine's words.
 */
export function useEnginePicture(path: string | null): {
  address: string | null;
  problem: string | null;
} {
  const engine = useEngine();
  const [shown, setShown] = useState<{
    path: string;
    address: string | null;
    problem: string | null;
  } | null>(null);
  useEffect(() => {
    if (path === null || engine.state !== "ready") return;
    let address: string | null = null;
    let cancelled = false;
    const headers = { Authorization: `Bearer ${engine.token}` };
    fetch(new URL(path, engine.url), { headers })
      .then(async (response) => {
        if (cancelled) return;
        if (!response.ok) {
          const problem = (await problemIn(response)) ?? "Kura couldn't make the picture.";
          if (!cancelled) setShown({ path, address: null, problem });
          return;
        }
        const blob = await response.blob();
        if (cancelled) return;
        address = URL.createObjectURL(blob);
        setShown({ path, address, problem: null });
      })
      .catch(() => {
        if (!cancelled) setShown({ path, address: null, problem: "Kura's engine didn't answer." });
      });
    return () => {
      cancelled = true;
      if (address) URL.revokeObjectURL(address);
    };
  }, [engine, path]);
  if (shown === null || shown.path !== path) return { address: null, problem: null };
  return { address: shown.address, problem: shown.problem };
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

/** Why a change is proposed: a rename in place, a move out of a folder holding several anime,
 * or a second copy of an episode set aside. */
export type TidyCategory = "rename" | "mixed" | "duplicate";

/** One change Kura proposes. Nothing moves until the owner applies it. */
export interface ProposedChange {
  kind: "move" | "quarantine";
  source: string;
  target: string;
  /** The library folder it's in. */
  root: string;
  /** "Cowboy Bebop · S01E01", "Cowboy Bebop · S01E01 · subtitles". */
  label: string;
  reason: string;
  category: TidyCategory;
  titleId: number;
  title: string;
}

/** What decides between two copies of one episode. */
export interface CopyFacts {
  path: string;
  height: number | null;
  codec: string | null;
  audio: string[];
  /** Subtitle tracks that can be switched off. */
  subtitles: number;
  size: number;
  plays: boolean;
}

/** Copies of one episode or movie: the one Kura keeps, and the ones it sets aside. */
export interface Duplicate {
  label: string;
  keep: CopyFacts;
  drop: CopyFacts[];
  reason: string;
}

export interface TidyProposal {
  changes: ProposedChange[];
  /** Videos that stay where they are, and why. */
  skipped: { path: string; reason: string }[];
  duplicates: Duplicate[];
  /** Videos that need a match first. */
  waiting: number;
  /** Videos that won't play. */
  broken: number;
}

/** A proposed change as the owner saw it: what applying sends, so the engine makes exactly
 * that, or nothing if its proposal changed meanwhile. */
export type ReviewedChange = Pick<ProposedChange, "source" | "kind" | "target">;

/** What applying or undoing a tidy-up did. */
export interface TidyResult {
  /** Null when nothing was asked for. */
  planId: number | null;
  moved: number;
  quarantined: number;
  problems: { label: string; source: string; problem: string }[];
}

/** Where every video would go; `keep` holds copies the owner keeps instead. */
export const useTidy = (keep: string[] = []) =>
  useEngineQuery<TidyProposal>(
    `/tidy${keep.length ? `?${keep.map((path) => `keep=${encodeURIComponent(path)}`).join("&")}` : ""}`,
    undefined,
    true,
    true,
  );
const TIDIED = [
  "/tidy",
  "/history",
  "/titles",
  "/franchises",
  "/library",
  "/review",
  "/convert",
  "/data",
];
/** Makes the changes: `apply.mutate({ path: "/tidy", body: { changes, keep } })`, `changes`
 * being ReviewedChange[]. */
export const useApplyTidy = () => useEngineAction<TidyResult>(TIDIED);
/** Puts back what a tidy-up moved (or what couldn't go back last time):
 * `undo.mutate({ path: "/plans/12/undo" })`. */
export const useUndoPlan = () => useEngineAction<TidyResult>(TIDIED);
/**
 * Deletes videos the way Kura deletes: into the quarantine with their subtitles, put back from
 * History till it's cleared out: `remove.mutate({ path: "/files/delete", body: { files } })`.
 */
export const useDeleteFiles = () => useEngineAction<TidyResult>([...TIDIED, "/queue"]);

/** A video's picture and size, before or after converting. */
export interface Picture {
  height: number | null;
  codec: string | null;
  size: number | null;
}

/** What converting made of a file, as History tells it. */
export interface Conversion {
  jobId: number;
  method: Method;
  before: Picture;
  after: Picture;
  /** How long converting took. */
  seconds: number | null;
  /** The original is back in its place. */
  restored: boolean;
}

/** A tidy-up or conversion that was applied, as History lists it. */
export interface PlanDone {
  id: number;
  kind: "tidy" | "convert";
  /** "Renamed 26 Cowboy Bebop files", "Converted Trigun · S01E03". */
  title: string;
  appliedAt: string;
  undoneAt: string | null;
  moved: number;
  quarantined: number;
  failed: number;
  undone: number;
  /** The owner deleted these videos: they went to quarantine. */
  deleted: boolean;
  conversion: Conversion | null;
}

export interface ScanDone {
  id: number;
  startedAt: string;
  finishedAt: string | null;
  state: "running" | "paused" | "done" | "failed";
  problem: string | null;
  note: string | null;
}

/** Everything Kura did, newest first. */
export interface History {
  plans: PlanDone[];
  scans: ScanDone[];
}

export const useHistory = () => useEngineQuery<History>("/history");

/** How a file is converted: copied into MKV, re-encoded, or upscaled fast or with the AI model. */
export type Method = "remux" | "reencode" | "fast" | "best";

/** The ways the owner can pick from on the Convert screen. */
export type Way = "best" | "fast" | "reencode";

/** A video not at the library's standard yet, with what each way of converting it takes. */
export interface Convertible {
  fileId: number;
  /** "Dragon Ball Z · S01E06". */
  label: string;
  titleId: number | null;
  title: string | null;
  season: number | null;
  episode: number | null;
  /** How long it plays. */
  seconds: number;
  height: number;
  /** "4:3", "16:9". */
  aspect: string;
  size: number;
  /** "D:". */
  drive: string;
  /** What each way gives it (never more than suits it), and its GPU time. Empty when broken. */
  ways: Partial<Record<Way, { method: Method; gpuSeconds: number }>>;
  /** The result's size, about. */
  outputBytes: number;
  /** In the queue already, or converting. */
  waiting: boolean;
  /** It won't play, so it can't be converted. */
  broken: boolean;
}

export interface ConvertOptions {
  /** "Cinema 1080p". */
  standard: string;
  files: Convertible[];
  /** Bytes free on each drive the files are on. */
  free: Record<string, number>;
}

export const useConvertOptions = () => useEngineQuery<ConvertOptions>("/convert");

export type JobState =
  | "queued"
  | "running"
  | "replacing"
  | "done"
  | "failed"
  | "skipped"
  | "restored";

/** A file in the conversion queue. */
export interface Job {
  id: number;
  fileId: number;
  path: string;
  label: string;
  titleId: number | null;
  title: string | null;
  season: number | null;
  episode: number | null;
  method: Method;
  state: JobState;
  /** How long it takes on the graphics card, as estimated. */
  gpuSeconds: number;
  addedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  /** Why it failed, in words. */
  problem: string | null;
  sourceSize: number;
  outputSize: number | null;
  /** The result's picture, for a file still to finish. */
  width: number | null;
  height: number | null;
  /** Waiting, and its drive isn't connected: it goes when the drive is back. */
  driveMissing: boolean;
  /**
   * Made, and waiting beside its original for another app (a player) to let go of it: when Kura
   * tries again to put it in place.
   */
  retryAt: string | null;
}

/** The file converting now, and how it's going. */
export interface RunningJob {
  job: Job;
  stage: "looking" | "converting" | "checking" | "replacing";
  frames: number;
  total: number;
  secondsLeft: number | null;
  /** Frames a second, over the last ten minutes. */
  fps: number | null;
}

export interface QueueStatus {
  paused: boolean;
  schedule: "now" | "nights";
  /** Nights only, and it's day: files start again at 23:00. */
  waitsForNight: boolean;
  /** Why nothing converts though files wait (no ffmpeg, say). */
  problem: string | null;
  running: RunningJob | null;
  /** In the order they'll go. */
  queued: Job[];
  /** The work left, in seconds of GPU time. */
  gpuSeconds: number;
  /** Finished today, newest first. */
  today: Job[];
  /** The graphics card's load and temperature, while a file converts. */
  gpu: { busy: number; celsius: number } | null;
}

/** The queue, asked again every two seconds while a file converts, else every ten. */
export const useQueue = () =>
  useEngineQuery<QueueStatus>("/queue", (now) => (now?.running ? 2000 : 10_000));

const QUEUED = ["/queue", "/convert", "/history", "/library", "/titles"];
/**
 * Adds files: `add.mutate({ path: "/queue", body: { files, method, when } })`, `when` being
 * "now", "nights" (both resume a paused queue) or "after" (the queue goes on as it is).
 */
export const useAddToQueue = () => useEngineAction<{ added: number }>(QUEUED);
/**
 * Changes the queue: `/queue/pause`, `/queue/resume`, `/queue/7/skip`, `/queue/7/retry`,
 * `/queue/7/move` (with `{ before }`) or `/queue/7/restore`.
 */
export const useQueueAction = () => useEngineAction<unknown>(QUEUED);
/** Takes a waiting file out: `remove.mutate({ path: "/queue/7" })`. */
export const useRemoveFromQueue = () => useEngineAction<void>(QUEUED, "DELETE");
/** Converts whenever files wait, or only at night: `{ path: "/queue/schedule", body: { schedule } }`. */
export const useQueueSchedule = () => useEngineAction<QueueStatus>(QUEUED, "PUT");
