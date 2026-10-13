import { Check } from "lucide-react";
import { RadioGroup } from "radix-ui";
import { useState } from "react";
import { useNavigate } from "react-router";
import { CheckBox } from "@/components/check-box";
import { EmptyState, ShelfIllustration } from "@/components/empty-state";
import { EngineProblem } from "@/components/engine-problem";
import { STANDARDS } from "@/components/standard-choices";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import {
  fitting,
  type GroupNode,
  gpuTime,
  METHOD_NAMES,
  nights,
  ORIGINALS,
  open,
  playTime,
  type SeasonNode,
  type TitleNode,
  totals,
  tree,
} from "@/lib/convert";
import {
  type Convertible,
  type Settings,
  useAddToQueue,
  useConvertOptions,
  useEmptyQuarantine,
  useFranchises,
  useQueue,
  useSaveSettings,
  useSettings,
  useSystem,
  type Way,
} from "@/lib/engine";
import { size } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ConvertTabs, Step } from "./convert-tabs";
import { NoRoom } from "./no-room";
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
  const empty = useEmptyQuarantine();
  const stored = useSettings();
  const save = useSaveSettings();
  const settings = stored.data;
  // The standard and what becomes of originals are the library's settings, chosen here as in
  // Settings: the estimates follow at once.
  const change = (part: Partial<Settings>) =>
    settings && save.mutate({ path: "/settings", body: { ...settings, ...part } });
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [way, setWay] = useState<Way>("best");
  const [when, setWhen] = useState<When | null>(null);
  const [asking, setAsking] = useState(false); // about a drive without room for the choice

  const header = (
    <header className="page-top flex animate-fade-up flex-wrap items-end justify-between gap-4">
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
        <EmptyState
          title="Everything is at your standard"
          illustration={<ShelfIllustration />}
          action={
            settings && (
              <StandardPick settings={settings} onChange={(standard) => change({ standard })} />
            )
          }
          note="Choose another, and what's at this one can be converted to it, Kura's own conversions too."
        >
          Every video in your library is {options.data.standard} already. New ones show up here when
          a scan finds them.
        </EmptyState>
        {save.isError && <Unsaved message={save.error.message} />}
      </>
    );
  }
  const groups = tree(files, franchises.data);
  const chosen = files.filter((file) => selected.has(file.fileId));
  const timing = (when ?? (queue.data?.schedule === "nights" ? "nights" : "now")) as When;

  function toggle(node: Convertible[]) {
    setAsking(false); // a new choice is asked about afresh
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

  function queueChosen(fit: string[] = []) {
    const body = { files: chosen.map((file) => file.fileId), method: way, when: timing, fit };
    add.mutate({ path: "/queue", body }, { onSuccess: () => void navigate("/convert/queue") });
  }

  const deleting = settings?.originals === "delete";
  const short = shortage(chosen, way, options.data.free, options.data.setAside, deleting);
  const room = asking && short && (
    <NoRoom
      drive={short.drive}
      waiting={short.files}
      needed={short.needed}
      free={short.free}
      fit={short.fit}
      setAside={short.setAside}
      busy={add.isPending || empty.isPending}
      problem={empty.error ?? add.error}
      onEmpty={() =>
        empty.mutate(
          { path: "/quarantine/empty", body: { drive: short.drive } },
          { onSuccess: () => queueChosen() },
        )
      }
      onFit={() => queueChosen([short.drive])}
      onBack={() => setAsking(false)}
    />
  );

  return (
    <>
      {header}
      <EngineProblem queries={[options, franchises]} />
      <div className="flex flex-wrap items-stretch gap-5">
        <What groups={groups} selected={selected} chosen={chosen} onToggle={toggle} />
        <How
          standard={options.data.standard}
          settings={settings}
          onStandard={(standard) => change({ standard })}
          basis={chosen.length > 0 ? chosen : open(files)}
          chosen={chosen}
          way={way}
          onWay={(next) => {
            setWay(next);
            setAsking(false);
          }}
        />
      </div>
      <SeeItFirst
        n={3}
        file={chosen[0] ?? open(files)[0] ?? null}
        way={way}
        height={standardHeight(options.data.standard)}
      />
      <div className="flex flex-wrap items-stretch gap-5">
        <Estimate
          chosen={chosen}
          way={way}
          free={options.data.free}
          settings={settings}
          onOriginals={(originals) => change({ originals })}
        />
        <WhenPanel
          when={timing}
          onWhen={setWhen}
          count={chosen.length}
          episodes={chosen.every((file) => file.episode !== null)}
          busy={add.isPending}
          onQueue={() => (short ? setAsking(true) : queueChosen())}
          problem={room ? null : (add.error?.message ?? null)}
          room={room || null}
        />
      </div>
      {save.isError && <Unsaved message={save.error.message} />}
    </>
  );
}

function Unsaved({ message }: { message: string }) {
  return (
    <p role="alert" className="text-13 text-broken-fg">
      Kura couldn't save that: {message}
    </p>
  );
}

/**
 * The library's standard, which every file is brought to: the same choice as Settings', here
 * where converting starts. Changed, what's at the old one can be converted again.
 */
function StandardPick(props: {
  settings: Settings;
  onChange: (standard: Settings["standard"]) => void;
}) {
  return (
    <Segmented
      label="Your standard"
      value={props.settings.standard}
      options={STANDARDS.map((each) => ({ value: each.value, label: each.name }))}
      onChange={props.onChange}
    />
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
      <CheckBox state={state} />
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

function How(props: {
  standard: string;
  settings: Settings | undefined;
  onStandard: (standard: Settings["standard"]) => void;
  /** What's chosen, or else everything, for the estimates. */
  basis: Convertible[];
  chosen: Convertible[];
  way: Way;
  onWay: (way: Way) => void;
}) {
  const tall = standardHeight(props.standard);
  const square = props.basis.some((file) => file.aspect === "4:3");
  const spec = STANDARDS.find((each) => each.value === props.settings?.standard)?.spec;
  const same = sameEveryWay(props.basis);
  return (
    <Step
      n={2}
      id="how-title"
      title="How"
      note={props.settings ? undefined : `To your standard: ${props.standard}`}
      className="flex-[999_1_520px]"
    >
      {props.settings && (
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="flex flex-col">
              <span className="font-bold text-14">Your standard</span>
              {spec && <span className="font-mono text-12 text-fg-muted">{spec}</span>}
            </span>
            <StandardPick settings={props.settings} onChange={props.onStandard} />
          </div>
          <span className="text-12 text-fg-faint">
            Every file is brought to it. Change it, and what's at the other one can be converted
            again, Kura's own conversions too; 720p saves space more than time, as the AI model
            works on the source.
          </span>
        </div>
      )}
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
        {same ? (
          <span>{same}</span>
        ) : (
          lighterNotes(props.chosen, props.way).map((note) => <span key={note}>{note}</span>)
        )}
      </div>
    </Step>
  );
}

/**
 * Why every way takes the same for these files, when it does: none of them needs upscaling, so
 * whichever way is chosen they're only re-encoded (or keep their picture). Null otherwise.
 */
function sameEveryWay(files: Convertible[]): string | null {
  const methods = new Set(files.flatMap((file) => Object.values(file.ways).map((w) => w?.method)));
  const [method] = methods;
  if (files.length === 0 || methods.size !== 1) return null;
  const one = files.length === 1;
  if (method === "reencode") {
    return one
      ? "This file needs no upscaling, so every way only re-encodes it to your standard and takes the same."
      : "These files need no upscaling, so every way only re-encodes them to your standard and takes the same.";
  }
  if (method === "remux") {
    return one
      ? "This file's picture is at your standard already, so every way only changes its sound or container."
      : "These files' pictures are at your standard already, so every way only changes their sound or container.";
  }
  return null;
}

/** What chosen files get instead of the way chosen, since nothing gets more than it needs. */
function lighterNotes(chosen: Convertible[], way: Way): string[] {
  const byMethod = new Map<string, number>();
  for (const file of chosen) {
    const method = file.ways[way]?.method;
    if (method && method !== way) byMethod.set(method, (byMethod.get(method) ?? 0) + 1);
  }
  return [...byMethod].map(([method, n]) => {
    const gets = `${count(n, "file")} ${n === 1 ? "gets" : "get"}`;
    if (method === "fast") {
      return `${gets} Fast instead: the AI model is for SD, and nothing gets more than it needs.`;
    }
    if (method === "remux") {
      return n === 1
        ? "1 file keeps its picture, at your standard already: only its sound or container changes."
        : `${n} files keep their pictures, at your standard already: only their sound or container changes.`;
    }
    const name = METHOD_NAMES[method as keyof typeof METHOD_NAMES] ?? method;
    return `${gets} ${name} instead: there's nothing to upscale, and nothing gets more than it needs.`;
  });
}

/** GPU time per file for one way, on average. */
function perFile(files: Convertible[], way: Way): number | null {
  const timed = files.filter((file) => file.ways[way]);
  if (timed.length === 0) return null;
  return timed.reduce((sum, file) => sum + (file.ways[way]?.gpuSeconds ?? 0), 0) / timed.length;
}

/**
 * The drive without room for what's chosen, as converting it in turn would find it, with what
 * waits there and what its quarantine would free; null when there's room on every drive.
 */
function shortage(
  chosen: Convertible[],
  way: Way,
  free: Record<string, number>,
  setAside: Record<string, number>,
  deleting: boolean,
) {
  const byDrive = new Map<string, Convertible[]>();
  for (const file of chosen) {
    if (file.ways[way]) byDrive.set(file.drive, [...(byDrive.get(file.drive) ?? []), file]);
  }
  for (const [drive, files] of byDrive) {
    const room = free[drive];
    if (room === undefined) continue; // not connected: it waits for the drive instead
    const { needed, fit } = fitting(
      files.map((file) => ({ output: file.outputBytes, original: file.size })),
      room,
      deleting,
    );
    if (fit === files.length) continue;
    const aside = Object.entries(setAside).find(([d]) => d.toUpperCase() === drive.toUpperCase());
    return { drive, files, needed, free: room, fit, setAside: aside?.[1] ?? 0 };
  }
  return null;
}

function Estimate(props: {
  chosen: Convertible[];
  way: Way;
  free: Record<string, number>;
  settings: Settings | undefined;
  onOriginals: (originals: Settings["originals"]) => void;
}) {
  const system = useSystem();
  const days = props.settings?.quarantineDays;
  const deleting = props.settings?.originals === "delete";
  const sum = totals(props.chosen, props.way);
  const [drive, needed] = spaceToShow(needs(props.chosen, props.way, deleting), props.free);
  const free = props.free[drive] ?? null;
  const enough = free === null || free >= needed;
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
                : `free: not enough, this needs ${size(needed)}`
          }
          warn={!enough}
        />
        <div className="flex flex-col gap-1.5 rounded-16 bg-glass px-4 py-3.5">
          <span className="text-12 text-fg-muted">Originals</span>
          <span className="font-extrabold text-24 leading-[1.1]">
            {deleting ? "Deleted" : days === null ? "Kept for good" : `Kept ${days ?? 30} days`}
          </span>
          <span className={cn("text-12", deleting ? "text-broken-fg" : "text-fg-muted")}>
            {deleting
              ? "for good, once each result is checked and in place: no putting back"
              : "in quarantine, after each check"}
          </span>
          {props.settings && (
            <Segmented
              label="Originals, once each result is checked"
              value={props.settings.originals}
              options={ORIGINALS}
              onChange={props.onOriginals}
              className="mt-1 self-start"
            />
          )}
        </div>
      </div>
    </Step>
  );
}

/**
 * The free space what's chosen wants on each drive it's on, as converting it in turn would find
 * it (with the margin converting keeps): less when originals are deleted as results go in.
 */
function needs(chosen: Convertible[], way: Way, deleting: boolean): Record<string, number> {
  const byDrive = new Map<string, Convertible[]>();
  for (const file of chosen) {
    if (file.ways[way]) byDrive.set(file.drive, [...(byDrive.get(file.drive) ?? []), file]);
  }
  return Object.fromEntries(
    [...byDrive].map(([drive, files]) => [
      drive,
      fitting(
        files.map((file) => ({ output: file.outputBytes, original: file.size })),
        Number.POSITIVE_INFINITY,
        deleting,
      ).needed,
    ]),
  );
}

/**
 * The drive the space tile speaks for, and the space it wants: one without room for what's
 * chosen, else one that isn't connected, else the one wanting the most.
 */
function spaceToShow(
  wanted: Record<string, number>,
  free: Record<string, number>,
): [string, number] {
  const drives = Object.entries(wanted).sort((a, b) => b[1] - a[1]);
  return (
    drives.find(([drive, needed]) => (free[drive] ?? Infinity) < needed) ??
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
  /** Not enough space for the choice: the ways on, instead of adding. */
  room: React.ReactNode;
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
      {props.room ?? (
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
      )}
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
