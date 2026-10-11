import { ArrowRight, Check } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { EmptyState, ShelfIllustration } from "@/components/empty-state";
import { EngineProblem } from "@/components/engine-problem";
import { Stayed } from "@/components/stayed";
import { Button } from "@/components/ui/button";
import {
  type CopyFacts,
  type Duplicate,
  type ProposedChange,
  type ReviewedChange,
  type TidyCategory,
  type TidyResult,
  useApplyTidy,
  useScan,
  useTidy,
  useUndoPlan,
} from "@/lib/engine";
import { codecName, languages, size, split, within } from "@/lib/format";
import { cn } from "@/lib/utils";

const SHOWN = 5; // changes listed per title before "Show more"

/** Tidy up: Kura proposes where every video goes, the owner keeps what they want and
 * applies it. Nothing changes until then, and History can undo it all. */
export function TidyPage() {
  const navigate = useNavigate();
  const [keep, setKeep] = useState<string[]>([]);
  const proposal = useTidy(keep);
  const apply = useApplyTidy();
  const undo = useUndoPlan();
  const scanning = useScan().data?.state === "running";
  const [only, setOnly] = useState<TidyCategory | null>(null);
  const [leftOut, setLeftOut] = useState<number[]>([]);
  const [done, setDone] = useState<TidyResult | null>(null);
  const [undone, setUndone] = useState<TidyResult | null>(null);

  if (!proposal.data) {
    return (
      <>
        <Header />
        <EngineProblem queries={[proposal]} />
      </>
    );
  }
  const found = proposal.data;
  const shown = only ? found.changes.filter((change) => change.category === only) : found.changes;
  const chosen = shown.filter((change) => !leftOut.includes(change.titleId)); // what's on screen
  const busy = apply.isPending || undo.isPending || scanning;

  function applyChosen() {
    setUndone(null);
    apply.mutate(
      { path: "/tidy", body: { changes: chosen.map(reviewed), keep } },
      {
        onSuccess: (result) => {
          setDone(result);
          setLeftOut([]);
          setKeep([]);
        },
      },
    );
  }

  return (
    <>
      <Header
        action={
          found.changes.length > 0 && (
            <Button variant="primary" disabled={busy || chosen.length === 0} onClick={applyChosen}>
              {applyText(chosen.length)}
            </Button>
          )
        }
      />
      {done && (
        <Done
          result={done}
          busy={busy}
          onUndo={() =>
            done.planId !== null &&
            undo.mutate(
              { path: `/plans/${done.planId}/undo` },
              {
                onSuccess: (result) => {
                  setDone(null);
                  setUndone(result.problems.length > 0 ? result : null);
                },
              },
            )
          }
          onHistory={() => void navigate("/history")}
        />
      )}
      {undone && <Stayed problems={undone.problems} />}
      {(apply.isError || undo.isError) && (
        <p role="alert" className="text-13 text-broken-fg">
          {(apply.error ?? undo.error)?.message}
        </p>
      )}
      <EngineProblem queries={[proposal]} />
      <Tiles
        changes={found.changes}
        waiting={found.waiting}
        broken={found.broken}
        only={only}
        onOnly={setOnly}
        onMatch={() => void navigate("/match")}
      />
      {found.changes.length === 0 ? (
        <EmptyState title="Everything is filed" illustration={<ShelfIllustration />}>
          Every video Kura knows is filed where it belongs. New ones are proposed here when they
          arrive.
        </EmptyState>
      ) : (
        <>
          <p className="animate-fade-up text-13 text-fg-muted">
            Duplicates go to a quarantine folder on the same drive (Kura quarantine). Nothing is
            deleted.
          </p>
          {found.duplicates.length > 0 && (!only || only === "duplicate") && (
            <section aria-label="Duplicates" className="flex animate-fade-up flex-col gap-4">
              {found.duplicates.map((duplicate) => (
                <Copies
                  key={duplicate.label}
                  duplicate={duplicate}
                  onSwap={() =>
                    setKeep((before) => [
                      ...before.filter((path) => path !== duplicate.keep.path),
                      ...duplicate.drop.slice(0, 1).map((copy) => copy.path),
                    ])
                  }
                />
              ))}
            </section>
          )}
          <section aria-label="Changes" className="flex animate-fade-up flex-col gap-4">
            {byTitle(shown).map(([titleId, changes]) => (
              <TitleChanges
                key={titleId}
                changes={changes}
                included={!leftOut.includes(titleId)}
                onInclude={(on) =>
                  setLeftOut((before) =>
                    on ? before.filter((id) => id !== titleId) : [...before, titleId],
                  )
                }
              />
            ))}
          </section>
          <footer className="flex animate-fade-up flex-wrap items-center justify-between gap-3 rounded-20 border border-edge bg-glass px-5 py-4">
            <span className="text-13 text-fg-muted">
              {scanning ? (
                "Kura is scanning. Apply once it's done, so it knows every file."
              ) : (
                <>
                  {chosen.length} {chosen.length === 1 ? "change" : "changes"} selected.
                  {found.waiting > 0 &&
                    ` ${found.waiting} ${found.waiting === 1 ? "file stays" : "files stay"} where ${found.waiting === 1 ? "it is" : "they are"} until matched.`}
                </>
              )}
            </span>
            <Button variant="primary" disabled={busy || chosen.length === 0} onClick={applyChosen}>
              {applyText(chosen.length)}
            </Button>
          </footer>
        </>
      )}
      {found.skipped.length > 0 && <Staying skipped={found.skipped} />}
    </>
  );
}

function Header({ action }: { action?: React.ReactNode }) {
  return (
    <header className="page-top flex animate-fade-up flex-wrap items-end justify-between gap-4">
      <div className="flex max-w-xl flex-col gap-1.5">
        <h1 className="type-title">Tidy up</h1>
        <p className="text-14 text-fg-muted">
          Kura proposes, you approve. Nothing changes until you apply, and every change can be
          undone from History.
        </p>
      </div>
      {action}
    </header>
  );
}

function Done(props: {
  result: TidyResult;
  busy: boolean;
  onUndo: () => void;
  onHistory: () => void;
}) {
  const { result } = props;
  const parts = [
    `${result.moved} ${result.moved === 1 ? "file" : "files"} filed`,
    result.quarantined > 0 &&
      `${result.quarantined} ${result.quarantined === 1 ? "copy" : "copies"} set aside`,
  ].filter(Boolean);
  return (
    <section
      aria-label="Done"
      className="flex animate-fade-up flex-col gap-3 rounded-20 border border-accent/35 bg-accent/8 px-5 py-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="inline-flex items-center gap-2 font-extrabold text-15">
          <Check size={18} aria-hidden="true" className="text-accent-fg" />
          Done: {parts.join(", ")}.
        </span>
        <div className="flex flex-wrap gap-2.5">
          {result.planId !== null && (
            <Button size="sm" disabled={props.busy} onClick={props.onUndo}>
              Undo
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={props.onHistory}>
            See History
          </Button>
        </div>
      </div>
      {result.problems.length > 0 && (
        <ul className="flex flex-col gap-1 text-13">
          {result.problems.map((problem) => (
            <li key={problem.source} className="text-broken-fg">
              {problem.label}: {problem.problem}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const TILES: { category: TidyCategory; label: string }[] = [
  { category: "mixed", label: "Mixed folders" },
  { category: "rename", label: "Renames" },
  { category: "duplicate", label: "Duplicates" },
];

function Tiles(props: {
  changes: ProposedChange[];
  waiting: number;
  broken: number;
  only: TidyCategory | null;
  onOnly: (only: TidyCategory | null) => void;
  onMatch: () => void;
}) {
  return (
    <div className="flex animate-fade-up flex-wrap gap-2.5">
      {TILES.map(({ category, label }) => {
        const count = props.changes.filter((change) => change.category === category).length;
        const on = props.only === category;
        return (
          <button
            key={category}
            type="button"
            aria-pressed={on}
            disabled={count === 0}
            onClick={() => props.onOnly(on ? null : category)}
            className={cn(
              "press flex min-w-36 cursor-pointer flex-col items-start gap-0.5 rounded-16 border bg-glass px-4 py-3 text-left disabled:cursor-default disabled:opacity-50",
              on ? "border-accent" : "border-edge",
            )}
          >
            <span className="font-extrabold text-22">{count}</span>{" "}
            <span className="text-12 text-fg-muted">{label}</span>
          </button>
        );
      })}
      <button
        type="button"
        disabled={props.waiting === 0}
        onClick={props.onMatch}
        className="press flex min-w-36 cursor-pointer flex-col items-start gap-0.5 rounded-16 border border-edge bg-glass px-4 py-3 text-left disabled:cursor-default disabled:opacity-50"
      >
        <span className="font-extrabold text-22">{props.waiting}</span>{" "}
        <span className="inline-flex items-center gap-1 text-12 text-fg-muted">
          Need a match {props.waiting > 0 && <ArrowRight size={12} aria-hidden="true" />}
        </span>
      </button>
      <div className="flex min-w-36 flex-col items-start gap-0.5 rounded-16 border border-edge bg-glass px-4 py-3">
        <span className="font-extrabold text-22">{props.broken}</span>{" "}
        <span className="text-12 text-fg-muted">Broken files</span>
      </div>
    </div>
  );
}

function TitleChanges(props: {
  changes: ProposedChange[];
  included: boolean;
  onInclude: (on: boolean) => void;
}) {
  const [all, setAll] = useState(false);
  const [first] = props.changes;
  if (!first) return null;
  const listed = all ? props.changes : props.changes.slice(0, SHOWN);
  const more = props.changes.length - listed.length;
  return (
    <section
      aria-label={first.title}
      className={cn(
        "flex flex-col gap-3 rounded-22 border border-edge bg-glass p-5 transition-opacity duration-200",
        !props.included && "opacity-55",
      )}
    >
      <label className="flex cursor-pointer items-center gap-3">
        <input
          type="checkbox"
          checked={props.included}
          onChange={(event) => props.onInclude(event.target.checked)}
          className="peer sr-only"
        />
        <span
          aria-hidden="true"
          className={cn(
            "inline-flex size-5.5 shrink-0 items-center justify-center rounded-6 peer-focus-visible:outline-2 peer-focus-visible:outline-accent-fg peer-focus-visible:outline-offset-3",
            props.included ? "bg-accent text-on-accent" : "border-2 border-control",
          )}
        >
          {props.included && <Check size={12} strokeWidth={3.4} />}
        </span>
        <span className="flex min-w-0 flex-col">
          <span className="font-extrabold text-16">{first.title}</span>
          <span className="text-12 text-fg-muted">
            {props.changes.length} {props.changes.length === 1 ? "change" : "changes"}
          </span>
        </span>
      </label>
      <ul className="flex flex-col">
        {listed.map((change) => (
          <ChangeRow key={change.source} change={change} />
        ))}
      </ul>
      {more > 0 && (
        <Button size="sm" variant="ghost" className="self-start" onClick={() => setAll(true)}>
          Show {more} more
        </Button>
      )}
    </section>
  );
}

function ChangeRow({ change }: { change: ProposedChange }) {
  const [name] = split(change.source);
  const quarantine = change.kind === "quarantine";
  return (
    <li className="flex flex-col gap-1 border-white/6 border-b py-2.5 text-13 last:border-b-0">
      <span className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "inline-flex h-5.5 items-center rounded-full px-2 font-extrabold text-11",
            quarantine ? "bg-broken/20 text-broken-fg" : "bg-white/8 text-fg-soft",
          )}
        >
          {quarantine ? "Quarantine" : "Move"}
        </span>
        <span className="font-bold">{change.label}</span>
      </span>
      <span className="font-mono text-12 text-fg-muted [overflow-wrap:anywhere]">{name}</span>
      <span className="flex items-start gap-1.5 font-mono text-12 text-fg-soft [overflow-wrap:anywhere]">
        <ArrowRight size={13} aria-hidden="true" className="mt-0.5 shrink-0 text-fg-faint" />
        {quarantine ? change.target : within(change.target, change.root)}
      </span>
      {change.taken && (
        <span className="text-12 text-fg-muted">
          A file with this name is already there, so this one gets (2). Kura never overwrites a
          file.
        </span>
      )}
    </li>
  );
}

function Copies({ duplicate, onSwap }: { duplicate: Duplicate; onSwap: () => void }) {
  const [dropped] = duplicate.drop;
  if (!dropped) return null;
  return (
    <section
      aria-label={`Copies of ${duplicate.label}`}
      className="flex flex-col gap-4 rounded-22 border border-edge bg-glass p-5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-extrabold text-16">
          {duplicate.drop.length === 1 ? "Two copies" : `${duplicate.drop.length + 1} copies`} of{" "}
          {duplicate.label}
        </h2>
        <span className="text-12 text-fg-muted">Kura keeps the better one</span>
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
        <CopyCard copy={duplicate.keep} kept />
        {duplicate.drop.map((copy) => (
          <CopyCard key={copy.path} copy={copy} kept={false} />
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-13 text-fg-muted">{duplicate.reason}</span>
        <Button size="sm" onClick={onSwap}>
          Swap which one is kept
        </Button>
      </div>
    </section>
  );
}

function CopyCard({ copy, kept }: { copy: CopyFacts; kept: boolean }) {
  const [name] = split(copy.path);
  return (
    <div
      className={cn(
        "flex flex-col gap-2.5 rounded-16 border p-4",
        kept ? "border-accent/50 bg-accent/6" : "border-edge bg-white/3",
      )}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="font-extrabold text-13">{kept ? "Keep" : "Quarantine"}</span>
        <span className="text-11 text-fg-muted">{kept ? "Better" : "Set aside"}</span>
      </span>
      <span className="font-mono text-12 [overflow-wrap:anywhere]">{name}</span>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-12">
        <dt className="text-fg-muted">Picture</dt>
        <dd className="font-mono">
          {copy.plays && copy.height
            ? `${copy.height}p${copy.codec ? ` · ${codecName(copy.codec)}` : ""}`
            : "won't play"}
        </dd>
        <dt className="text-fg-muted">Audio</dt>
        <dd className="font-mono">{languages(copy.audio)}</dd>
        <dt className="text-fg-muted">Subtitles</dt>
        <dd className="font-mono">
          {copy.subtitles > 0 ? `${copy.subtitles} you can switch off` : "none"}
        </dd>
        <dt className="text-fg-muted">Size</dt>
        <dd className="font-mono">{size(copy.size)}</dd>
      </dl>
    </div>
  );
}

function Staying({ skipped }: { skipped: { path: string; reason: string }[] }) {
  return (
    <section
      aria-labelledby="staying-title"
      className="flex animate-fade-up flex-col gap-2.5 rounded-22 border border-white/6 bg-white/3 px-5.5 py-5"
    >
      <h2 id="staying-title" className="font-extrabold text-15">
        Staying where they are
      </h2>
      <ul className="flex flex-col">
        {skipped.map((file) => (
          <li
            key={file.path}
            className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-white/6 border-b py-2 text-12 last:border-b-0"
          >
            <span className="font-mono [overflow-wrap:anywhere]">{split(file.path)[0]}</span>
            <span className="text-fg-muted">{file.reason}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function reviewed({ source, kind, target }: ProposedChange): ReviewedChange {
  return { source, kind, target };
}

/** The changes, a title at a time, in the order Kura proposes them. */
function byTitle(changes: ProposedChange[]): [number, ProposedChange[]][] {
  const groups = new Map<number, ProposedChange[]>();
  for (const change of changes) {
    groups.set(change.titleId, [...(groups.get(change.titleId) ?? []), change]);
  }
  return [...groups];
}

function applyText(count: number): string {
  return count === 0 ? "Nothing selected" : `Apply ${count} ${count === 1 ? "change" : "changes"}`;
}
