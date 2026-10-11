import { Check, Cpu, Database, Folder, SlidersHorizontal, X } from "lucide-react";
import { RadioGroup } from "radix-ui";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { TitleBar } from "@/components/shell/title-bar";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Switch } from "@/components/ui/switch";
import { pickFolder } from "@/lib/dialogs";
import {
  type Settings,
  type Tool,
  useAddFolder,
  useDownloadTool,
  useFolders,
  useForgetFolder,
  useHealth,
  useSaveSettings,
  useScanAction,
  useSettings,
  useSystem,
  useTools,
} from "@/lib/engine";
import { cn } from "@/lib/utils";

const STEPS = [
  { id: "data", label: "Your data" },
  { id: "folders", label: "Your folders" },
  { id: "standard", label: "Your standard" },
  { id: "tools", label: "Tools" },
] as const;

type Step = (typeof STEPS)[number]["id"];

const isStep = (value: string | null): value is Step => STEPS.some((step) => step.id === value);

/** First run: where the data lives, the anime folders, the standard, and the tools. */
export function SetupPage() {
  const [params] = useSearchParams();
  const asked = params.get("step");
  const [step, setStep] = useState<Step>(isStep(asked) ? asked : "data");
  const current = STEPS.findIndex((each) => each.id === step);
  const go = (to: Step) => setStep(to);

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <TitleBar title="Kura setup" />
      <div className="flex-1 overflow-y-auto">
        <main className="mx-auto flex w-full max-w-250 flex-col gap-7 px-6 pt-6 pb-16">
          <header className="flex animate-fade-up flex-col gap-2">
            <span className="type-eyebrow">First run</span>
            <h1 className="font-extrabold text-44 leading-[1.05] tracking-[-0.03em]">
              Welcome to Kura
            </h1>
            <p className="max-w-170 text-17 text-fg-muted">
              Four quick steps. You can change any of them later in Settings, and nothing in your
              folders changes until you review it.
            </p>
          </header>

          <Stepper current={current} />

          {STEPS.map((each, index) => {
            if (index < current) return <Done key={each.id} step={each.id} onChange={go} />;
            if (index > current) return <Upcoming key={each.id} step={each.id} />;
            return <Current key={each.id} step={each.id} go={go} />;
          })}

          <p className="text-13 text-fg-faint">
            Kura never uploads your files. It only goes online to look up titles and artwork, to
            fetch its tools, and to check for updates.
          </p>
        </main>
      </div>
    </div>
  );
}

function Stepper({ current }: { current: number }) {
  return (
    <ol
      aria-label="Setup steps"
      className="flex animate-fade-up flex-wrap items-center gap-2.5 font-bold text-13"
    >
      {STEPS.map((step, index) => (
        <li key={step.id} className="contents">
          {index > 0 && (
            <span
              aria-hidden="true"
              className={cn("h-0.5 w-7 rounded-2", index <= current ? "bg-accent" : "bg-line")}
            />
          )}
          <span
            aria-current={index === current ? "step" : undefined}
            className={cn(
              "inline-flex items-center gap-2",
              index === current && "text-accent-fg",
              index > current && "text-fg-faint",
            )}
          >
            <span
              className={cn(
                "inline-flex size-6.5 items-center justify-center rounded-full text-12",
                index < current && "bg-accent text-on-accent",
                index === current && "border-2 border-accent",
                index > current && "border-2 border-line-strong",
              )}
            >
              {index < current ? (
                <Check size={13} strokeWidth={3.4} aria-label="Done:" />
              ) : (
                index + 1
              )}
            </span>
            {step.label}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** A finished step, folded into one line. */
function Done({ step, onChange }: { step: Step; onChange: (step: Step) => void }) {
  const health = useHealth();
  const folders = useFolders();
  const settings = useSettings();

  switch (step) {
    case "data":
      return (
        <Row icon={<Database size={18} />} title="Where Kura keeps its data">
          <span className="font-mono text-12">{health.data?.dataDir ?? "…"}</span>
          <span className="text-13 text-fg-muted">
            One database file, artwork, backups and logs. Your anime files never go here.
          </span>
        </Row>
      );
    case "folders":
      return (
        <Row
          icon={<Folder size={18} />}
          title="Your anime folders"
          action={
            <Button size="sm" onClick={() => onChange("folders")}>
              Change
            </Button>
          }
        >
          <span className="flex flex-wrap gap-2">
            {folders.data?.map((folder) => (
              <FolderChip key={folder.id} path={folder.path} />
            ))}
          </span>
          <span className="text-13 text-fg-muted">
            A folder can hold many anime in any layout, even mixed together. Kura works out what is
            what.
          </span>
        </Row>
      );
    case "standard":
      return (
        <Row
          icon={<SlidersHorizontal size={18} />}
          title="Your standard"
          action={
            <Button size="sm" onClick={() => onChange("standard")}>
              Change
            </Button>
          }
        >
          <span className="text-13 text-fg-muted">
            {settings.data ? describe(settings.data) : "…"}
          </span>
        </Row>
      );
    case "tools":
      return null; // the last step: finishing it starts the scan
  }
}

/** A step still to come, as a dashed line. */
function Upcoming({ step }: { step: Step }) {
  const system = useSystem();
  const tools = useTools();
  const size = (tools.data ?? []).reduce((total, tool) => total + tool.size, 0);

  if (step === "folders") {
    return (
      <Row dashed title="Your folders" icon={<Folder size={18} />}>
        <span className="text-13">The folders your anime is in, in any layout.</span>
      </Row>
    );
  }
  if (step !== "tools") {
    return (
      <Row dashed title="Your standard" icon={<SlidersHorizontal size={18} />}>
        <span className="text-13">The size and format every file is brought to, and its name.</span>
      </Row>
    );
  }
  return (
    <Row
      dashed
      icon={<Cpu size={18} />}
      title="Tools"
      action={system.data?.graphicsCard && <CardFound name={system.data.graphicsCard} />}
    >
      <span className="text-13">
        ffmpeg{size ? `, about ${megabytes(size)}` : ""}, plus a quick graphics card check.
      </span>
    </Row>
  );
}

function Current({ step, go }: { step: Step; go: (step: Step) => void }) {
  switch (step) {
    case "data":
      return <DataStep onContinue={() => go("folders")} />;
    case "folders":
      return <FoldersStep onBack={() => go("data")} onContinue={() => go("standard")} />;
    case "standard":
      return <StandardStep onBack={() => go("folders")} onContinue={() => go("tools")} />;
    case "tools":
      return <ToolsStep onBack={() => go("standard")} />;
  }
}

function DataStep({ onContinue }: { onContinue: () => void }) {
  const health = useHealth();

  return (
    <Panel title="Where Kura keeps its data" labelledBy="data-title">
      <p className="text-14 text-fg-muted">
        One database file, artwork, backups and logs, in one folder on this PC. Your anime files
        never go here.
      </p>
      <p className="w-fit rounded-14 bg-white/6 px-3.5 py-2 font-mono text-13">
        {health.data?.dataDir ?? "…"}
      </p>
      <Footer note="Uninstalling offers to export it first, and keeps it unless you choose otherwise.">
        <Button variant="primary" onClick={onContinue}>
          Continue
        </Button>
      </Footer>
    </Panel>
  );
}

function FoldersStep({ onBack, onContinue }: { onBack: () => void; onContinue: () => void }) {
  const folders = useFolders();
  const add = useAddFolder();
  const forget = useForgetFolder();
  const [picking, setPicking] = useState(false);
  const none = !folders.data?.length;

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
    <Panel title="Your anime folders" labelledBy="folders-title">
      <p className="text-14 text-fg-muted">
        A folder can hold many anime in any layout, even mixed together. Kura works out what is
        what. Nothing in them changes: Kura only looks.
      </p>
      {folders.data && folders.data.length > 0 && (
        <ul aria-label="Folders in your library" className="flex flex-wrap gap-2">
          {folders.data.map((folder) => (
            <li key={folder.id}>
              <FolderChip
                path={folder.path}
                onRemove={() => forget.mutate({ path: `/folders/${folder.id}` })}
              />
            </li>
          ))}
        </ul>
      )}
      <div>
        <Button
          variant={none ? "primary" : "secondary"}
          disabled={picking || add.isPending}
          onClick={() => void addFolder()}
        >
          <Folder size={16} aria-hidden="true" />
          Add a folder
        </Button>
      </div>
      {add.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          {add.error.message}
        </p>
      )}
      <Footer note="Add as many as you like. Later scans only read what's new.">
        <Button onClick={onBack}>Back</Button>
        <Button variant={none ? "secondary" : "primary"} disabled={none} onClick={onContinue}>
          Continue
        </Button>
      </Footer>
    </Panel>
  );
}

const STANDARDS = [
  {
    value: "cinema-1080",
    name: "Cinema 1080p",
    recommended: true,
    spec: "1080p · HEVC 10-bit · MKV",
    text: "Original audio kept, lossless tracks become AAC. Subtitles and fonts kept.",
    size: "≈ 450 MB per episode",
  },
  {
    value: "compact-720",
    name: "Compact 720p",
    recommended: false,
    spec: "720p · HEVC 10-bit · MKV",
    text: "Same audio and subtitle rules. Still crisp on a laptop screen, about half the size.",
    size: "≈ 250 MB per episode",
  },
] as const;

const NAMING = [
  { value: "plex", label: "Plex" },
  { value: "jellyfin", label: "Jellyfin" },
  { value: "keep", label: "Keep my names" },
] as const;

const EXAMPLES = [
  {
    from: "[Group] DBZ - 001 [480p].mkv",
    folder: "TV\\Dragon Ball Z (1989)\\Season 01\\",
    name: "Dragon Ball Z (1989) - S01E01 - The New Threat.mkv",
  },
  {
    from: "Broly the Legendary Super Saiyan.avi",
    folder: "Movies\\Dragon Ball Z - Broly - The Legendary Super Saiyan (1993)\\",
    name: "Dragon Ball Z - Broly - The Legendary Super Saiyan (1993).avi",
  },
];

function StandardStep({ onBack, onContinue }: { onBack: () => void; onContinue: () => void }) {
  const stored = useSettings();
  const save = useSaveSettings();
  const [draft, setDraft] = useState<Settings | null>(null);
  const settings = draft ?? stored.data;

  if (!settings) return <Panel title="Choose your standard" labelledBy="standard-title" />;
  // From the latest draft, so two quick changes in a row both count.
  const change = (part: Partial<Settings>) =>
    setDraft((latest) => ({ ...(latest ?? settings), ...part }));

  return (
    <Panel
      title="Choose your standard"
      labelledBy="standard-title"
      intro="Every file in the library is brought to this, even ones already at the right size. Files that already match are only renamed."
    >
      <RadioGroup.Root
        aria-label="Standard"
        value={settings.standard}
        onValueChange={(value) => change({ standard: value as Settings["standard"] })}
        className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-3"
      >
        {STANDARDS.map((standard) => (
          <RadioGroup.Item
            key={standard.value}
            value={standard.value}
            className="press group flex cursor-pointer flex-col gap-2.5 rounded-18 border-2 border-edge bg-glass p-4.5 text-left data-[state=checked]:border-accent data-[state=checked]:bg-accent/10"
          >
            <span className="flex w-full items-center justify-between gap-2">
              <span className="font-extrabold text-17">{standard.name}</span>
              <RadioRing />
            </span>
            {standard.recommended && (
              <span className="inline-flex h-5.5 w-fit items-center rounded-full bg-accent px-2 font-extrabold text-11 text-on-accent">
                Recommended
              </span>
            )}
            <span className="text-13 text-fg-soft">{standard.spec}</span>
            <span className="text-13 text-fg-muted">{standard.text}</span>
            <span className="font-mono text-12 text-fg-muted group-data-[state=checked]:text-accent-fg">
              {standard.size}
            </span>
          </RadioGroup.Item>
        ))}
        <div
          aria-disabled="true"
          className="flex flex-col gap-2.5 rounded-18 border-2 border-edge border-dashed p-4.5 text-fg-muted"
        >
          <span className="font-extrabold text-17 text-fg-soft">Custom</span>
          <span className="text-13">Pick every detail yourself</span>
          <span className="text-13">
            Resolution, codec and quality, which audio languages to keep, subtitle handling.
          </span>
          <span className="font-mono text-12">Arrives with conversion</span>
        </div>
      </RadioGroup.Root>

      <div className="flex flex-col gap-2.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="font-extrabold text-15">Name files for</span>
          <Segmented
            label="Name files for"
            value={settings.naming}
            options={NAMING}
            onChange={(naming) => change({ naming })}
          />
        </div>
        <NamePreview keep={settings.naming === "keep"} />
      </div>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3">
        <Toggle
          label="Upscale SD with AI"
          text="480p and 576p sources get the best quality model."
          checked={settings.upscaleSd}
          onChange={(upscaleSd) => change({ upscaleSd })}
        />
        <Toggle
          label="Fast upscale for 720p"
          text="A quicker model where the gain is smaller."
          checked={settings.upscale720}
          onChange={(upscale720) => change({ upscale720 })}
        />
      </div>

      {save.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          Kura couldn't save your choices: {save.error.message}
        </p>
      )}
      <Footer note="You can change the standard any time. Kura then shows what would be redone before doing it.">
        <Button onClick={onBack}>Back</Button>
        <Button
          variant="primary"
          disabled={save.isPending}
          onClick={() =>
            save.mutate({ path: "/settings", body: settings }, { onSuccess: onContinue })
          }
        >
          Continue
        </Button>
      </Footer>
    </Panel>
  );
}

function NamePreview({ keep }: { keep: boolean }) {
  return (
    <div className="flex flex-col gap-3 overflow-x-auto rounded-16 bg-inset px-4 py-3.5 font-mono text-12">
      {EXAMPLES.map((example) => (
        <div key={example.from} className="flex flex-col gap-1 whitespace-nowrap">
          <span className="text-fg-faint">{example.from}</span>
          <span className="text-fg">
            → {example.folder}
            {keep ? example.from : example.name}
          </span>
        </div>
      ))}
      {keep && (
        <span className="font-sans text-12 text-fg-muted">
          Files keep their names, and still go into a folder per show, season and movie.
        </span>
      )}
    </div>
  );
}

function ToolsStep({ onBack }: { onBack: () => void }) {
  const tools = useTools();
  const system = useSystem();
  const stored = useSettings();
  const save = useSaveSettings();
  const scan = useScanAction();
  const navigate = useNavigate();
  const ready = tools.data?.every((tool) => tool.state === "ready") ?? false;

  function startScan() {
    if (!stored.data) return;
    save.mutate(
      { path: "/settings", body: { ...stored.data, setUp: true } },
      {
        onSuccess: () =>
          scan.mutate({ path: "/scan" }, { onSuccess: () => void navigate("/scan") }),
      },
    );
  }

  return (
    <Panel
      title="Tools"
      labelledBy="tools-title"
      intro="Kura fetches these once, checks each one against the list it ships with, and keeps them in its data folder."
    >
      <ul className="flex flex-col gap-3">
        {tools.data?.map((tool) => (
          <li key={tool.id}>
            <ToolRow tool={tool} />
          </li>
        ))}
      </ul>
      <p className="flex items-center gap-2.5 text-13 text-fg-soft">
        <Cpu size={16} aria-hidden="true" className="text-fg-muted" />
        {system.isPending && "Checking the graphics card…"}
        {system.data &&
          (system.data.graphicsCard ? (
            <>
              Graphics card: <strong>{system.data.graphicsCard}</strong>
            </>
          ) : (
            "Kura couldn't find a graphics card. Scanning works; converting will be slow."
          ))}
      </p>
      {(save.isError || scan.isError) && (
        <p role="alert" className="text-13 text-broken-fg">
          The scan didn't start: {(save.error ?? scan.error)?.message}
        </p>
      )}
      <Footer note="The first scan only looks: nothing is renamed or moved.">
        <Button onClick={onBack}>Back</Button>
        <Button
          variant="primary"
          disabled={!ready || save.isPending || scan.isPending}
          onClick={startScan}
        >
          Start the first scan
        </Button>
      </Footer>
    </Panel>
  );
}

function ToolRow({ tool }: { tool: Tool }) {
  const download = useDownloadTool();
  const busy = tool.state === "downloading" || tool.state === "unpacking";
  const percent = tool.size ? Math.round((tool.done / tool.size) * 100) : 0;

  return (
    <div className="flex flex-col gap-3 rounded-16 border border-edge bg-glass px-4 py-3.5">
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-0.5">
          <span className="font-extrabold text-15">
            {tool.name} <span className="font-normal text-fg-muted">{tool.version}</span>
          </span>
          <span className="text-13 text-fg-muted">{tool.purpose}</span>
          <span className="font-mono text-11 text-fg-faint">
            {megabytes(tool.size)} · {tool.licence}
          </span>
        </div>
        {tool.state === "ready" && (
          <span className="inline-flex items-center gap-2 font-bold text-13 text-accent-fg">
            <Check size={16} strokeWidth={3} aria-hidden="true" />
            Ready
          </span>
        )}
        {(tool.state === "missing" || tool.state === "failed") && (
          <Button
            variant={tool.state === "missing" ? "primary" : "secondary"}
            disabled={download.isPending}
            onClick={() => download.mutate({ path: `/tools/${tool.id}/download` })}
          >
            {tool.state === "missing" ? "Download" : "Try again"}
          </Button>
        )}
        {busy && (
          <span className="font-mono text-12 text-fg-muted">
            {tool.state === "unpacking" ? "Unpacking…" : `${percent}%`}
          </span>
        )}
      </div>
      {busy && (
        <div
          role="progressbar"
          aria-label={`Downloading ${tool.name}`}
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          className="h-1.5 overflow-hidden rounded-3 bg-track"
        >
          <div
            className="h-full rounded-3 bg-accent transition-[width] duration-320 ease-cinema"
            style={{ width: `${percent}%` }}
          />
        </div>
      )}
      {tool.state === "failed" && tool.problem && (
        <p role="alert" className="text-13 text-broken-fg">
          {tool.problem}
        </p>
      )}
    </div>
  );
}

function Panel(props: { title: string; labelledBy: string; intro?: string; children?: ReactNode }) {
  const panel = useRef<HTMLElement>(null);

  // A new step comes into view as it opens, below the steps already done.
  useEffect(() => {
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    panel.current?.scrollIntoView?.({ block: "nearest", behavior: still ? "auto" : "smooth" });
  }, []);

  return (
    <section
      ref={panel}
      aria-labelledby={props.labelledBy}
      className="flex animate-pop scroll-mt-6 flex-col gap-5 rounded-24 border border-accent/35 bg-raised p-6"
    >
      <div className="flex flex-col gap-1">
        <h2 id={props.labelledBy} className="font-extrabold text-24 tracking-[-0.02em]">
          {props.title}
        </h2>
        {props.intro && <p className="text-14 text-fg-muted">{props.intro}</p>}
      </div>
      {props.children}
    </section>
  );
}

function Footer({ note, children }: { note: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="flex-[1_1_320px] text-13 text-fg-muted">{note}</p>
      <div className="flex gap-2.5">{children}</div>
    </div>
  );
}

function Row(props: {
  icon: ReactNode;
  title: string;
  dashed?: boolean;
  action?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section
      className={cn(
        "flex animate-fade-up flex-wrap items-center gap-4 rounded-20 border px-5 py-4.5",
        props.dashed
          ? "border-white/12 border-dashed text-fg-muted"
          : "border-edge bg-glass text-fg",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "inline-flex size-10 shrink-0 items-center justify-center rounded-full",
          props.dashed ? "bg-white/5" : "bg-accent/12 text-accent-fg",
        )}
      >
        {props.icon}
      </span>
      <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-1">
        <h2 className={cn("font-extrabold text-15", props.dashed && "text-fg-soft")}>
          {props.title}
        </h2>
        {props.children}
      </div>
      {props.action}
    </section>
  );
}

function FolderChip({ path, onRemove }: { path: string; onRemove?: () => void }) {
  return (
    <span className="inline-flex h-8 items-center gap-2 rounded-16 bg-white/6 pr-1.5 pl-3 font-mono text-12">
      {path}
      <span className="font-bold font-sans text-11 text-accent-fg">watching</span>
      {onRemove && (
        <button
          type="button"
          aria-label={`Remove ${path}`}
          onClick={onRemove}
          className="inline-flex size-6 cursor-pointer items-center justify-center rounded-full text-fg-muted hover:bg-white/8 hover:text-fg"
        >
          <X size={14} aria-hidden="true" />
        </button>
      )}
    </span>
  );
}

function CardFound({ name }: { name: string }) {
  return (
    <span className="inline-flex h-7.5 items-center gap-2 rounded-full bg-white/5 px-3 font-bold text-12 text-fg-soft">
      <span aria-hidden="true" className="size-2 animate-pulse rounded-full bg-accent" />
      {name.replace(/^NVIDIA GeForce /, "")} found
    </span>
  );
}

function Toggle(props: {
  label: string;
  text: string;
  checked: boolean;
  onChange: (on: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="flex items-center gap-3.5 rounded-16 border border-edge bg-glass px-4 py-3.5">
      <Switch
        id={id}
        checked={props.checked}
        onCheckedChange={props.onChange}
        aria-describedby={`${id}-text`}
      />
      <span className="flex flex-col gap-0.5">
        <label htmlFor={id} className="cursor-pointer font-extrabold">
          {props.label}
        </label>
        <span id={`${id}-text`} className="text-13 text-fg-muted">
          {props.text}
        </span>
      </span>
    </div>
  );
}

function RadioRing() {
  return (
    <span
      aria-hidden="true"
      className="inline-flex size-5.5 items-center justify-center rounded-full border-2 border-control group-data-[state=checked]:border-accent"
    >
      <span className="size-2.5 rounded-full bg-accent opacity-0 group-data-[state=checked]:opacity-100" />
    </span>
  );
}

function describe(settings: Settings): string {
  const standard = STANDARDS.find((each) => each.value === settings.standard);
  const naming = NAMING.find((each) => each.value === settings.naming);
  const format = standard?.spec.split(" · ").slice(1).join(" · ") ?? "";
  const names = settings.naming === "keep" ? "names kept" : `named for ${naming?.label}`;
  return `${standard?.name ?? settings.standard} · ${format} · ${names}`;
}

function megabytes(bytes: number): string {
  return `${Math.round(bytes / 1e6)} MB`;
}
