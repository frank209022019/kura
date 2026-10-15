import { NoMatches, SearchField } from "@/components/search-field";
import { CardsSkeleton, ListHeadSkeleton, Loading } from "@/components/skeleton";
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
import { matches } from "@/lib/search";

/** Every franchise and series in the library as poster cards, by type (franchises, then series,
 * films, OVAs and specials on their own) and oldest release first, unless the owner picks another
 * order. A franchise of several titles is one card with a page of its own. The search finds a
 * franchise by its name or any of its titles'. */
export function Shelf(props: {
  sort: TitleSort;
  onSort: (sort: TitleSort) => void;
  query: string;
  onQuery: (query: string) => void;
}) {
  const { sort, query } = props;
  const franchises = useFranchises(sort);
  if (!franchises.data) {
    return (
      <Loading label="Loading the shelf" queries={[franchises]}>
        <div className="flex flex-col gap-4">
          <ListHeadSkeleton />
          <CardsSkeleton count={12} />
        </div>
      </Loading>
    );
  }
  if (franchises.data.length === 0) return null;
  const count = franchises.data.length;
  const found = franchises.data.filter((franchise) =>
    matches(query, franchise.name, ...franchise.titles.map((title) => title.name)),
  );

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
            {query ? `${found.length} of ${count}` : count} anime · {orderWords(sort)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {(count > 1 || query) && (
            <SearchField
              value={query}
              onChange={props.onQuery}
              label="Search the shelf"
              placeholder={`Search ${count} anime`}
              className="w-64"
            />
          )}
          <SortControl value={sort} onChange={props.onSort} />
        </div>
      </div>
      {found.length === 0 ? (
        <NoMatches>No anime on the shelf goes by “{query.trim()}”.</NoMatches>
      ) : (
        <CardGrid
          groups={groupsByType(sort) ? shelfByKind(found) : together(found)}
          keyOf={(franchise) => franchise.id}
          card={(franchise) => <ShelfCard franchise={franchise} />}
        />
      )}
    </section>
  );
}
