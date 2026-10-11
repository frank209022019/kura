import { Link } from "react-router";
import { Poster } from "@/components/poster";
import { SortControl } from "@/components/sort-control";
import { StatusShape } from "@/components/status";
import { type TitleSort, type TitleSummary, useTitles } from "@/lib/engine";
import { files, kindWord } from "@/lib/kinds";

/** Every anime and film in the library as poster cards, oldest release first unless the owner
 * picks another order. */
export function TitlesGrid({
  sort,
  onSort,
}: {
  sort: TitleSort;
  onSort: (sort: TitleSort) => void;
}) {
  const titles = useTitles(sort);
  if (!titles.data?.length) return null;
  const count = titles.data.length;

  return (
    <section
      id="titles"
      aria-labelledby="titles-heading"
      className="flex animate-fade-up scroll-mt-6 flex-col gap-4 [animation-delay:90ms]"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <h2 id="titles-heading" className="type-heading">
            Anime and films
          </h2>
          <span className="text-13 text-fg-muted">
            {count} {count === 1 ? "title" : "titles"} · {order(sort)}
          </span>
        </div>
        <SortControl value={sort} onChange={onSort} />
      </div>
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-x-4.5 gap-y-5">
        {titles.data.map((title) => (
          <li key={title.id}>
            <TitleCard title={title} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function TitleCard({ title }: { title: TitleSummary }) {
  const tag = tagOf(title);
  return (
    <Link
      to={`/titles/${title.id}`}
      className="lift flex flex-col gap-2 rounded-16 focus-visible:outline-2"
    >
      <div className="relative">
        <Poster title={title} />
        {tag && (
          <span className="absolute top-2 left-2 inline-flex h-6 items-center gap-1.5 rounded-full bg-window/85 px-2.5 font-bold text-11">
            {tag.state && <StatusShape state={tag.state} className="size-2" />}
            {tag.text}
          </span>
        )}
      </div>
      <span className="flex flex-col gap-px px-0.5">
        <span className="truncate font-bold text-14">{title.name}</span>
        <span className="text-12 text-fg-muted">{facts(title)}</span>
        {title.aired > 0 && (
          <span className="font-mono text-11 text-fg-faint">
            {title.present} of {title.aired}
            {title.missing === 0
              ? " · complete"
              : ` · ${Math.floor((title.present / title.aired) * 100)}%`}
          </span>
        )}
      </span>
    </Link>
  );
}

/** The card's tag: what most needs saying, by its status shape. */
function tagOf(title: TitleSummary): { text: string; state: "missing" | "ready" | null } | null {
  if (title.missing > 0) return { text: `${title.missing} missing`, state: "missing" };
  if (title.airing) return { text: "Airing", state: null };
  if (title.aired > 0) return { text: "Complete", state: "ready" };
  return null;
}

/** "TV series · 1989 · 291 episodes", "Movie · 2001", "OVA · 1992 · 2 files". */
function facts(title: TitleSummary): string {
  const parts = [kindWord(title.kind)];
  if (title.year) parts.push(String(title.year));
  if (title.kind !== "movie") {
    parts.push(title.aired > 0 ? `${title.aired} episodes` : files(title.files));
  }
  return parts.join(" · ");
}

function order(sort: TitleSort): string {
  switch (sort) {
    case "released":
      return "oldest release first";
    case "name":
      return "by name";
    case "added":
      return "newest added first";
    case "missing":
      return "most missing first";
  }
}
