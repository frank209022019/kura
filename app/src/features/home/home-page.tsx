import { FolderPlus } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { EmptyState, ShelfIllustration } from "@/components/empty-state";
import { EngineProblem } from "@/components/engine-problem";
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
  useHealth,
  useLibrary,
  useScan,
  useScanAction,
  useSettings,
  useTmdb,
} from "@/lib/engine";
import { openDownloadsPage } from "@/lib/links";
import { useReadyUpdate } from "@/lib/updates";
import { Attention } from "./attention";
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
      <header className="page-top flex animate-fade-up flex-col gap-1.5">
        <h1 className="type-title">Library</h1>
        <p className="text-14 text-fg-muted">
          {empty
            ? "No folders yet."
            : library.data
              ? summary(library.data, franchises.data?.length)
              : "…"}
        </p>
      </header>

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
      {working && library.data && scan.data && !empty && (
        <Overview library={library.data} scan={scan.data} />
      )}

      <ThisCopy />
    </>
  );
}

/** What's in the library so far, by picture size, and how the latest scan went. */
function Overview({ library, scan }: { library: Library; scan: Scan }) {
  const navigate = useNavigate();
  const action = useScanAction();
  const add = useAddFolder();
  const [picking, setPicking] = useState(false);
  const scanning = scan.state === "running" || scan.state === "paused";
  const sizes = [
    { label: "SD", count: library.sd, note: "gets the AI model" },
    { label: "720p", count: library.hd720, note: "gets the fast upscale" },
    { label: "1080p", count: library.hd1080, note: "re-encoded or kept" },
    { label: "Larger", count: library.larger, note: "brought down to 1080p" },
  ];
  const most = Math.max(1, ...sizes.map((size) => size.count));

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
    <section
      aria-labelledby="overview-title"
      className="flex animate-fade-up flex-col gap-5 rounded-22 border border-edge bg-glass p-5 [animation-delay:60ms]"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="overview-title" className="font-extrabold text-16">
          Your videos by picture
        </h2>
        <div className="flex flex-wrap gap-2">
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
      </div>
      <ul className="flex flex-col gap-2.5">
        {sizes.map((size) => (
          <li
            key={size.label}
            className="grid grid-cols-[4.5rem_1fr_13.5rem] items-center gap-3 text-13"
          >
            <span className="font-bold">{size.label}</span>
            <span className="h-2 overflow-hidden rounded-4 bg-track" aria-hidden="true">
              <span
                className="block h-full animate-grow-x rounded-4 bg-accent"
                style={{ width: `${(size.count / most) * 100}%` }}
              />
            </span>
            <span className="text-fg-muted">
              <span className="font-mono text-fg">{size.count.toLocaleString("en-GB")}</span> ·{" "}
              {size.note}
            </span>
          </li>
        ))}
      </ul>
      {(library.problems > 0 || library.unread > 0) && (
        <p className="text-13 text-fg-muted">
          {library.problems > 0 &&
            `${library.problems.toLocaleString("en-GB")} ${library.problems === 1 ? "file" : "files"} couldn't be read. `}
          {library.unread > 0 &&
            `${library.unread.toLocaleString("en-GB")} still to read: the next scan reads them.`}
        </p>
      )}
      {(add.isError || action.isError) && (
        <p role="alert" className="text-13 text-broken-fg">
          {(add.error ?? action.error)?.message}
        </p>
      )}
    </section>
  );
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

/** Engine, data folder, database, lookups and updates at a glance. */
function ThisCopy() {
  const engine = useEngine();
  const health = useHealth();
  const tmdb = useTmdb();
  const update = useReadyUpdate();
  const navigate = useNavigate();

  const engineText = {
    starting: "Starting…",
    ready: health.data ? `Running · version ${health.data.version}` : "Running",
    failed: "Not running",
  }[engine.state];

  let updateText = "Checked in installed copies of Kura";
  if (import.meta.env.PROD) {
    if (update.isPending) updateText = "Checking…";
    else if (update.isError) updateText = `Can't check right now: ${String(update.error)}`;
    else if (update.data) updateText = `Kura ${update.data.version} is ready to install`;
    else updateText = "Up to date";
  }

  return (
    <section
      aria-labelledby="this-copy-title"
      className="flex animate-fade-up flex-col gap-3.5 rounded-22 border border-edge bg-glass p-5 [animation-delay:120ms]"
    >
      <h2 id="this-copy-title" className="font-extrabold text-16">
        This copy of Kura
      </h2>
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2.5 text-13">
        <dt className="text-fg-muted">Engine</dt>
        <dd className="flex items-center gap-2">
          {engine.state === "starting" && (
            <span className="size-2 animate-pulse rounded-full bg-accent" aria-hidden="true" />
          )}
          {engineText}
        </dd>
        <dt className="text-fg-muted">Data folder</dt>
        <dd className="font-mono text-12 text-fg-soft [overflow-wrap:anywhere]">
          {health.data?.dataDir ?? "…"}
        </dd>
        <dt className="text-fg-muted">Database</dt>
        <dd>{health.data ? `Ready · schema version ${health.data.schemaVersion}` : "…"}</dd>
        <dt className="text-fg-muted">Titles and artwork</dt>
        <dd>
          {tmdb.data?.connected && `TMDB connected · key ending ${tmdb.data.keyEnd}`}
          {tmdb.data && !tmdb.data.connected && (
            <>
              AniList only: no episode titles yet ·{" "}
              <button
                type="button"
                className="cursor-pointer text-accent-fg underline-offset-3 hover:text-accent-fg-hover hover:underline"
                onClick={() => void navigate("/setup?step=tools")}
              >
                Add your TMDB key
              </button>
            </>
          )}
          {!tmdb.data && "…"}
        </dd>
        <dt className="text-fg-muted">Updates</dt>
        <dd>{updateText}</dd>
        <dt className="text-fg-muted">Versions</dt>
        <dd>
          <button
            type="button"
            className="cursor-pointer text-accent-fg underline-offset-3 hover:text-accent-fg-hover hover:underline"
            onClick={() => void openDownloadsPage()}
          >
            Every version and what changed
          </button>
        </dd>
      </dl>
      <p className="text-12 text-fg-faint">
        Episode lists and artwork come from TMDB, anime details from AniList. This product uses the
        TMDB API but is not endorsed or certified by TMDB.
      </p>
    </section>
  );
}
