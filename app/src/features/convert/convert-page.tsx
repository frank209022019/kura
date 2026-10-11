import { Check } from "lucide-react";
import { RadioGroup } from "radix-ui";
import { useState } from "react";
import { useNavigate } from "react-router";
import { EmptyState, ShelfIllustration } from "@/components/empty-state";
import { EngineProblem } from "@/components/engine-problem";
import { Button } from "@/components/ui/button";
import {
  type GroupNode,
  gpuTime,
  METHOD_NAMES,
  nights,
  open,
  playTime,
  type SeasonNode,
  type TitleNode,
  totals,
  tree,
} from "@/lib/convert";
import {
  type Convertible,
  useAddToQueue,
  useConvertOptions,
  useFranchises,
  useQueue,
  useSystem,
  type Way,
} from "@/lib/engine";
import { size } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ConvertTabs, Step } from "./convert-tabs";
import { SeeItFirst } from "./see-it-first";

type When = "now" | "nights" | "after";

const WAYS: { way: Way; name: string; says: string; engine: string }[] = [
  {
    way: "best",
    name: "Best quality",
    says: "Crispest lines, cleans blur and blocky compression.",
    engine: "Real-ESRGAN anime model",
  },
  {
    way: "fast",
    name: "Fast",
    says: "Sharper lines, lighter clean-up. Good for 720p.",
    engine: "Anime4K shaders",
  },
  {
    way: "reencode",
    name: "Re-encode only",
    says: "No AI. Brings the format to your standard.",
    engine: "Graphics card encoder",
  },
];

/** Convert: pick what to convert and how, see what it takes, then queue it. */
export function ConvertPage() {
  const navigate = useNavigate();
  const options = useConvertOptions();
  const franchises = useFranchises();
  const queue = useQueue();
  const add = useAddToQueue();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [way, setWay] = useState<Way>("best");
  const [when, setWhen] = useState<When | null>(null);

  const header = (
    <header className="flex animate-fade-up flex-wrap items-end justify-between gap-4">
      <div className="flex max-w-xl flex-col gap-1.5">
        <h1 className="type-title">Convert</h1>
        <p className="text-14 text-fg-muted">
          Pick what to convert, see what it takes, then queue it.
        </p>
      </div>
      <ConvertTabs queued={queue.data ? queue.data.queued.length : null} />
    </header>
  );
  if (!options.data || !franchises.data) {
    return (
      <>
        {header}
        <EngineProblem queries={[options, franchises]} />
      </>
    );
  }
  const files = options.data.files;
  if (files.length === 0) {
    return (
      <>
        {header}
        <EmptyState title="Everything is at your standard" illustration={<ShelfIllustration />}>
          Every video in your library is {options.data.standard} already. New ones show up here when
          a scan finds them.
        </EmptyState>
      </>
    );
  }
  const groups = tree(files, franchises.data);
  const chosen = files.filter((file) => selected.has(file.fileId));
  const timing = (when ?? (queue.data?.schedule === "nights" ? "nights" : "now")) as When;

  function toggle(node: Convertible[]) {
    const ids = open(node).map((file) => file.fileId);
    setSelected((before) => {
      const next = new Set(before);
      const all = ids.every((id) => next.has(id));
      for (const id of ids) {
        if (all) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  }

  function queueChosen() {
    const body = { files: chosen.map((file) => file.fileId), method: way, when: timing };
    add.mutate({ path: "/queue", body }, { onSuccess: () => void navigate("/convert/queue") });
  }

  return (
    <>
      {header}
      <EngineProblem queries={[options, franchises]} />
      <div className="flex flex-wrap items-stretch gap-5">
        <What groups={groups} selected={selected} chosen={chosen} onToggle={toggle} />
        <How
          standard={options.data.standard}
          basis={chosen.length > 0 ? chosen : open(files)}
          chosen={chosen}
          way={way}
          onWay={setWay}
        />
      </div>
      <SeeItFirst
        n={3}
        file={chosen[0] ?? open(files)[0] ?? null}
        way={way}
        height={standardHeight(options.data.standard)}
      />
      <div className="flex flex-wrap items-stretch gap-5">
        <Estimate chosen={chosen} way={way} free={options.data.free} />
        <WhenPanel
          when={timing}
          onWhen={setWhen}
          count={chosen.length}
          episodes={chosen.every((file) => file.episode !== null)}
          busy={add.isPending}
          onQueue={queueChosen}
          problem={add.error?.message ?? null}
        />
      </div>
    </>
  );
}

function What(props: {
  groups: GroupNode[];
  selected: Set<number>;
  chosen: Convertible[];
  onToggle: (files: Convertible[]) => void;
}) {
  const sum = totals(props.chosen, "best");
  const rows = props.groups.flatMap((group) =>
    group.titles.length > 1
      ? [
          <TreeRow
            key={group.key}
            level={0}
            name={group.name}
            meta="franchise"
            files={group.files}
            {...props}
          />,
          ...group.titles.flatMap((title) => titleRows(title, 1, props)),
        ]
      : group.titles.flatMap((title) => titleRows(title, 0, props)),
  );
  return (
    <Step n={1} id="what-title" title="What" className="flex-[1_1_380px]">
      <div className="flex max-h-[28rem] flex-col overflow-y-auto text-14">{rows}</div>
      <div className="mt-auto flex flex-wrap gap-2">
        {props.chosen.length === 0 ? (
          <Chip>Nothing chosen yet</Chip>
        ) : (
          <>
            <Chip>
              {count(
                props.chosen.length,
                props.chosen.every((file) => file.episode !== null) ? "episode" : "file",
              )}
            </Chip>
            <Chip>{playTime(sum.seconds)} of video</Chip>
            <Chip>{sum.sources}</Chip>
          </>
        )}
      </div>
    </Step>
  );
}

function titleRows(
  title: TitleNode,
  level: number,
  props: { selected: Set<number>; onToggle: (files: Convertible[]) => void },
) {
  return [
    <TreeRow
      key={title.key}
      level={level}
      name={title.name}
      meta={left(title.files)}
      files={title.files}
      {...props}
    />,
    ...(title.seasons.length > 1
      ? compact(title.seasons).map((season) => (
          <TreeRow
            key={`${title.key}-${season.key}`}
            level={level + 1}
            name={season.label}
            meta={count(open(season.files).length, "episode")}
            files={season.files}
            {...props}
          />
        ))
      : []),
  ];
}

/** A title's seasons, the first two on their own and the rest together: "Seasons 3 to 9". */
function compact(seasons: SeasonNode[]): SeasonNode[] {
  const numbered = seasons.filter((season) => season.key.startsWith("s") && season.key !== "s0");
  if (numbered.length <= 3) return seasons;
  const [first, second, ...rest] = numbered;
  const others = seasons.filter((season) => !numbered.includes(season));
  const label = `Seasons ${rest[0]?.label.replace("Season ", "")} to ${rest.at(-1)?.label.replace("Season ", "")}`;
  const together = { key: "rest", label, files: rest.flatMap((season) => season.files) };
  return [first, second, together, ...others].filter(
    (season): season is SeasonNode => season !== undefined,
  );
}

/** "283 left", "62 left, 2 broken skipped", "all in the queue". */
function left(files: Convertible[]): string {
  const ready = open(files).length;
  const broken = files.filter((file) => file.broken).length;
  if (ready === 0 && broken === 0) return "all in the queue";
  return [`${ready} left`, broken > 0 && `${broken} broken skipped`].filter(Boolean).join(", ");
}

function TreeRow(props: {
  level: number;
  name: string;
  meta: string;
  files: Convertible[];
  selected: Set<number>;
  onToggle: (files: Convertible[]) => void;
}) {
  const ids = open(props.files).map((file) => file.fileId);
  const picked = ids.filter((id) => props.selected.has(id)).length;
  const state = ids.length > 0 && picked === ids.length ? true : picked > 0 ? "mixed" : false;
  const indent = ["pl-2", "pl-9", "pl-16"][props.level] ?? "pl-16";
  return (
    <label
      className={cn(
        "press flex min-h-11 cursor-pointer items-center gap-3 rounded-12 pr-2 has-disabled:cursor-default has-disabled:opacity-50",
        indent,
        props.level === 0 ? "font-extrabold" : "font-bold",
        state === true ? "bg-accent/8 text-fg" : state === "mixed" ? "text-fg" : "text-fg-soft",
      )}
    >
      <input
        type="checkbox"
        checked={state === true}
        ref={(box) => {
          if (box) box.indeterminate = state === "mixed";
        }}
        disabled={ids.length === 0}
        onChange={() => props.onToggle(props.files)}
        className="peer sr-only"
      />
      <Box state={state} />
      <span className="min-w-0 truncate">{props.name}</span>
      <span
        className={cn(
          "ml-auto shrink-0 font-semibold text-12",
          state === true && props.level > 0 ? "text-accent-fg" : "text-fg-muted",
        )}
      >
        {props.meta}
      </span>
    </label>
  );
}

const FOCUS =
  "peer-focus-visible:outline-2 peer-focus-visible:outline-accent-fg peer-focus-visible:outline-offset-3";

function Box({ state }: { state: boolean | "mixed" }) {
  if (state === true) {
    return (
      <span
        aria-hidden="true"
        className={cn(
          "inline-flex size-5 shrink-0 items-center justify-center rounded-6 bg-accent text-on-accent",
          FOCUS,
        )}
      >
        <Check size={11} strokeWidth={3.6} />
      </span>
    );
  }
  if (state === "mixed") {
    return (
      <span
        aria-hidden="true"
        className={cn(
          "inline-flex size-5 shrink-0 items-center justify-center rounded-6 bg-accent/25 shadow-[inset_0_0_0_2px_var(--color-accent)]",
          FOCUS,
        )}
      >
        <span className="h-0.5 w-2.5 bg-accent-fg" />
      </span>
    );
  }
  return (
    <span
      aria-hidden="true"
      className={cn(
        "size-5 shrink-0 rounded-6 shadow-[inset_0_0_0_2px_var(--color-control)]",
        FOCUS,
      )}
    />
  );
}

function How(props: {
  standard: string;
  /** What's chosen, or else everything, for the estimates. */
  basis: Convertible[];
  chosen: Convertible[];
  way: Way;
  onWay: (way: Way) => void;
}) {
  const tall = standardHeight(props.standard);
  const square = props.basis.some((file) => file.aspect === "4:3");
  const lighter = props.chosen.filter((file) => file.ways[props.way]?.method !== props.way);
  return (
    <Step
      n={2}
      id="how-title"
      title="How"
      note={`To your standard: ${props.standard}`}
      className="flex-[999_1_520px]"
    >
      <RadioGroup.Root
        aria-label="Quality"
        value={props.way}
        onValueChange={(value) => props.onWay(value as Way)}
        className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-2.5"
      >
        {WAYS.map(({ way, name, says, engine }) => {
          const on = props.way === way;
          const each = perFile(props.basis, way);
          return (
            <RadioGroup.Item
              key={way}
              value={way}
              aria-label={name}
              aria-describedby={`way-${way}`}
              className={cn(
                "press flex cursor-pointer flex-col gap-2 rounded-18 border-2 p-4 text-left",
                on ? "border-accent bg-accent/10" : "border-edge bg-white/3",
              )}
            >
              <span className="flex w-full items-center justify-between gap-2">
                <span className="font-extrabold text-16">{name}</span>
                <Dot on={on} />
              </span>
              <span id={`way-${way}`} className="flex flex-col gap-2">
                <span className="text-13 text-fg-muted">{says}</span>
                <span className={cn("font-mono text-12", on ? "text-accent-fg" : "text-fg-muted")}>
                  {each === null ? "nothing to convert" : `≈ ${gpuTime(each)} per episode`}
                </span>
              </span>
              <span className="text-12 text-fg-faint">{engine}</span>
            </RadioGroup.Item>
          );
        })}
      </RadioGroup.Root>
      <div className="flex flex-col gap-1 text-12 text-fg-faint">
        {square && (
          <span>
            4:3 shows stay 4:3 at {Math.round((tall * 4) / 3)} × {tall}. Nothing is stretched or
            cropped.
          </span>
        )}
        {lighter.length > 0 && (
          <span>
            {count(lighter.length, "file")} {lighter.length === 1 ? "gets" : "get"}{" "}
            {METHOD_NAMES[lighter[0]?.ways[props.way]?.method ?? "fast"]} instead: the AI model is
            for SD, and nothing gets more than it needs.
          </span>
        )}
      </div>
    </Step>
  );
}

/** GPU time per file for one way, on average. */
function perFile(files: Convertible[], way: Way): number | null {
  const timed = files.filter((file) => file.ways[way]);
  if (timed.length === 0) return null;
  return timed.reduce((sum, file) => sum + (file.ways[way]?.gpuSeconds ?? 0), 0) / timed.length;
}

/** Free space wanted on a drive, over the results' size there (the engine wants the same). */
const ROOM = 1.25;

function Estimate(props: { chosen: Convertible[]; way: Way; free: Record<string, number> }) {
  const system = useSystem();
  const sum = totals(props.chosen, props.way);
  const [drive, needed] = spaceToShow(sum.byDrive, props.free);
  const free = props.free[drive] ?? null;
  const enough = free === null || free >= needed * ROOM;
  const card = system.data?.graphicsCard ?? "";
  return (
    <Step
      n={4}
      id="estimate-title"
      title="Estimate"
      note={/1660/.test(card) ? `Measured on your ${card}` : "Speeds measured on a GTX 1660 Super"}
      className="flex-[999_1_520px]"
    >
      <div className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-2.5">
        <Tile
          label="GPU time"
          value={sum.files > 0 ? `≈ ${gpuTime(sum.gpuSeconds)}` : "–"}
          note={sum.files > 0 ? nights(sum.gpuSeconds) : "nothing chosen yet"}
        />
        <Tile
          label="Size"
          value={sum.files > 0 ? `${size(sum.sizeBefore)} → ${size(sum.sizeAfter)}` : "–"}
          note={sum.files > 0 ? `≈ ${size(sum.sizeAfter / sum.files)} per episode` : "nothing yet"}
        />
        <Tile
          label={`Space on ${drive}`}
          value={
            <>
              {free === null ? "?" : size(free)}
              {free !== null && enough && (
                <Check size={18} strokeWidth={3} aria-hidden="true" className="text-accent-fg" />
              )}
            </>
          }
          note={
            free === null
              ? "the drive isn't connected"
              : enough
                ? "free, plenty for this"
                : `free: not enough, this needs ${size(needed * ROOM)}`
          }
          warn={!enough}
        />
        <Tile label="Originals" value="Kept 30 days" note="in quarantine, after each check" />
      </div>
    </Step>
  );
}

/**
 * The drive the space tile speaks for, and what its results take: one without room for them,
 * else one that isn't connected, else the one taking the most.
 */
function spaceToShow(
  byDrive: Record<string, number>,
  free: Record<string, number>,
): [string, number] {
  const drives = Object.entries(byDrive).sort((a, b) => b[1] - a[1]);
  return (
    drives.find(([drive, needed]) => (free[drive] ?? Infinity) < needed * ROOM) ??
    drives.find(([drive]) => free[drive] === undefined) ??
    drives[0] ?? [Object.keys(free)[0] ?? "", 0]
  );
}

function Tile(props: { label: string; value: React.ReactNode; note: string; warn?: boolean }) {
  return (
    <div className="flex flex-col gap-1 rounded-16 bg-glass px-4 py-3.5">
      <span className="text-12 text-fg-muted">{props.label}</span>
      <span className="flex items-center gap-2 font-extrabold text-24 leading-[1.1]">
        {props.value}
      </span>
      <span className={cn("text-12", props.warn ? "text-broken-fg" : "text-fg-muted")}>
        {props.note}
      </span>
    </div>
  );
}

function WhenPanel(props: {
  when: When;
  onWhen: (when: When) => void;
  count: number;
  episodes: boolean;
  busy: boolean;
  onQueue: () => void;
  problem: string | null;
}) {
  const choices: { when: When; label: string; note?: string }[] = [
    { when: "now", label: "Start now" },
    { when: "nights", label: "Nights only", note: "23:00–07:00" },
    { when: "after", label: "After the current queue" },
  ];
  const what = props.episodes ? "episode" : "file";
  return (
    <Step n={5} id="when-title" title="When" className="flex-[1_1_380px]">
      <RadioGroup.Root
        aria-label="When to convert"
        value={props.when}
        onValueChange={(value) => props.onWhen(value as When)}
        className="flex flex-col gap-1.5"
      >
        {choices.map((choice) => {
          const on = props.when === choice.when;
          return (
            <RadioGroup.Item
              key={choice.when}
              value={choice.when}
              className={cn(
                "press flex min-h-11 cursor-pointer items-center gap-3 rounded-14 px-3 text-left",
                on ? "bg-accent/10 font-extrabold text-fg" : "font-bold text-fg-soft",
              )}
            >
              <Dot on={on} />
              {choice.label}
              {choice.note && (
                <span className="ml-auto font-medium font-mono text-12 text-accent-fg">
                  {choice.note}
                </span>
              )}
            </RadioGroup.Item>
          );
        })}
      </RadioGroup.Root>
      {props.problem && (
        <p role="alert" className="text-13 text-broken-fg">
          {props.problem}
        </p>
      )}
      <Button
        variant="primary"
        className="mt-auto min-h-12 w-full"
        disabled={props.count === 0 || props.busy}
        onClick={props.onQueue}
      >
        {props.count === 0
          ? "Choose what to convert"
          : `Add ${count(props.count, what)} to the queue`}
      </Button>
    </Step>
  );
}

function Dot({ on }: { on: boolean }) {
  return on ? (
    <span
      aria-hidden="true"
      className="inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-accent"
    >
      <span className="size-2 rounded-full bg-on-accent" />
    </span>
  ) : (
    <span
      aria-hidden="true"
      className="size-5 shrink-0 rounded-full shadow-[inset_0_0_0_2px_var(--color-control)]"
    />
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex h-7 items-center rounded-full bg-white/6 px-3 font-bold text-12">
      {children}
    </span>
  );
}

/** The standard's height, from its name: "Cinema 1080p" is 1080. */
function standardHeight(standard: string): number {
  return Number(/(\d+)p/.exec(standard)?.[1] ?? 1080);
}

function count(n: number, one: string): string {
  return `${n} ${n === 1 ? one : `${one}s`}`;
}
