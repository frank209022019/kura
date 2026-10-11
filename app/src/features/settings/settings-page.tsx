import { Check, Folder, Info, Lock } from "lucide-react";
import { useId, useState } from "react";
import { Navigate, NavLink, useParams } from "react-router";
import { EngineProblem } from "@/components/engine-problem";
import { StandardChoices } from "@/components/standard-choices";
import { TmdbKey } from "@/components/tmdb-key";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Switch } from "@/components/ui/switch";
import { pickFolder } from "@/lib/dialogs";
import {
  type DataSizes,
  type Settings,
  useAddFolder,
  useDataSizes,
  useExport,
  useFolders,
  useForgetFolder,
  useHealth,
  useSaveSettings,
  useSettings,
} from "@/lib/engine";
import { openFolder, showInFolder, useExplorer } from "@/lib/explorer";
import { size } from "@/lib/format";
import { openDownloadsPage } from "@/lib/links";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { key: "libraries", label: "Libraries" },
  { key: "standard", label: "Standard" },
  { key: "titles", label: "Titles and artwork" },
  { key: "data", label: "Your data" },
  { key: "updates", label: "Updates" },
  { key: "about", label: "About" },
] as const;

type Section = (typeof SECTIONS)[number]["key"];

/** Settings: everything chosen in setup, Kura's data, updates and what Kura is made of. */
export function SettingsPage() {
  const { section } = useParams();
  const folders = useFolders();
  const known = SECTIONS.find((each) => each.key === section);
  if (!known) return <Navigate to="/settings/libraries" replace />;
  return (
    <>
      <h1 className="type-title animate-fade-up">Settings</h1>
      <div className="flex flex-wrap items-start gap-5">
        <nav aria-label="Settings" className="flex flex-[0_1_220px] animate-fade-up flex-col gap-1">
          {SECTIONS.map(({ key, label }) => (
            <NavLink
              key={key}
              to={`/settings/${key}`}
              className={({ isActive }) =>
                cn(
                  "press flex min-h-11 items-center justify-between rounded-14 px-3.5 font-bold text-14",
                  isActive ? "bg-accent/12 text-accent-fg" : "text-fg-soft",
                )
              }
            >
              {label}
              {key === "libraries" && folders.data && (
                <span className="font-mono text-12 text-fg-muted">{folders.data.length}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-5">
          <Content section={known.key} />
        </div>
      </div>
    </>
  );
}

function Content({ section }: { section: Section }) {
  switch (section) {
    case "libraries":
      return <Libraries />;
    case "standard":
      return <Standard />;
    case "titles":
      return <Titles />;
    case "data":
      return <YourData />;
    case "updates":
      return <Updates />;
    case "about":
      return <About />;
  }
}

function Panel(props: {
  title: string;
  note?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  const id = useId();
  return (
    <section
      aria-labelledby={id}
      className={cn(
        "flex animate-fade-up flex-col gap-3.5 rounded-24 border border-edge bg-glass p-5.5",
        props.className,
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h2 id={id} className="font-extrabold text-18">
            {props.title}
          </h2>
          {props.note && <span className="text-13 text-fg-muted">{props.note}</span>}
        </div>
        {props.action}
      </div>
      {props.children}
    </section>
  );
}

function Libraries() {
  const folders = useFolders();
  const add = useAddFolder();
  const forget = useForgetFolder();
  const [picking, setPicking] = useState(false);

  async function addFolder() {
    setPicking(true);
    try {
      const path = await pickFolder("Choose a folder with anime in it");
      if (path) add.mutate({ path: "/folders", body: { path } });
    } finally {
      setPicking(false);
    }
  }

  return (
    <Panel
      title="Your anime folders"
      note="A folder can hold many anime in any layout. Kura only looks: forgetting a folder leaves its files as they are."
      action={
        <Button disabled={picking || add.isPending} onClick={() => void addFolder()}>
          <Folder size={16} aria-hidden="true" />
          Add a folder
        </Button>
      }
    >
      <EngineProblem queries={[folders]} />
      {add.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          {add.error.message}
        </p>
      )}
      <ul className="flex flex-col">
        {folders.data?.map((folder) => (
          <li
            key={folder.id}
            className="flex flex-wrap items-center gap-3 border-white/6 border-b py-3 last:border-b-0"
          >
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="font-mono text-13 [overflow-wrap:anywhere]">{folder.path}</span>
              <span
                className={cn("text-12", folder.available ? "text-fg-muted" : "text-broken-fg")}
              >
                {folder.available
                  ? `${folder.files} ${folder.files === 1 ? "video" : "videos"}`
                  : "Not connected: its files wait till the drive is back"}
              </span>
            </span>
            <Button
              size="sm"
              variant="ghost"
              disabled={forget.isPending}
              onClick={() => forget.mutate({ path: `/folders/${folder.id}` })}
            >
              Forget
            </Button>
          </li>
        ))}
      </ul>
      {folders.data?.length === 0 && (
        <p className="text-13 text-fg-muted">No folders yet. Add the one your anime is in.</p>
      )}
    </Panel>
  );
}

function Standard() {
  const stored = useSettings();
  const save = useSaveSettings();
  const settings = stored.data;
  if (!settings) return <EngineProblem queries={[stored]} />;
  return (
    <Panel
      title="Your standard"
      note="Every file is brought to this. Changing it changes what's left to convert; files converted already stay as they are."
    >
      <StandardChoices
        settings={settings}
        onChange={(part) => save.mutate({ path: "/settings", body: { ...settings, ...part } })}
      />
      {save.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          Kura couldn't save that: {save.error.message}
        </p>
      )}
    </Panel>
  );
}

function Titles() {
  return (
    <Panel
      title="Titles and artwork"
      note="Kura names each anime with AniList, and with a TMDB key also its seasons, episode titles and posters, as Plex shows them."
    >
      <TmdbKey />
      <p className="text-12 text-fg-faint">
        This product uses the TMDB API but is not endorsed or certified by TMDB. Anime details come
        from AniList.
      </p>
    </Panel>
  );
}

const PARTS: { key: keyof DataSizes; label: string; note: string; color: string }[] = [
  { key: "database", label: "Database", note: "kura.db, one SQLite file", color: "bg-accent" },
  { key: "artwork", label: "Artwork", note: "can be downloaded again", color: "bg-convert" },
  { key: "cache", label: "Cache", note: "can be asked for again", color: "bg-chart" },
  { key: "tools", label: "Tools", note: "ffmpeg", color: "bg-line-strong" },
  { key: "logs", label: "Logs", note: "kept 30 days", color: "bg-control" },
];

function YourData() {
  const sizes = useDataSizes();
  const stored = useSettings();
  const save = useSaveSettings();
  const explorer = useExplorer();
  const found = sizes.data;
  const settings = stored.data;
  return (
    <>
      <EngineProblem queries={[sizes, stored]} />
      {found && (
        <Panel
          title="Where your data lives"
          note={<span className="font-mono text-12 text-fg-soft">{found.folder}</span>}
          action={
            <Button onClick={() => explorer.run(() => openFolder(found.folder))}>
              Open folder
            </Button>
          }
        >
          {explorer.problem && (
            <p role="alert" className="text-13 text-broken-fg">
              {explorer.problem}
            </p>
          )}
          <Breakdown sizes={found} />
          <p className="text-13 text-fg-muted">
            The library, your matches, the undo journal, the queue and History all live in one
            database file. There's no server to install, nothing listens beyond this PC, and none of
            it is uploaded.
          </p>
        </Panel>
      )}
      {settings && (
        <Panel title="Kept with your files too">
          <Choice
            label="A gap report in each anime's folder"
            text="Kura - Gap analysis.md: what's missing, broken and left to convert"
            checked={settings.reports}
            onChange={(reports) =>
              save.mutate({ path: "/settings", body: { ...settings, reports } })
            }
          />
          <div className="flex items-center gap-3.5">
            <Lock size={16} aria-hidden="true" className="ml-3 shrink-0 text-fg-muted" />
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="font-extrabold text-14">
                A small tag inside every converted file
              </span>
              <span className="text-12 text-fg-muted">
                The standard and Kura's version. It's how a converted file is told apart.
              </span>
            </span>
            <span className="text-12 text-fg-muted">Always on</span>
          </div>
        </Panel>
      )}
      <div className="flex flex-wrap items-stretch gap-5">
        <ExportPanel />
        {found && settings && <Quarantine sizes={found} settings={settings} />}
      </div>
      <p className="flex items-start gap-2.5 rounded-20 border border-white/14 border-dashed px-5 py-4 text-13 text-fg-soft">
        <Info size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-fg-muted" />
        Uninstalling asks you to export first, and keeps this folder unless you choose to delete it.
        Your anime files are never touched.
      </p>
    </>
  );
}

function Breakdown({ sizes }: { sizes: DataSizes }) {
  const total = PARTS.reduce((sum, part) => sum + (sizes[part.key] as number), 0) || 1;
  return (
    <>
      <div aria-hidden="true" className="flex h-3 gap-0.5 overflow-hidden rounded-6 bg-track">
        {PARTS.map((part) => (
          <span
            key={part.key}
            className={cn("h-full animate-grow-x origin-left", part.color)}
            style={{ width: `${((sizes[part.key] as number) / total) * 100}%` }}
          />
        ))}
      </div>
      <dl className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-3">
        {PARTS.map((part) => (
          <div key={part.key} className="flex flex-col gap-0.5">
            <dt className="inline-flex items-center gap-1.5 text-12 text-fg-muted">
              <span aria-hidden="true" className={cn("size-2 rounded-2", part.color)} />
              {part.label}
            </dt>
            <dd className="font-extrabold text-14">{size(sizes[part.key] as number)}</dd>
            <dd className="font-mono text-11 text-fg-faint">{part.note}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

function Choice(props: {
  label: string;
  text: string;
  checked: boolean;
  onChange: (on: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="flex items-center gap-3.5">
      <Switch
        id={id}
        checked={props.checked}
        onCheckedChange={props.onChange}
        aria-describedby={`${id}-text`}
      />
      <span className="flex min-w-0 flex-col gap-0.5">
        <label htmlFor={id} className="cursor-pointer font-extrabold text-14">
          {props.label}
        </label>
        <span id={`${id}-text`} className="font-mono text-12 text-fg-muted">
          {props.text}
        </span>
      </span>
    </div>
  );
}

function ExportPanel() {
  const exporting = useExport();
  const explorer = useExplorer();
  const [picking, setPicking] = useState(false);

  async function exportEverything() {
    setPicking(true);
    try {
      const folder = await pickFolder("Where should the export go?");
      if (folder) exporting.mutate({ path: "/export", body: { folder } });
    } finally {
      setPicking(false);
    }
  }

  const done = exporting.data;
  return (
    <Panel
      title="Export"
      note="One zip with everything, in files you can open without Kura."
      className="flex-[1_1_380px] border-accent/35 bg-accent/5"
    >
      <ul className="flex flex-col gap-1.5 text-13">
        {[
          "The database, as SQLite",
          "Every file change, as CSV",
          "The library's videos, as CSV",
          "Your settings",
        ].map((item) => (
          <li key={item} className="flex items-center gap-2.5">
            <span aria-hidden="true" className="size-1.5 rounded-full bg-accent" />
            {item}
          </li>
        ))}
      </ul>
      {done && (
        <div className="flex flex-wrap items-center gap-2.5 rounded-14 bg-glass px-3.5 py-2.5 text-13">
          <Check size={16} aria-hidden="true" className="text-accent-fg" />
          <span className="min-w-0 flex-1 font-mono text-12 [overflow-wrap:anywhere]">
            {done.path} · {size(done.size)}
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => explorer.run(() => showInFolder(done.path))}
          >
            Show in folder
          </Button>
        </div>
      )}
      {(exporting.isError || explorer.problem) && (
        <p role="alert" className="text-13 text-broken-fg">
          {exporting.error?.message ?? explorer.problem}
        </p>
      )}
      <Button
        variant="primary"
        className="mt-auto self-start"
        disabled={picking || exporting.isPending}
        onClick={() => void exportEverything()}
      >
        {exporting.isPending ? "Exporting…" : "Export everything"}
      </Button>
    </Panel>
  );
}

const KEEP = [
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
  { value: "never", label: "Never" },
] as const;

function Quarantine({ sizes, settings }: { sizes: DataSizes; settings: Settings }) {
  const save = useSaveSettings();
  const bytes = sizes.quarantine.reduce((sum, each) => sum + each.bytes, 0);
  const files = sizes.quarantine.reduce((sum, each) => sum + each.files, 0);
  const keep = settings.quarantineDays === null ? "never" : String(settings.quarantineDays);
  return (
    <Panel
      title="Quarantine"
      note={
        files === 0
          ? "Nothing set aside now."
          : `${size(bytes)} in ${files} ${files === 1 ? "file" : "files"}: copies set aside and converted files' originals, each on its own drive.`
      }
      className="flex-[1_1_380px]"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-bold text-14">Keep them</span>
        <Segmented
          label="Keep what's set aside"
          value={keep as (typeof KEEP)[number]["value"]}
          options={KEEP}
          onChange={(value) =>
            save.mutate({
              path: "/settings",
              body: {
                ...settings,
                quarantineDays: value === "never" ? null : (Number(value) as 7 | 30 | 90),
              },
            })
          }
        />
      </div>
      <ul className="flex flex-col gap-1">
        {sizes.quarantine.map((each) => (
          <li key={each.folder} className="font-mono text-12 text-fg-muted">
            {each.folder} · {size(each.bytes)}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function Updates() {
  const health = useHealth();
  return (
    <Panel
      title="Updates"
      note="Kura looks for a new version once a day and downloads it in the background. When one is ready, it shows what's new and asks before restarting."
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-14">
          This is Kura <span className="font-mono">{health.data?.version ?? "…"}</span>
        </span>
        <Button onClick={() => void openDownloadsPage()}>Every version</Button>
      </div>
    </Panel>
  );
}

function About() {
  const health = useHealth();
  return (
    <Panel title="About Kura" note="蔵, a storehouse: a personal tool for one anime library.">
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-13">
        <dt className="text-fg-muted">Version</dt>
        <dd className="font-mono">{health.data?.version ?? "…"}</dd>
        <dt className="text-fg-muted">Data</dt>
        <dd className="font-mono [overflow-wrap:anywhere]">{health.data?.dataDir ?? "…"}</dd>
        <dt className="text-fg-muted">Licence</dt>
        <dd>MIT. Anyone may fork it; the repo takes no contributions.</dd>
      </dl>
      <p className="text-13 text-fg-muted">
        Kura stands on others' work: ffmpeg reads and converts the videos, Real-ESRGAN's anime model
        and Anime4K's shaders upscale them, AniList and TMDB say what each one is.
        THIRD-PARTY-NOTICES.txt, next to Kura, lists every part with its licence.
      </p>
    </Panel>
  );
}
