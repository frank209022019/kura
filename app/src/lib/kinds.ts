import type { TitleKind } from "@/lib/engine";

/** The words for each kind of title, as every screen says them. */
const WORDS: Record<TitleKind, { full: string; short: string; one: string; many: string }> = {
  series: { full: "TV series", short: "TV", one: "series", many: "series" },
  movie: { full: "Movie", short: "Movie", one: "movie", many: "movies" },
  ova: { full: "OVA", short: "OVA", one: "OVA", many: "OVAs" },
  special: { full: "Special", short: "Special", one: "special", many: "specials" },
};

/** "TV series", "Movie", "OVA" or "Special"; `short` gives "TV" for a series, where room is tight. */
export function kindWord(kind: TitleKind, short = false): string {
  return short ? WORDS[kind].short : WORDS[kind].full;
}

/** "3 movies", "1 OVA". */
export function kindCount(kind: TitleKind, count: number): string {
  return `${count.toLocaleString("en-GB")} ${count === 1 ? WORDS[kind].one : WORDS[kind].many}`;
}

/** "1 file", "287 files". */
export function files(count: number): string {
  return `${count.toLocaleString("en-GB")} ${count === 1 ? "file" : "files"}`;
}
