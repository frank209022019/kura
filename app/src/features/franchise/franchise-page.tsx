import { useState } from "react";
import { useParams, useSearchParams } from "react-router";
import { Breadcrumb, LIBRARY } from "@/components/breadcrumb";
import { EngineProblem } from "@/components/engine-problem";
import { Poster } from "@/components/poster";
import { CardsSkeleton, HeaderSkeleton, ListHeadSkeleton, Loading } from "@/components/skeleton";
import { SortControl } from "@/components/sort-control";
import { StatusShape } from "@/components/status";
import { TitleCard } from "@/components/title-card";
import { byKind, CardGrid, groupsByType, orderWords, together } from "@/components/title-groups";
import {
  type FranchiseSummary,
  type MissingTitle,
  type TitleKind,
  type TitleSort,
  type TitleSummary,
  useCover,
  useFranchise,
  useFranchiseMissing,
} from "@/lib/engine";
import { kindCount, kindWord } from "@/lib/kinds";
import { share } from "@/lib/share";
import { cn } from "@/lib/utils";

/** A title on a franchise's page: one the library has, or one it has no part of. */
type Shelved =
  | { kind: TitleKind; name: string; released: string | null; title: TitleSummary }
  | { kind: TitleKind; name: string; released: string | null; missing: MissingTitle };

/** A franchise: its series, films, OVAs and specials, by type and oldest release first unless the
 * owner picks another order, each leading to its own page. "Missing titles" puts in among them
 * the ones AniList ties to the franchise that the library has no part of. The address keeps
 * whether they're in (`?missing`, as a title's own "Missing titles" leads here), so going back
 * to the page finds it as it was left. */
export function FranchisePage() {
  const { id } = useParams();
  const [address, setAddress] = useSearchParams();
  const [sort, setSort] = useState<TitleSort>("released");
  const whole = address.has("missing");
  const setWhole = (on: boolean) => setAddress(on ? { missing: "" } : {}, { replace: true });
  const franchise = useFranchise(Number(id), sort);
  const missing = useFranchiseMissing(Number(id));

  if (!franchise.data) {
    return (
      <>
        <Breadcrumb trail={[LIBRARY]} current="…" />
        <EngineProblem queries={[franchise]} />
        <Loading label="Loading the franchise" queries={[franchise]}>
          <HeaderSkeleton />
          <div className="flex flex-col gap-4">
            <ListHeadSkeleton />
            <CardsSkeleton count={8} />
          </div>
        </Loading>
      </>
    );
  }
  const found = franchise.data;
  const rest = missing.data;
  // Offered while there's something it lacks, or Kura is still looking; on only while offered.
  const offered = rest && (rest.titles.length > 0 || rest.looking) ? rest : null;
  const on = whole && offered !== null;
  const lacking = on ? offered.titles : [];
  const items = shelved(found.titles, lacking, sort);
  const count = on
    ? [
        `${found.titles.length} of ${found.titles.length + lacking.length} titles`,
        offered.looking && "still looking up the rest",
      ]
    : [found.titles.length === 1 ? "1 title" : `${found.titles.length} titles`];
  return (
    <>
      <Breadcrumb trail={[LIBRARY]} current={found.name} />
      <Header franchise={found} />
      <EngineProblem queries={[franchise]} />
      <section
        aria-labelledby="franchise-titles"
        className="flex animate-fade-up flex-col gap-4 [animation-delay:90ms]"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-col gap-0.5">
            <h2 id="franchise-titles" className="type-heading">
              Titles
            </h2>
            <span className="text-13 text-fg-muted">
              {[...count, orderWords(sort)].filter(Boolean).join(" · ")}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <SortControl value={sort} onChange={setSort} />
            {offered && (
              <>
                <span aria-hidden="true" className="h-6 w-px bg-edge" />
                <MissingToggle
                  on={on}
                  count={offered.titles.length}
                  looking={offered.looking}
                  onChange={setWhole}
                />
              </>
            )}
          </div>
        </div>
        <CardGrid
          groups={groupsByType(sort) ? byKind(items) : together(items)}
          keyOf={(item) => ("title" in item ? item.title.id : `missing ${item.missing.anilistId}`)}
          card={(item) =>
            "title" in item ? (
              <TitleCard title={item.title} />
            ) : (
              <MissingCard title={item.missing} />
            )
          }
        />
      </section>
    </>
  );
}

/** The library's titles, and with them the ones it lacks: in their places by release or name,
 * or after the library's own when the order looks at what's in the library (newest added, most
 * missing). */
function shelved(titles: TitleSummary[], lacking: MissingTitle[], sort: TitleSort): Shelved[] {
  const held: Shelved[] = titles.map((title) => ({ ...facts(title), title }));
  if (lacking.length === 0) return held;
  const missing: Shelved[] = lacking.map((title) => ({ ...facts(title), missing: title }));
  if (!groupsByType(sort)) return [...held, ...missing];
  return [...held, ...missing].sort(sort === "name" ? byName : byRelease);
}

function facts(title: TitleSummary | MissingTitle) {
  return { kind: title.kind, name: title.name, released: title.released };
}

function byName(a: Shelved, b: Shelved): number {
  return a.name.localeCompare(b.name, "en", { sensitivity: "base" });
}

/** Oldest release first, undated last, then by name. */
function byRelease(a: Shelved, b: Shelved): number {
  if (a.released === b.released) return byName(a, b);
  if (a.released === null) return 1;
  if (b.released === null) return -1;
  return a.released < b.released ? -1 : 1;
}

/** Puts the titles the library has no part of among the franchise's, or takes them away. */
function MissingToggle(props: {
  on: boolean;
  count: number;
  looking: boolean;
  onChange: (on: boolean) => void;
}) {
  return (
    <div className="inline-flex rounded-22 bg-well p-1">
      <button
        type="button"
        aria-pressed={props.on}
        onClick={() => props.onChange(!props.on)}
        className={cn(
          "press inline-flex min-h-9 cursor-pointer items-center gap-2 rounded-18 px-4 font-bold text-fg-soft",
          props.on && "bg-accent font-extrabold text-on-accent",
        )}
      >
        Missing titles{" "}
        <span className={cn("font-mono text-12", props.on ? "text-on-accent" : "text-fg-muted")}>
          {props.count === 0 && props.looking ? "…" : props.count}
        </span>
      </button>
    </div>
  );
}

/** A title the library has no part of: a place kept for it, its outline dotted, AniList's cover
 * dimmed in it, with a hollow "Not in library" (a fainter "Coming" for one not out yet). Kura
 * has no page for it, so it leads nowhere. */
function MissingCard({ title }: { title: MissingTitle }) {
  const cover = useCover(title.cover);
  return (
    <div className="flex flex-col gap-2.5">
      <div
        className={cn(
          "relative aspect-[2/3] overflow-hidden rounded-14 border-2 border-dotted",
          title.coming ? "border-missing/40" : "border-missing",
        )}
      >
        {cover && (
          <img
            src={cover}
            alt=""
            aria-hidden="true"
            className="absolute inset-0 size-full object-cover opacity-40"
          />
        )}
        <span className="absolute top-2 left-2 inline-flex h-6 items-center gap-1.5 rounded-full bg-tag px-2.25 font-bold text-11">
          <StatusShape state={title.coming ? "upcoming" : "missing"} className="size-2" />
          {title.coming ? "Coming" : "Not in library"}
        </span>
      </div>
      <span className="flex flex-col gap-px px-0.5">
        <span className="truncate font-extrabold text-14 text-fg-muted">{title.name}</span>
        <span className="truncate text-12 text-fg-faint">{missingFacts(title)}</span>
      </span>
    </div>
  );
}

/** "TV series · 2024 · 20 episodes", "Movie · 1986", "TV series · 2026 · airing". */
function missingFacts(title: MissingTitle): string {
  const parts = [kindWord(title.kind)];
  if (title.year) parts.push(String(title.year));
  if (title.airing) parts.push("airing");
  else if (title.kind !== "movie" && title.episodes !== null && title.episodes > 1) {
    parts.push(`${title.episodes} episodes`);
  }
  return parts.join(" · ");
}

const KINDS: TitleKind[] = ["series", "movie", "ova", "special"];

function Header({ franchise }: { franchise: FranchiseSummary }) {
  const lead = franchise.titles.find((title) => title.id === franchise.id) ?? franchise.titles[0];
  const kinds = KINDS.filter((kind) => franchise.kinds[kind] > 0).map((kind) =>
    kindCount(kind, franchise.kinds[kind]),
  );
  const facts = [franchise.released?.slice(0, 4), ...kinds].filter(Boolean);

  return (
    <section
      aria-label={franchise.name}
      className="flex animate-fade-up flex-wrap items-center gap-6 rounded-24 border border-edge bg-glass p-6 shadow-panel"
    >
      {lead && (
        <Poster title={{ ...lead, hasPoster: franchise.hasPoster }} className="w-30 shrink-0" />
      )}
      <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex h-6.5 items-center rounded-full bg-accent px-2.5 font-extrabold text-12 text-on-accent">
            {/* A title alone in the library, come for what its franchise lacks, says what it is. */}
            {franchise.titles.length === 1 && lead ? kindWord(lead.kind) : "Franchise"}
          </span>
          {franchise.airing && <span className="text-12 text-accent-fg">Still airing</span>}
        </div>
        <h1 className="type-title">{franchise.name}</h1>
        <span className="text-14 text-fg-muted">{facts.join(" · ")}</span>
      </div>
      {franchise.aired > 0 && (
        <div className="flex flex-col items-center gap-1">
          <span className="font-extrabold text-36 tracking-[-0.02em]">
            {share(franchise.present, franchise.aired)}%
          </span>
          <span className="text-12 text-fg-muted">
            {franchise.present} of {franchise.aired} episodes
          </span>
        </div>
      )}
    </section>
  );
}
