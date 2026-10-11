import { Check, FolderTree, Pause, Play, Timer } from "lucide-react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router";
import { EngineProblem } from "@/components/engine-problem";
import { Button } from "@/components/ui/button";
import { type Scan, useFolders, useScan, useScanAction } from "@/lib/engine";
import { cn } from "@/lib/utils";

/** The scan: finding every video, then reading each one. Nothing is renamed or moved. */
export function ScanPage() {
  const scan = useScan();
  const folders = useFolders();
  const action = useScanAction();
  const navigate = useNavigate();

  if (!scan.data || !folders.data) {
    return (
      <>
        <h1 className="type-title animate-fade-up">Scan</h1>
        <EngineProblem queries={[scan, folders]} />
      </>
    );
  }
  const now = scan.data;
  const where = mapping(folders.data.map((folder) => folder.path));
  const send = (path: string) => action.mutate({ path });

  return (
    <>
      <header className="flex animate-fade-up flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <span className="type-eyebrow">{eyebrow(now)}</span>
          <h1 className="type-title">
            {now.state === "done" ? "Mapped" : "Mapping"} {where}
          </h1>
          <p className="text-14 text-fg-muted">{subtitle(now)}</p>
        </div>
        <div className="flex flex-wrap gap-2.5">
          {now.state === "running" && (
            <Button disabled={action.isPending} onClick={() => send("/scan/pause")}>
              <Pause size={16} aria-hidden="true" />
              Pause scan
            </Button>
          )}
          {now.state === "paused" && (
            <Button
              variant="primary"
              disabled={action.isPending}
              onClick={() => send("/scan/resume")}
            >
              <Play size={16} aria-hidden="true" />
              Resume scan
            </Button>
          )}
          {(now.state === "done" || now.state === "failed" || now.state === "idle") && (
            <Button disabled={action.isPending} onClick={() => send("/scan")}>
              Scan again
            </Button>
          )}
          <Button
            variant={now.state === "paused" ? "secondary" : "primary"}
            onClick={() => void navigate("/")}
          >
            {now.state === "running" ? "Keep using Kura" : "Go to Home"}
          </Button>
        </div>
      </header>

      <EngineProblem queries={[scan, folders]} />
      {action.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          {action.error.message}
        </p>
      )}
      {now.state === "failed" && now.problem && (
        <Failed problem={now.problem} onTools={() => void navigate("/setup?step=tools")} />
      )}
      {now.unavailable.map((path) => (
        <p
          key={path}
          role="status"
          className="animate-fade-up rounded-18 border border-edge bg-glass px-4.5 py-3.5 text-14"
        >
          <strong>{path} isn't connected.</strong> Kura scans it when the drive is back, and its
          files stay as they were.
        </p>
      ))}

      <Progress scan={now} />

      <div className="grid animate-fade-up grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-4 [animation-delay:200ms]">
        <Note icon={<FolderTree size={18} />} title="Any folder layout works">
          One folder per anime, franchises with sub-folders, or everything mixed in Downloads. Kura
          finds every video wherever it is.
        </Note>
        <Note icon={<Timer size={18} />} title="Stop any time">
          A paused or interrupted scan carries on where it stopped. Later scans only read new and
          changed files, so they take seconds.
        </Note>
      </div>
    </>
  );
}

function Progress({ scan }: { scan: Scan }) {
  const percent =
    scan.stage === "finding" || scan.toRead === 0
      ? scan.stage === "done"
        ? 100
        : 0
      : Math.round((scan.read / scan.toRead) * 100);
  const finding = scan.stage === "finding";
  const reading = scan.stage === "reading";

  return (
    <section
      aria-label="Scan progress"
      className="flex animate-fade-up flex-col gap-6 rounded-24 border border-edge bg-glass p-7 [animation-delay:120ms]"
    >
      <div className="flex flex-wrap items-center gap-8">
        <Ring percent={percent} read={scan.read} toRead={scan.toRead} />
        <ol className="flex flex-[1_1_280px] flex-col gap-4">
          <StepLine
            state={finding ? "now" : "done"}
            title="Find every file"
            text={
              scan.found
                ? `${count(scan.found)} ${scan.found === 1 ? "video" : "videos"}`
                : "Looking through your folders"
            }
          />
          <StepLine
            state={reading ? "now" : finding ? "later" : "done"}
            title="Read length and quality"
            text="Resolution, codecs, audio and subtitle languages"
          />
        </ol>
        <div className="grid flex-[1_1_300px] grid-cols-2 gap-3">
          <Tile value={scan.found} label="videos found" />
          <Tile value={scan.read} label={scan.state === "done" ? "read" : "read so far"} />
          <Tile value={scan.toRead - scan.read} label="still to read" />
          <Tile value={scan.problems} label="couldn't be read" />
        </div>
      </div>
      <div className="flex flex-col gap-2.5">
        <div className="h-1.5 overflow-hidden rounded-3 bg-track">
          <div
            className="h-full rounded-3 bg-accent transition-[width] duration-320 ease-cinema"
            style={{ width: `${percent}%` }}
          />
        </div>
        {scan.current && (
          <p className="flex min-w-0 items-center gap-2 text-12 text-fg-muted">
            <span
              aria-hidden="true"
              className="size-1.5 shrink-0 animate-pulse rounded-full bg-accent"
            />
            {finding ? "Looking at" : "Reading"}
            <span className="truncate font-mono text-fg-soft">{scan.current}</span>
          </p>
        )}
      </div>
    </section>
  );
}

function Ring({ percent, read, toRead }: { percent: number; read: number; toRead: number }) {
  const circumference = 2 * Math.PI * 70;
  return (
    <div className="relative size-40 shrink-0">
      <svg viewBox="0 0 160 160" className="-rotate-90 size-40" aria-hidden="true">
        <circle cx="80" cy="80" r="70" fill="none" strokeWidth="10" className="stroke-track" />
        <circle
          cx="80"
          cy="80"
          r="70"
          fill="none"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - percent / 100)}
          className="stroke-accent transition-[stroke-dashoffset] duration-600 ease-cinema"
        />
      </svg>
      <div
        role="progressbar"
        aria-label="Files read"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        className="absolute inset-0 flex flex-col items-center justify-center"
      >
        <span className="font-extrabold text-36 tracking-[-0.02em]">{percent}%</span>
        <span className="font-mono text-11 text-fg-muted">
          {count(read)} / {count(toRead)}
        </span>
      </div>
    </div>
  );
}

function StepLine(props: { state: "done" | "now" | "later"; title: string; text: string }) {
  return (
    <li className="flex items-start gap-3">
      <span
        aria-hidden="true"
        className={cn(
          "mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full",
          props.state === "done" && "bg-accent text-on-accent",
          props.state === "now" && "border-2 border-accent",
          props.state === "later" && "border-2 border-line-strong",
        )}
      >
        {props.state === "done" && <Check size={13} strokeWidth={3.4} />}
        {props.state === "now" && <span className="size-2 animate-pulse rounded-full bg-accent" />}
      </span>
      <span className="flex flex-col">
        <span
          className={cn(
            "font-extrabold text-14",
            props.state === "now" && "text-accent-fg",
            props.state === "later" && "text-fg-muted",
          )}
        >
          {props.title}
          <span className="sr-only">
            {props.state === "done"
              ? ", done"
              : props.state === "now"
                ? ", in progress"
                : ", to come"}
          </span>
        </span>
        <span className="text-12 text-fg-muted">{props.text}</span>
      </span>
    </li>
  );
}

function Tile({ value, label }: { value: number; label: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-16 bg-white/4 px-4 py-3.5">
      <span className="font-extrabold text-26 tracking-[-0.02em]">{count(Math.max(value, 0))}</span>
      <span className="text-12 text-fg-muted">{label}</span>
    </div>
  );
}

function Failed({ problem, onTools }: { problem: string; onTools: () => void }) {
  const needsTools = problem.includes("ffmpeg");
  return (
    <section
      role="alert"
      className="flex animate-fade-up flex-col gap-3 rounded-18 border border-broken/26 bg-broken/7 px-4.5 py-4"
    >
      <p>{problem}</p>
      {needsTools && (
        <div>
          <Button variant="primary" size="sm" onClick={onTools}>
            Get ffmpeg
          </Button>
        </div>
      )}
    </section>
  );
}

function Note({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="flex items-start gap-3.5 rounded-20 border border-edge bg-glass px-5 py-4.5">
      <span
        aria-hidden="true"
        className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-accent/12 text-accent-fg"
      >
        {icon}
      </span>
      <div className="flex flex-col gap-1">
        <h2 className="font-extrabold text-14">{title}</h2>
        <p className="text-13 text-fg-muted">{children}</p>
      </div>
    </section>
  );
}

function eyebrow(scan: Scan): string {
  if (scan.state === "done") return "Scan finished";
  if (scan.state === "paused") return "Scan paused";
  if (scan.state === "failed") return "Scan stopped";
  return "Scanning";
}

function subtitle(scan: Scan): string {
  const started = scan.startedAt ? `Started ${clock(scan.startedAt)}` : "Not scanned yet";
  switch (scan.state) {
    case "running":
      return `${started} · ${timeLeft(scan.secondsLeft)} · nothing is renamed or moved`;
    case "paused":
      return `Paused · ${count(scan.read)} of ${count(scan.toRead)} read · nothing is renamed or moved`;
    case "done":
      return `${count(scan.found)} ${scan.found === 1 ? "video" : "videos"} · finished ${
        scan.finishedAt ? clock(scan.finishedAt) : ""
      } · nothing was renamed or moved`;
    case "failed":
      return `${started} · nothing was renamed or moved`;
    case "idle":
      return "Nothing is renamed or moved: a scan only looks.";
  }
}

function mapping(paths: string[]): string {
  if (paths.length === 0) return "your folders";
  if (paths.length === 1) return paths[0] ?? "";
  return `${paths.length} folders`;
}

function timeLeft(seconds: number | null): string {
  if (seconds === null) return "working out the time left";
  if (seconds < 60) return "less than a minute left";
  const minutes = Math.round(seconds / 60);
  return minutes === 1 ? "about a minute left" : `about ${minutes} minutes left`;
}

function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function count(value: number): string {
  return value.toLocaleString("en-GB");
}
