import { SortControl } from "@/components/sort-control";
import { ShelfCard } from "@/components/title-card";
import {
  CardGrid,
  groupsByType,
  orderWords,
  shelfByKind,
  together,
} from "@/components/title-groups";
import { type TitleSort, useFranchises } from "@/lib/engine";

/** Every franchise and series in the library as poster cards, by type (franchises, then series,
 * films, OVAs and specials on their own) and oldest release first, unless the owner picks another
 * order. A franchise of several titles is one card with a page of its own. */
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
            {count} anime · {orderWords(sort)}
          </span>
        </div>
        <SortControl value={sort} onChange={onSort} />
      </div>
      <CardGrid
        groups={groupsByType(sort) ? shelfByKind(franchises.data) : together(franchises.data)}
        keyOf={(franchise) => franchise.id}
        card={(franchise) => <ShelfCard franchise={franchise} />}
      />
    </section>
  );
}
