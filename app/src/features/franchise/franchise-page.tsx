import { useState } from "react";
import { useParams } from "react-router";
import { Breadcrumb, LIBRARY } from "@/components/breadcrumb";
import { EngineProblem } from "@/components/engine-problem";
import { Poster } from "@/components/poster";
import { SortControl, sortWords } from "@/components/sort-control";
import { TitleCard } from "@/components/title-card";
import { type FranchiseSummary, type TitleKind, type TitleSort, useFranchise } from "@/lib/engine";
import { kindCount } from "@/lib/kinds";
import { share } from "@/lib/share";

/** A franchise: its series, films, OVAs and specials, oldest release first unless the owner picks
 * another order, each leading to its own page. */
export function FranchisePage() {
  const { id } = useParams();
  const [sort, setSort] = useState<TitleSort>("released");
  const franchise = useFranchise(Number(id), sort);

  if (!franchise.data) {
    return (
      <>
        <Breadcrumb trail={[LIBRARY]} current="…" />
        <EngineProblem queries={[franchise]} />
      </>
    );
  }
  const found = franchise.data;
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
              {found.titles.length} titles · {sortWords(sort)}
            </span>
          </div>
          <SortControl value={sort} onChange={setSort} />
        </div>
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-x-4.5 gap-y-5">
          {found.titles.map((title) => (
            <li key={title.id}>
              <TitleCard title={title} />
            </li>
          ))}
        </ul>
      </section>
    </>
  );
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
      className="flex animate-fade-up flex-wrap items-center gap-6 rounded-24 border border-edge bg-glass p-6"
    >
      {lead && (
        <Poster title={{ ...lead, hasPoster: franchise.hasPoster }} className="w-30 shrink-0" />
      )}
      <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex h-6.5 items-center rounded-full bg-accent px-2.5 font-extrabold text-12 text-on-accent">
            Franchise
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
