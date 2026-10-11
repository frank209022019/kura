import { SortControl, sortWords } from "@/components/sort-control";
import { ShelfCard } from "@/components/title-card";
import { type TitleSort, useFranchises } from "@/lib/engine";

/** Every franchise and series in the library as poster cards, oldest release first unless the
 * owner picks another order. A franchise of several titles is one card with a page of its own. */
export function Shelf({ sort, onSort }: { sort: TitleSort; onSort: (sort: TitleSort) => void }) {
  const franchises = useFranchises(sort);
  if (!franchises.data?.length) return null;
  const count = franchises.data.length;

  return (
    <section
      id="shelf"
      aria-labelledby="shelf-heading"
      className="flex animate-fade-up scroll-mt-6 flex-col gap-4 [animation-delay:90ms]"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <h2 id="shelf-heading" className="type-heading">
            Franchises and series
          </h2>
          <span className="text-13 text-fg-muted">
            {count} anime · {sortWords(sort)}
          </span>
        </div>
        <SortControl value={sort} onChange={onSort} />
      </div>
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-x-4.5 gap-y-5">
        {franchises.data.map((franchise) => (
          <li key={franchise.id}>
            <ShelfCard franchise={franchise} />
          </li>
        ))}
      </ul>
    </section>
  );
}
