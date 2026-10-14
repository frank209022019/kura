import { FolderPlus } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { EmptyState, ShelfIllustration } from "@/components/empty-state";
import { EngineProblem } from "@/components/engine-problem";
import { Loading, TilesSkeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { pickFolder } from "@/lib/dialogs";
import {
  type Library,
  type Scan,
  type TitleSort,
  useAddFolder,
  useEngine,
  useFolders,
  useFranchises,
  useLibrary,
  useScan,
  useScanAction,
  useSettings,
} from "@/lib/engine";
import { dayAndTime, scanChanges } from "@/lib/format";
import { Attention } from "./attention";
import { Recovered } from "./recovered";
import { Shelf } from "./shelf";

export function HomePage() {
  const engine = useEngine();
  const settings = useSettings();
  const folders = useFolders();
  const library = useLibrary();
  const scan = useScan();
  const franchises = useFranchises();
  const navigate = useNavigate();
  const [sort, setSort] = useState<TitleSort>("released");

  const empty = folders.data?.length === 0;
  if (empty && settings.data && !settings.data.setUp) return <Navigate to="/setup" replace />;
  const working = engine.state !== "failed";
  const missing = (franchises.data ?? []).filter((franchise) => franchise.missing > 0);

  return (
    <>
      <header className="page-top flex animate-fade-up flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-1.5">
          <h1 className="type-title">Library</h1>
          <p className="text-14 text-fg-muted">
            {empty
              ? "No folders yet."
              : library.data
                ? summary(library.data, franchises.data?.length)
                : "…"}
          </p>
        </div>
        {working && scan.data && !empty && <ScanButtons scan={scan.data} />}
      </header>

      <Recovered />
      <EngineProblem queries={[settings, folders, library, scan]} />
      {engine.state !== "failed" && empty && (
        <EmptyState
          title="Your shelf is empty"
          illustration={<ShelfIllustration />}
          action={
            <Button variant="primary" onClick={() => void navigate("/setup?step=folders")}>
              Add a folder
            </Button>
          }
        >
          Add a folder with anime in it. Any layout, even everything in one folder.
        </EmptyState>
      )}
      {working && !empty && !library.data && (
        <Loading label="Loading your library" queries={[settings, folders, library, scan]}>
          <TilesSkeleton count={4} />
        </Loading>
      )}
      {working && library.data && !empty && <Pictures library={library.data} />}
      {working && scan.data && library.data && !empty && (
        <Attention
          waiting={scan.data.waiting}
          missing={missing.reduce((total, franchise) => total + franchise.missing, 0)}
          missingIn={missing.length}
          broken={library.data.problems}
          mixed={scan.data.mixed}
          onMatch={() => void navigate("/match")}
          onMissing={() => {
            setSort("missing");
            document.getElementById("shelf")?.scrollIntoView({ behavior: "smooth" });
          }}
        />
      )}
      {working && !empty && <Shelf sort={sort} onSort={setSort} />}
    </>
  );
}

/** Scanning again and adding a folder, by the page's title, with when the latest scan ran and
 * what it found new or gone. */
function ScanButtons({ scan }: { scan: Scan }) {
  const navigate = useNavigate();
  const action = useScanAction();
  const add = useAddFolder();
  const [picking, setPicking] = useState(false);
  const scanning = scan.state === "running" || scan.state === "paused";

  const rescan = () =>
    action.mutate({ path: "/scan" }, { onSuccess: () => void navigate("/scan") });

  async function addFolder() {
    setPicking(true);
    try {
      const path = await pickFolder("Choose a folder with anime in it");
      if (path) add.mutate({ path: "/folders", body: { path } }, { onSuccess: rescan });
    } finally {
      setPicking(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1.5">
      <div className="flex flex-wrap justify-end gap-2">
        {scanning ? (
          <Button size="sm" variant="primary" onClick={() => void navigate("/scan")}>
            {scan.state === "running" ? "Scanning… see progress" : "Scan paused: see it"}
          </Button>
        ) : (
          <Button size="sm" disabled={action.isPending} onClick={rescan}>
            Scan again
          </Button>
        )}
        {/* Adding a folder starts a scan, and one can't start while another runs. */}
        {scan.state !== "running" && (
          <Button
            size="sm"
            variant="ghost"
            disabled={picking || add.isPending}
            onClick={() => void addFolder()}
          >
            <FolderPlus size={15} aria-hidden="true" />
            Add a folder
          </Button>
        )}
      </div>
      {scan.state === "done" && scan.finishedAt && (
        <span className="text-12 text-fg-muted">
          Scanned {dayAndTime(new Date(scan.finishedAt))}
          {scan.added !== null && scan.gone !== null && ` · ${scanChanges(scan.added, scan.gone)}`}
        </span>
      )}
      {(add.isError || action.isError) && (
        <p role="alert" className="text-13 text-broken-fg">
          {(add.error ?? action.error)?.message}
        </p>
      )}
    </div>
  );
}

/** What's in the library, by picture size: the summary at the top of Home. Each size says what
 * converting does to it. */
function Pictures({ library }: { library: Library }) {
  const sizes = [
    { label: "SD", count: library.sd, note: "gets the AI model" },
    { label: "720p", count: library.hd720, note: "gets the fast upscale" },
    { label: "1080p", count: library.hd1080, note: "re-encoded or kept" },
    { label: "Larger", count: library.larger, note: "brought down to 1080p" },
  ];
  const parts = shares(sizes.map((size) => size.count));
  return (
    <section
      aria-labelledby="pictures-title"
      className="flex animate-fade-up flex-col gap-2.5 [animation-delay:60ms]"
    >
      <h2 id="pictures-title" className="font-bold text-13 text-fg-muted">
        Your videos by picture
      </h2>
      <ul className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-2.5">
        {sizes.map((size, at) => {
          const share = parts[at] ?? 0;
          return (
            <li
              key={size.label}
              className="flex flex-col gap-1.5 rounded-16 border border-edge bg-glass px-4 py-3.5 shadow-panel"
            >
              <span className="flex items-baseline justify-between gap-2">
                <span className="font-bold text-13">{size.label}</span>
                <span className="font-mono text-12 text-fg-muted">{share}%</span>
              </span>
              <span className="font-extrabold text-24 leading-[1.1]">
                {size.count.toLocaleString("en-GB")}
              </span>
              <span className="h-1.5 overflow-hidden rounded-3 bg-track" aria-hidden="true">
                <span
                  className="block h-full animate-grow-x rounded-3 bg-accent"
                  style={{ width: `${share}%` }}
                />
              </span>
              <span className="text-12 text-fg-muted">{size.note}</span>
            </li>
          );
        })}
      </ul>
      {(library.problems > 0 || library.unread > 0) && (
        <p className="text-13 text-fg-muted">
          {library.problems > 0 &&
            `${library.problems.toLocaleString("en-GB")} ${library.problems === 1 ? "file" : "files"} couldn't be read. `}
          {library.unread > 0 &&
            `${library.unread.toLocaleString("en-GB")} still to read: the next scan reads them.`}
        </p>
      )}
    </section>
  );
}

/** Each count's share of them all in whole percents that add up to 100 (the largest
 * remainders rounded up), or every share 0 when there's nothing. */
function shares(counts: number[]): number[] {
  const all = counts.reduce((sum, count) => sum + count, 0);
  if (all === 0) return counts.map(() => 0);
  const exact = counts.map((count) => (count / all) * 100);
  const whole = exact.map(Math.floor);
  const short = 100 - whole.reduce((sum, part) => sum + part, 0);
  const order = exact
    .map((share, at) => ({ at, rest: share - Math.floor(share) }))
    .sort((a, b) => b.rest - a.rest);
  for (const { at } of order.slice(0, short)) whole[at] = (whole[at] ?? 0) + 1;
  return whole;
}

function summary(library: Library, titles: number | undefined): string {
  const anime = titles ? `${titles.toLocaleString("en-GB")} anime · ` : "";
  const videos = `${anime}${library.files.toLocaleString("en-GB")} ${library.files === 1 ? "video" : "videos"}`;
  const size =
    library.size >= 1e12
      ? `${(library.size / 1e12).toFixed(1)} TB`
      : `${(library.size / 1e9).toFixed(1)} GB`;
  const folders = `${library.folders} ${library.folders === 1 ? "folder" : "folders"}`;
  return `${videos} · ${size} · ${folders}`;
}
