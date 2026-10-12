/** What the Convert screens work out from the engine's lists: the tree of what can be converted,
 * what a choice adds up to, and how long things take, in words. */

import type { Convertible, FranchiseSummary, Job, Way } from "@/lib/engine";

/** A season of a title, or its specials, or a film's file. */
export interface SeasonNode {
  key: string;
  label: string;
  files: Convertible[];
}

export interface TitleNode {
  key: string;
  name: string;
  seasons: SeasonNode[];
  files: Convertible[];
}

/** A franchise of several titles, or one title on its own. */
export interface GroupNode {
  key: string;
  name: string;
  /** Several titles: the franchise's; one: that title's seasons, under the group itself. */
  titles: TitleNode[];
  files: Convertible[];
}

const OTHERS = "Not matched yet";

/**
 * The files by franchise, title and season, in the library's order: franchises as Home sorts them
 * (`franchises`), then files Kura hasn't matched yet.
 */
export function tree(files: Convertible[], franchises: FranchiseSummary[]): GroupNode[] {
  const franchiseOf = new Map<number, FranchiseSummary>();
  for (const franchise of franchises) {
    for (const title of franchise.titles) franchiseOf.set(title.id, franchise);
  }
  const titles = new Map<string, TitleNode>();
  for (const file of files) {
    const key = file.titleId === null ? "none" : `t${file.titleId}`;
    const node = titles.get(key) ?? {
      key,
      name: file.title ?? OTHERS,
      seasons: [],
      files: [],
    };
    node.files.push(file);
    titles.set(key, node);
  }
  for (const node of titles.values()) node.seasons = seasonsOf(node.files);

  const groups: GroupNode[] = [];
  const placed = new Set<string>();
  for (const franchise of franchises) {
    const members = franchise.titles
      .map((title) => titles.get(`t${title.id}`))
      .filter((node): node is TitleNode => node !== undefined);
    if (members.length === 0) continue;
    for (const member of members) placed.add(member.key);
    groups.push({
      key: `f${franchise.id}`,
      name: members.length > 1 ? franchise.name : (members[0]?.name ?? franchise.name),
      titles: members,
      files: members.flatMap((member) => member.files),
    });
  }
  for (const node of titles.values()) {
    if (placed.has(node.key)) continue;
    groups.push({ key: node.key, name: node.name, titles: [node], files: node.files });
  }
  return groups;
}

function seasonsOf(files: Convertible[]): SeasonNode[] {
  const seasons = new Map<string, SeasonNode>();
  for (const file of files) {
    const key = file.season === null ? "film" : `s${file.season}`;
    const node = seasons.get(key) ?? { key, label: seasonLabel(file.season), files: [] };
    node.files.push(file);
    seasons.set(key, node);
  }
  return [...seasons.values()];
}

function seasonLabel(season: number | null): string {
  if (season === null) return "The film";
  return season === 0 ? "Specials" : `Season ${season}`;
}

/** Files that can join the queue: they play, and aren't in it already. */
export function open(files: Convertible[]): Convertible[] {
  return files.filter((file) => !file.broken && !file.waiting);
}

/** What converting `files` one way adds up to. */
export interface Totals {
  files: number;
  /** How long they play. */
  seconds: number;
  gpuSeconds: number;
  sizeBefore: number;
  sizeAfter: number;
  /** The results' size on each drive. */
  byDrive: Record<string, number>;
  /** "SD 480p · 4:3", or "SD 480p · 4:3, 720p · 16:9". */
  sources: string;
}

export function totals(files: Convertible[], way: Way): Totals {
  const byDrive: Record<string, number> = {};
  const sources: string[] = [];
  let seconds = 0;
  let gpuSeconds = 0;
  let sizeBefore = 0;
  let sizeAfter = 0;
  for (const file of files) {
    seconds += file.seconds;
    gpuSeconds += file.ways[way]?.gpuSeconds ?? 0;
    sizeBefore += file.size;
    sizeAfter += file.outputBytes;
    byDrive[file.drive] = (byDrive[file.drive] ?? 0) + file.outputBytes;
    const source = `${sizeClass(file.height)} · ${file.aspect}`;
    if (!sources.includes(source)) sources.push(source);
  }
  return {
    files: files.length,
    seconds,
    gpuSeconds,
    sizeBefore,
    sizeAfter,
    byDrive,
    sources: sources.length > 2 ? `${sources.slice(0, 2).join(", ")} and more` : sources.join(", "),
  };
}

/** "SD 480p", "720p", "1080p", "4K". */
export function sizeClass(height: number): string {
  if (height <= 576) return `SD ${height}p`;
  if (height > 1440) return "4K";
  return `${height}p`;
}

/** GPU time in words: "12 min", "1 h", "35 h", "12 days". */
export function gpuTime(seconds: number): string {
  const minutes = seconds / 60;
  if (minutes < 59.5) return `${Math.max(1, Math.round(minutes))} min`;
  const hours = minutes / 60;
  if (hours < 47.5) return `${Math.round(hours)} h`;
  const days = Math.round(hours / 24);
  return `${days} days`;
}

/** The short form the queue's rows use: "1 h", "12 min", "10 d". */
export function gpuTimeShort(seconds: number): string {
  return gpuTime(seconds).replace(/ days$/, " d");
}

/** The drive a path is on, as Kura writes it: "D:", or a share, "\\\\nas\\anime" (empty for none). */
export function driveOf(path: string): string {
  const letter = /^[a-z]:/i.exec(path)?.[0];
  if (letter) return letter.toUpperCase();
  return /^\\\\[^\\]+\\[^\\]+/.exec(path)?.[0] ?? "";
}

/** Free space wanted on a drive, over a result's size (the engine wants the same). */
export const ROOM = 1.25;

/**
 * Of files to convert on one drive, in turn: the free space their results all want, and how
 * many fit in `free` now, each result taking its size of what's left (as the engine counts).
 */
export function fitting(outputs: number[], free: number): { needed: number; fit: number } {
  let left = free;
  let needed = 0;
  let fit = 0;
  for (const bytes of outputs) {
    const wanted = Math.round(bytes * ROOM);
    needed += wanted;
    if (left >= wanted) {
      fit += 1;
      left -= bytes;
    }
  }
  return { needed, fit };
}

/** When Kura tries again, from now: "in 5 minutes", "in a minute", "in a moment". */
export function retryIn(retryAt: string, now: number): string {
  const minutes = Math.ceil((Date.parse(retryAt) - now) / 60_000);
  if (minutes <= 0) return "in a moment";
  return minutes === 1 ? "in a minute" : `in ${minutes} minutes`;
}

/** Nights of 23:00 to 07:00 that GPU time takes: "about 5 nights", or "less than a night". */
export function nights(seconds: number): string {
  if (seconds < 8 * 3600) return "less than a night";
  const count = Math.ceil(seconds / 3600 / 8);
  return `about ${count} nights`;
}

/** "13 h 40 min of video". */
export function playTime(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours} h ${minutes % 60} min` : `${minutes} min`;
}

/** The queue's waiting files, a title's season at a time: "Dragon Ball Z · Season 1". */
export interface JobGroup {
  key: string;
  label: string;
  jobs: Job[];
}

export function jobGroups(jobs: Job[]): JobGroup[] {
  const groups: JobGroup[] = [];
  for (const job of jobs) {
    const season =
      job.season === null ? "" : job.season === 0 ? "Specials" : `Season ${job.season}`;
    const title = job.title ?? OTHERS;
    const key = `${job.titleId ?? "none"}-${job.season ?? "film"}`;
    const last = groups.at(-1);
    if (last?.key === key) last.jobs.push(job);
    else groups.push({ key, label: season ? `${title} · ${season}` : title, jobs: [job] });
  }
  return groups;
}

/** A job's place in its season, "S01E06", or its file's name for a film or unmatched file. */
export function episodeCode(job: Pick<Job, "season" | "episode" | "path">): string {
  if (job.season === null || job.episode === null) {
    const at = Math.max(job.path.lastIndexOf("\\"), job.path.lastIndexOf("/"));
    return job.path.slice(at + 1);
  }
  const pad = (n: number) => String(n).padStart(2, "0");
  return `S${pad(job.season)}E${pad(job.episode)}`;
}

/** What each method is called on the screens. */
export const METHOD_NAMES = {
  best: "Best",
  fast: "Fast",
  reencode: "Re-encode",
  remux: "Remux",
} as const;

/** The engine each method uses, as the queue tells it: "Real-ESRGAN → HEVC 10-bit". */
export const METHOD_ENGINES = {
  best: "Real-ESRGAN",
  fast: "Anime4K",
  reencode: "Re-encode",
  remux: "Copied",
} as const;
