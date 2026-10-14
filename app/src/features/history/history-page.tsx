import { useState } from "react";
import { EmptyState } from "@/components/empty-state";
import { EngineProblem } from "@/components/engine-problem";
import { Loading, PanelSkeleton } from "@/components/skeleton";
import { Stayed } from "@/components/stayed";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import {
  type Conversion,
  type History,
  type Picture,
  type PlanDone,
  type ScanDone,
  type TidyResult,
  useClearHistory,
  useHistory,
  useSettings,
  useUndoPlan,
} from "@/lib/engine";
import { clockLength, codecName, scanChanges, size } from "@/lib/format";

type Shown = "all" | "conversions" | "moves" | "scans";

const FILTERS = [
  { value: "all", label: "All" },
  { value: "conversions", label: "Conversions" },
  { value: "moves", label: "Renames and moves" },
  { value: "scans", label: "Scans" },
] as const;

/** One thing Kura did, at a moment. */
type Event =
  | { kind: "plan"; at: string; plan: PlanDone }
  | { kind: "undo"; at: string; plan: PlanDone }
  | { kind: "scan"; at: string; scan: ScanDone };

/** What a day shows before "Show all": a night's conversions or a day of scans can be many. */
const A_DAY = 20;

type Keep = "day" | "week" | "month" | "nothing";

const KEEP = [
  { value: "day", label: "Last 24 hours" },
  { value: "week", label: "Last 7 days" },
  { value: "month", label: "Last 30 days" },
  { value: "nothing", label: "Nothing" },
] as const;

/** Everything Kura changed, newest first, a week's worth of days at a time; a tidy-up can be
 * undone from here, and History cleared, all of it or what's older than a day, week or month. */
export function HistoryPage() {
  const history = useHistory();
  const undo = useUndoPlan();
  const settings = useSettings().data;
  const kept = settings?.quarantineDays;
  const [shown, setShown] = useState<Shown>("all");
  const [result, setResult] = useState<TidyResult | null>(null);
  const [clearing, setClearing] = useState(false);
  const [cleared, setCleared] = useState<number | null>(null);
  const [opened, setOpened] = useState<ReadonlySet<string>>(new Set());

  const pages = history.data?.pages;
  const events = pages ? eventsOf(together(pages), shown) : [];
  const anything = pages?.some((page) => page.plans.length + page.scans.length > 0) ?? false;
  return (
    <>
      <header className="page-top flex animate-fade-up flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-xl flex-col gap-1.5">
          <h1 className="type-title">History</h1>
          <p className="text-14 text-fg-muted">
            {settings?.historyDays
              ? `Everything Kura changed in the last ${settings.historyDays} days, newest first. Renames and moves can be undone while they're here`
              : "Everything Kura changed, newest first. Renames and moves can be undone at any time"}
            , and a converted file's original put back{" "}
            {kept === null ? "while it's in quarantine" : `for ${kept ?? 30} days`}.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <Segmented label="Show" value={shown} options={FILTERS} onChange={setShown} />
          {anything && !clearing && (
            <Button variant="ghost" onClick={() => setClearing(true)}>
              Clear History
            </Button>
          )}
        </div>
      </header>
      {clearing && (
        <ClearHistory
          onClose={() => setClearing(false)}
          onCleared={(gone) => {
            setCleared(gone);
            setClearing(false);
          }}
        />
      )}
      {cleared !== null && !clearing && (
        <p role="status" className="text-13 text-fg-muted">
          {cleared === 0
            ? "There was nothing to clear: what's left is newer, or can still be put back."
            : `${count(cleared, "entry", "entries")} cleared from History. Your files stay as they are.`}
        </p>
      )}
      <EngineProblem queries={[history]} />
      {!history.data && (
        <Loading label="Loading history" queries={[history]}>
          <PanelSkeleton rows={4} />
          <PanelSkeleton rows={3} />
        </Loading>
      )}
      {undo.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          {undo.error.message}
        </p>
      )}
      {result && result.problems.length > 0 && <Stayed problems={result.problems} />}
      {history.data && events.length === 0 && !history.hasNextPage && (
        <EmptyState title="Nothing yet">
          Kura lists here everything it changes in your folders, newest first.
        </EmptyState>
      )}
      {history.data && events.length === 0 && history.hasNextPage && (
        <p className="text-13 text-fg-muted">Nothing of that kind on the days shown.</p>
      )}
      {days(events).map(([day, onDay]) => {
        const all = opened.has(day) || onDay.length <= A_DAY;
        return (
          <section
            key={day}
            aria-label={day}
            className="flex animate-fade-up flex-col gap-1 rounded-22 border border-edge bg-glass px-5 py-4 shadow-panel"
          >
            <h2 className="pb-1 font-extrabold text-15">{day}</h2>
            <ul className="flex flex-col">
              {(all ? onDay : onDay.slice(0, A_DAY)).map((event) => (
                <EventRow
                  key={`${event.kind}-${event.kind === "scan" ? event.scan.id : event.plan.id}`}
                  event={event}
                  busy={undo.isPending}
                  onUndo={(plan) =>
                    undo.mutate({ path: `/plans/${plan.id}/undo` }, { onSuccess: setResult })
                  }
                />
              ))}
            </ul>
            {!all && (
              <Button
                size="sm"
                variant="ghost"
                className="self-start"
                onClick={() => setOpened((before) => new Set(before).add(day))}
              >
                Show all {onDay.length}
              </Button>
            )}
          </section>
        );
      })}
      {history.hasNextPage && (
        <Button
          className="self-center"
          disabled={history.isFetchingNextPage}
          onClick={() => void history.fetchNextPage()}
        >
          {history.isFetchingNextPage ? "Loading older days…" : "Show older"}
        </Button>
      )}
    </>
  );
}

/** Asks before clearing History: what stays (the last day, week or month, or nothing), and
 * that what goes can't be undone from here. Files never change, and what still has a copy in
 * quarantine stays, so it can be put back. */
function ClearHistory(props: { onClose: () => void; onCleared: (gone: number) => void }) {
  const clear = useClearHistory();
  const [keep, setKeep] = useState<Keep>("week");
  return (
    <fieldset
      aria-label="Clear History?"
      className="flex animate-fade-up flex-col gap-3 rounded-16 border border-danger/40 bg-danger/8 p-4"
    >
      <span className="font-extrabold text-14">Clear History?</span>
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-bold text-13">Keep</span>
        <Segmented label="Keep" value={keep} options={KEEP} onChange={setKeep} />
      </div>
      <span className="text-13 text-fg-soft">
        What's cleared can't be undone or put back from here. Your files stay as they are, and
        anything with a copy still in quarantine stays listed, so you can still put it back.
      </span>
      {clear.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          {clear.error.message}
        </p>
      )}
      <div className="flex flex-wrap gap-2.5">
        <Button
          size="sm"
          variant="danger"
          disabled={clear.isPending}
          onClick={() =>
            clear.mutate(
              { path: "/history/clear", body: { keep } },
              { onSuccess: (done) => props.onCleared(done.cleared) },
            )
          }
        >
          {keep === "nothing" ? "Clear all of History" : "Clear the rest"}
        </Button>
        <Button size="sm" variant="ghost" onClick={props.onClose}>
          Back
        </Button>
      </div>
    </fieldset>
  );
}

function EventRow(props: { event: Event; busy: boolean; onUndo: (plan: PlanDone) => void }) {
  const { event } = props;
  const [verb, title, detail] = words(event);
  const plan = event.kind === "plan" ? event.plan : null;
  // A conversion goes back only while its original is still in quarantine.
  const undoable =
    plan !== null &&
    plan.undoneAt === null &&
    (plan.kind === "convert" ? plan.quarantined > 0 : plan.moved + plan.quarantined > 0);
  const action =
    plan?.kind === "convert"
      ? "Put back the original"
      : plan?.deleted
        ? "Put back what was deleted"
        : "Undo";
  return (
    <li className="grid grid-cols-[3.5rem_6.5rem_1fr_auto] items-center gap-x-3 gap-y-1 border-rule border-b py-3 text-13 last:border-b-0">
      <span className="font-mono text-12 text-fg-muted">{clock(event.at)}</span>
      <span className="font-extrabold">{verb}</span>
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="font-bold">{title}</span>
        {detail && <span className="text-12 text-fg-muted">{detail}</span>}
      </span>
      {undoable ? (
        <Button
          size="sm"
          aria-label={action}
          disabled={props.busy}
          onClick={() => props.onUndo(plan)}
        >
          {plan.kind === "convert" || plan.deleted ? "Put back" : "Undo"}
        </Button>
      ) : (
        <span />
      )}
    </li>
  );
}

/** [verb, title, detail] for one event, as the history board words them. */
function words(event: Event): [string, string, string | null] {
  if (event.kind === "scan") {
    const { scan } = event;
    const detail =
      scan.state === "failed"
        ? (scan.problem ?? "It stopped")
        : scan.state === "running"
          ? "Running now"
          : scan.state === "paused"
            ? "Paused"
            : (scan.note ?? "Every folder looked at");
    const changed =
      scan.state === "done" && scan.added !== null && scan.gone !== null
        ? ` · ${scanChanges(scan.added, scan.gone)}`
        : "";
    return ["Scanned", "Your library folders", `${detail}${changed}`];
  }
  const { plan } = event;
  const made = plan.conversion;
  if (plan.kind === "convert") {
    const label = plan.title.replace(/^Converted /, "");
    if (event.kind === "undo") return ["Put back", label, "The original is in its place again"];
    const gone = plan.undoneAt === null && plan.quarantined === 0 && plan.moved > 0;
    const words = [made && conversionWords(made), gone && "original deleted"].filter(Boolean);
    return ["Converted", label, words.length > 0 ? words.join(" · ") : null];
  }
  if (plan.deleted) {
    const label = plan.title.replace(/^Deleted /, "");
    if (event.kind === "undo")
      return ["Put back", label, `You put ${count(plan.undone, "file")} back`];
    const parts = [
      plan.quarantined > 0 && `${count(plan.quarantined, "video")} in quarantine`,
      plan.failed > 0 && `${plan.failed} couldn't be moved`,
      plan.undoneAt !== null && "Put back since",
      `plan ${plan.id}`,
    ].filter(Boolean);
    return ["Deleted", label, parts.join(" · ")];
  }
  if (event.kind === "undo") {
    return ["Undone", plan.title, `You put ${count(plan.undone, "file")} back`];
  }
  const parts = [
    plan.moved > 0 && `${count(plan.moved, "file")} moved`,
    plan.quarantined > 0 && `${count(plan.quarantined, "copy", "copies")} set aside`,
    plan.failed > 0 && `${plan.failed} couldn't be moved`,
    plan.undoneAt !== null && "Put back since",
    plan.undoneAt === null && plan.undone > 0 && `${plan.undone} put back`, // the rest couldn't be
    `plan ${plan.id}`,
  ].filter(Boolean);
  return [plan.title.startsWith("Renamed") ? "Renamed" : "Moved", plan.title, parts.join(" · ")];
}

/** "480p H.264 233 MB → 1080p HEVC 412 MB · 58 min · checked": every result is checked before
 * it takes its original's place. */
function conversionWords(made: Conversion): string {
  const picture = ({ height, codec, size: bytes }: Picture) =>
    [height && `${height}p`, codec && codecName(codec), bytes && size(bytes)]
      .filter(Boolean)
      .join(" ");
  return [
    `${picture(made.before)} → ${picture(made.after)}`,
    made.seconds !== null &&
      (made.seconds < 60 ? `${Math.round(made.seconds)} s` : clockLength(made.seconds / 60)),
    "checked",
  ]
    .filter(Boolean)
    .join(" · ");
}

/** The pages loaded, as one: a tidy-up undone on a later day is on both days' pages. Only
 * what happened on the days loaded shows (from `from` on), so the tidy-up itself waits for its
 * own page. */
function together(pages: History[]): { plans: PlanDone[]; scans: ScanDone[]; from: string | null } {
  const plans = new Map<number, PlanDone>();
  const scans = new Map<number, ScanDone>();
  for (const page of pages) {
    for (const plan of page.plans) if (!plans.has(plan.id)) plans.set(plan.id, plan);
    for (const scan of page.scans) if (!scans.has(scan.id)) scans.set(scan.id, scan);
  }
  return {
    plans: [...plans.values()],
    scans: [...scans.values()],
    from: pages.at(-1)?.older ?? null,
  };
}

function eventsOf(history: ReturnType<typeof together>, shown: Shown): Event[] {
  const events: Event[] = [];
  const kinds: Record<Shown, PlanDone["kind"][]> = {
    all: ["tidy", "convert"],
    conversions: ["convert"],
    moves: ["tidy"],
    scans: [],
  };
  for (const plan of history.plans) {
    if (!kinds[shown].includes(plan.kind)) continue;
    events.push({ kind: "plan", at: plan.appliedAt, plan });
    if (plan.undoneAt) events.push({ kind: "undo", at: plan.undoneAt, plan });
  }
  if (shown === "all" || shown === "scans") {
    for (const scan of history.scans) events.push({ kind: "scan", at: scan.startedAt, scan });
  }
  return events
    .filter((event) => history.from === null || localDay(event.at) >= history.from)
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
}

/** "2026-10-14": the day on this PC a moment fell on, as the engine counts History's days. */
function localDay(at: string): string {
  const moment = new Date(at);
  const month = String(moment.getMonth() + 1).padStart(2, "0");
  const day = String(moment.getDate()).padStart(2, "0");
  return `${moment.getFullYear()}-${month}-${day}`;
}

/** The events by day, as the owner reads them: "Today", "Yesterday", "8 October", and
 * "8 October 2025" a year back. */
function days(events: Event[]): [string, Event[]][] {
  const groups = new Map<string, Event[]>();
  for (const event of events) {
    const day = dayName(new Date(event.at));
    groups.set(day, [...(groups.get(day) ?? []), event]);
  }
  return [...groups];
}

function dayName(moment: Date): string {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (moment.toDateString() === today.toDateString()) return "Today";
  if (moment.toDateString() === yesterday.toDateString()) return "Yesterday";
  // A year ago, the same day has the year with it, so the two never run together.
  return moment.toLocaleDateString(
    "en-GB",
    moment.getFullYear() === today.getFullYear()
      ? { day: "numeric", month: "long" }
      : { day: "numeric", month: "long", year: "numeric" },
  );
}

function clock(at: string): string {
  return new Date(at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function count(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
