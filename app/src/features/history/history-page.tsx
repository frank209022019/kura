import { useState } from "react";
import { EmptyState } from "@/components/empty-state";
import { EngineProblem } from "@/components/engine-problem";
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
  useHistory,
  useUndoPlan,
} from "@/lib/engine";
import { clockLength, codecName, size } from "@/lib/format";

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

/** Everything Kura changed, newest first; a tidy-up can be undone from here. */
export function HistoryPage() {
  const history = useHistory();
  const undo = useUndoPlan();
  const [shown, setShown] = useState<Shown>("all");
  const [result, setResult] = useState<TidyResult | null>(null);

  const events = history.data ? eventsOf(history.data, shown) : [];
  return (
    <>
      <header className="flex animate-fade-up flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-xl flex-col gap-1.5">
          <h1 className="type-title">History</h1>
          <p className="text-14 text-fg-muted">
            Everything Kura changed, newest first. Renames and moves can be undone at any time, and
            a converted file's original put back for 30 days.
          </p>
        </div>
        <Segmented label="Show" value={shown} options={FILTERS} onChange={setShown} />
      </header>
      <EngineProblem queries={[history]} />
      {undo.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          {undo.error.message}
        </p>
      )}
      {result && result.problems.length > 0 && <Stayed problems={result.problems} />}
      {history.data &&
        (events.length === 0 ? (
          <EmptyState title="Nothing yet">
            Kura lists here everything it changes in your folders, newest first.
          </EmptyState>
        ) : (
          days(events).map(([day, onDay]) => (
            <section
              key={day}
              aria-label={day}
              className="flex animate-fade-up flex-col gap-1 rounded-22 border border-edge bg-glass px-5 py-4"
            >
              <h2 className="pb-1 font-extrabold text-15">{day}</h2>
              <ul className="flex flex-col">
                {onDay.map((event) => (
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
            </section>
          ))
        ))}
    </>
  );
}

function EventRow(props: { event: Event; busy: boolean; onUndo: (plan: PlanDone) => void }) {
  const { event } = props;
  const [verb, title, detail] = words(event);
  const plan = event.kind === "plan" ? event.plan : null;
  const undoable = plan !== null && plan.undoneAt === null && plan.moved + plan.quarantined > 0;
  const action = plan?.kind === "convert" ? "Put back the original" : "Undo";
  return (
    <li className="grid grid-cols-[3.5rem_6.5rem_1fr_auto] items-center gap-x-3 gap-y-1 border-white/6 border-b py-3 text-13 last:border-b-0">
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
          {plan.kind === "convert" ? "Put back" : "Undo"}
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
    return ["Scanned", "Your library folders", detail];
  }
  const { plan } = event;
  const made = plan.conversion;
  if (plan.kind === "convert") {
    const label = plan.title.replace(/^Converted /, "");
    if (event.kind === "undo") return ["Put back", label, "The original is in its place again"];
    return ["Converted", label, made ? conversionWords(made) : null];
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

function eventsOf(history: History, shown: Shown): Event[] {
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
  return events.sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
}

/** The events by day, as the owner reads them: "Today", "Yesterday", "8 October". */
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
  return moment.toLocaleDateString("en-GB", { day: "numeric", month: "long" });
}

function clock(at: string): string {
  return new Date(at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function count(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
