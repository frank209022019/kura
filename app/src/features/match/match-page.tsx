import { Check, Search } from "lucide-react";
import { RadioGroup } from "radix-ui";
import { type ReactNode, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { EmptyState, ShelfIllustration } from "@/components/empty-state";
import { EngineProblem } from "@/components/engine-problem";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import {
  type Guess,
  useChooseMatch,
  useCover,
  useIgnoreFile,
  useMatchSearch,
  useReview,
  useStill,
  type WaitingFile,
} from "@/lib/engine";
import { kindWord } from "@/lib/kinds";
import { cn } from "@/lib/utils";

type Kind = "episode" | "movie" | "special";

const KINDS = [
  { value: "episode", label: "Episode" },
  { value: "movie", label: "Movie" },
  { value: "special", label: "Special or extra" },
] as const;

/** Files Kura couldn't place surely, one at a time: which anime is this? */
export function MatchPage() {
  const review = useReview();
  const [skipped, setSkipped] = useState<number[]>([]);
  const [settled, setSettled] = useState(0);

  if (!review.data) {
    return (
      <>
        <h1 className="type-title animate-fade-up">Which anime is this?</h1>
        <EngineProblem queries={[review]} />
      </>
    );
  }
  // Skipped files go to the back of the queue for this visit.
  const queue = [...review.data].sort(
    (a, b) => Number(skipped.includes(a.id)) - Number(skipped.includes(b.id)),
  );
  const [file, ...next] = queue;
  if (!file) return <AllMatched />;

  return (
    <>
      <Breadcrumb />
      <MatchFile
        key={file.id}
        file={file}
        position={settled + 1}
        total={settled + queue.length}
        next={next}
        onSkip={() => setSkipped((before) => [...before.filter((id) => id !== file.id), file.id])}
        onSettled={(count) => setSettled((before) => before + count)}
      />
      <EngineProblem queries={[review]} />
    </>
  );
}

function MatchFile(props: {
  file: WaitingFile;
  position: number;
  total: number;
  next: WaitingFile[];
  onSkip: () => void;
  onSettled: (count: number) => void;
}) {
  const { file } = props;
  const choose = useChooseMatch();
  const ignore = useIgnoreFile();
  const [search, setSearch] = useState("");
  const found = useMatchSearch(file.id, search);
  const searching = search.trim().length >= 2;
  const guesses = searching ? (found.data ?? []) : file.guesses;
  const [picked, setPicked] = useState<number | null>(file.guesses[0]?.anilistId ?? null);
  const [kind, setKind] = useState<Kind>(asKind(file.kind));
  // An episode's number starts as its name gives it; a special's starts blank.
  const named = file.episode === null ? "" : String(file.episode);
  const [numbers, setNumbers] = useState({ episode: named, special: "" });
  const number = kind === "movie" ? "" : numbers[kind];
  const [together, setTogether] = useState(true);
  const chosen = guesses.find((guess) => guess.anilistId === picked) ?? null;
  const busy = choose.isPending || ignore.isPending;

  // 1, 2 or 3 picks a guess, as the board says, unless the owner is typing.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.target instanceof HTMLInputElement || event.ctrlKey || event.altKey) return;
      const index = ["1", "2", "3"].indexOf(event.key);
      const guess = guesses[index];
      if (guess) setPicked(guess.anilistId);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [guesses]);

  function confirm() {
    if (!chosen) return;
    const also = together ? file.alike : [];
    // The number goes only when the owner gave one its name doesn't.
    const given = number !== "" && (kind === "special" || number !== named);
    const episode = given ? Number(number) : undefined;
    choose.mutate(
      { path: `/review/${file.id}`, body: { anilistId: chosen.anilistId, kind, also, episode } },
      { onSuccess: (answer) => props.onSettled(answer.placed) },
    );
  }

  return (
    <>
      <header className="flex animate-fade-up flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-2">
          <h1 className="font-extrabold text-32 leading-[1.1] tracking-[-0.02em]">
            Which anime is this?
          </h1>
          <div className="flex items-center gap-3 text-14 text-fg-muted">
            <span>
              File {props.position} of {props.total}
            </span>
            <span className="h-1.5 w-35 overflow-hidden rounded-3 bg-track" aria-hidden="true">
              <span
                className="block h-full rounded-3 bg-accent transition-[width] duration-320 ease-cinema"
                style={{ width: `${(props.position / props.total) * 100}%` }}
              />
            </span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <Button disabled={busy} onClick={props.onSkip}>
            Skip for now
          </Button>
          <Button
            disabled={busy}
            onClick={() =>
              ignore.mutate(
                { path: `/review/${file.id}/ignore` },
                { onSuccess: () => props.onSettled(1) },
              )
            }
          >
            Not anime, ignore it
          </Button>
        </div>
      </header>

      <div className="flex flex-wrap items-start gap-5">
        <FilePanel file={file} />

        <section
          aria-labelledby="guess-title"
          className="flex min-w-0 flex-[1.3_1_420px] animate-fade-up flex-col gap-3.5 rounded-24 border border-accent/35 bg-raised p-5.5 [animation-delay:120ms]"
        >
          <div className="flex items-baseline justify-between gap-3">
            <h2 id="guess-title" className="font-extrabold text-17">
              {searching ? "Found" : "Best guesses"}
            </h2>
            {guesses.length > 1 && (
              <span className="text-12 text-fg-muted">
                Press{" "}
                {guesses
                  .slice(0, 3)
                  .map((_, index) => index + 1)
                  .join(", ")
                  .replace(/, (\d)$/, " or $1")}
              </span>
            )}
          </div>
          {guesses.length > 0 ? (
            <RadioGroup.Root
              aria-label="Pick the anime"
              value={picked === null ? "" : String(picked)}
              onValueChange={(value) => setPicked(Number(value))}
              className="flex flex-col gap-2.5"
            >
              {guesses.slice(0, searching ? 6 : 3).map((guess, index) => (
                <GuessOption key={guess.anilistId} guess={guess} index={index} file={file} />
              ))}
            </RadioGroup.Root>
          ) : (
            <p className="rounded-16 bg-white/4 px-4 py-3.5 text-13 text-fg-muted">
              {searching
                ? found.isFetching
                  ? "Searching…"
                  : "Nothing by that name. Try another spelling, or its Japanese title."
                : "Kura has no guess for this one. Search for the anime by name."}
            </p>
          )}
          <label className="flex h-11 items-center gap-2.5 rounded-full border border-white/12 bg-white/5 px-4 text-fg-muted">
            <Search size={16} aria-hidden="true" />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="None of these? Search for the anime"
              aria-label="Search for the right anime"
              className="min-w-0 flex-1 bg-transparent text-13 text-fg outline-none placeholder:text-fg-faint"
            />
          </label>
          {found.isError && (
            <p role="alert" className="text-13 text-broken-fg">
              {found.error.message}
            </p>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="font-bold text-13">It is a</span>
            <Segmented label="Kind of file" value={kind} options={KINDS} onChange={setKind} />
          </div>
          {kind !== "movie" && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <label htmlFor="match-number" className="font-bold text-13">
                {kind === "special" ? "Which special" : "Which episode"}
              </label>
              <Input
                id="match-number"
                inputMode="numeric"
                autoComplete="off"
                value={number}
                onChange={(event) => {
                  const digits = event.target.value.replace(/\D/g, "").slice(0, 4);
                  setNumbers((before) => ({ ...before, [kind]: digits }));
                }}
                placeholder={kind === "special" ? "If you know it" : "Its number"}
                className="h-10 w-36 text-right font-mono text-13 placeholder:font-sans"
              />
            </div>
          )}

          {file.alike.length > 0 && (
            <Together
              file={file}
              others={props.next.filter((other) => file.alike.includes(other.id))}
              on={together}
              onChange={setTogether}
            />
          )}

          {(choose.isError || ignore.isError) && (
            <p role="alert" className="text-13 text-broken-fg">
              {(choose.error ?? ignore.error)?.message}
            </p>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-12 text-fg-faint">
              Your choice is remembered, so a rescan never undoes it.
            </span>
            <Button variant="primary" disabled={!chosen || busy} onClick={confirm}>
              {chosen ? confirmText(chosen, kind, number) : "Pick the anime first"}
            </Button>
          </div>
        </section>
      </div>

      {props.next.length > 0 && (
        <UpNext files={props.next.slice(0, 4)} following={together ? file.alike : []} />
      )}
    </>
  );
}

function Breadcrumb() {
  return (
    <nav aria-label="Breadcrumb" className="flex animate-fade-up items-center gap-2 text-13">
      <Link to="/tidy" className="text-fg-muted underline-offset-3 hover:text-fg hover:underline">
        Tidy up
      </Link>
      <span aria-hidden="true" className="text-fg-faint">
        ›
      </span>
      <span aria-current="page" className="font-bold">
        Need a match
      </span>
    </nav>
  );
}

/** The file itself: its name, folder, three stills and what reading it showed. */
function FilePanel({ file }: { file: WaitingFile }) {
  const [name, folder] = split(file.path);
  return (
    <section
      aria-labelledby="file-title"
      className="flex min-w-0 flex-[1_1_380px] animate-fade-up flex-col gap-4 rounded-24 border border-edge bg-glass p-5.5 [animation-delay:60ms]"
    >
      <div className="flex flex-col gap-1">
        <h2 id="file-title" className="font-medium font-mono text-15 [overflow-wrap:anywhere]">
          {name}
        </h2>
        <span className="font-mono text-12 text-fg-muted [overflow-wrap:anywhere]">{folder}</span>
      </div>
      {file.minutes !== null && (
        <div className="grid grid-cols-3 gap-2">
          {[0.15, 0.5, 0.8].map((point, index) => (
            <Still
              key={point}
              fileId={file.id}
              index={index}
              at={clockTime((file.minutes ?? 0) * 60 * point)}
            />
          ))}
        </div>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-5 gap-y-2 text-13">
        <Fact label="Length">
          {file.minutes !== null ? clockTime(file.minutes * 60) : "unknown"}
        </Fact>
        <Fact label="Picture">
          {file.height ? `${file.height}p` : "unknown"}
          {file.codec ? ` · ${codecName(file.codec)}` : ""}
        </Fact>
        <Fact label="Audio">{languages(file.audio)}</Fact>
        <Fact label="Subtitles">{languages(file.subtitles)}</Fact>
        <Fact label="Size">{size(file.size)}</Fact>
        {file.group && <Fact label="Group tag">[{file.group}]</Fact>}
      </dl>
    </section>
  );
}

function Still({ fileId, index, at }: { fileId: number; index: number; at: string }) {
  const picture = useStill(fileId, index);
  return (
    <div className="flex flex-col gap-1">
      <div aria-hidden="true" className="aspect-[4/3] overflow-hidden rounded-10 bg-surface">
        {picture && <img src={picture} alt="" className="size-full object-cover" />}
      </div>
      <span className="font-mono text-11 text-fg-muted">{at}</span>
    </div>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-fg-muted">{label}</dt>
      <dd className="font-mono text-12">{children}</dd>
    </>
  );
}

function GuessOption({ guess, index, file }: { guess: Guess; index: number; file: WaitingFile }) {
  const cover = useCover(guess.cover);
  const facts = [
    guess.kind ? kindWord(guess.kind) : null,
    guess.kind !== "movie" && guess.episodes ? `${guess.episodes} episodes` : null,
    guess.minutes ? `${guess.minutes} min` : null,
  ].filter(Boolean);
  return (
    <RadioGroup.Item
      value={String(guess.anilistId)}
      className="press flex cursor-pointer items-center gap-3.5 rounded-18 border-2 border-edge bg-glass px-3.5 py-3 text-left data-[state=checked]:border-accent data-[state=checked]:bg-accent/10"
    >
      <span className="w-5.5 shrink-0 font-mono text-12 text-fg-muted">
        {index < 3 ? index + 1 : ""}
      </span>
      <span
        aria-hidden="true"
        className="relative h-16.5 w-11 shrink-0 overflow-hidden rounded-8 bg-featured"
      >
        {cover && <img src={cover} alt="" className="absolute inset-0 size-full object-cover" />}
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="font-extrabold">
          {guess.title}
          {guess.year ? ` (${guess.year})` : ""}
        </span>
        <span className="text-12 text-fg-muted">
          {file.episode !== null && guess.kind !== "movie" ? `Episode ${file.episode} · ` : ""}
          {facts.join(" · ")}
        </span>
        <span className="flex items-center gap-2 text-12">
          <span className="h-1.25 w-30 overflow-hidden rounded-3 bg-track" aria-hidden="true">
            <span
              className="block h-full rounded-3 bg-accent"
              style={{ width: `${guess.confidence}%` }}
            />
          </span>
          <span className="font-mono">{guess.confidence}%</span>
        </span>
        {guess.reasons.length > 0 && (
          <span className="text-12 text-fg-muted">{guess.reasons.join("; ")}</span>
        )}
      </span>
    </RadioGroup.Item>
  );
}

function Together(props: {
  file: WaitingFile;
  others: WaitingFile[];
  on: boolean;
  onChange: (on: boolean) => void;
}) {
  const count = props.file.alike.length;
  const tag = props.file.group ? `[${props.file.group}] ` : "";
  const numbers = props.others
    .map((other) => other.episode)
    .filter((episode): episode is number => episode !== null)
    .map((episode) => String(episode).padStart(2, "0"));
  return (
    <label className="press flex min-h-13 cursor-pointer items-center gap-3 rounded-16 border border-edge bg-glass px-3.5 py-2">
      <input
        type="checkbox"
        checked={props.on}
        onChange={(event) => props.onChange(event.target.checked)}
        className="peer sr-only"
      />
      <span
        aria-hidden="true"
        className={cn(
          "inline-flex size-5.5 shrink-0 items-center justify-center rounded-6 peer-focus-visible:outline-2 peer-focus-visible:outline-accent-fg peer-focus-visible:outline-offset-3",
          props.on ? "bg-accent text-on-accent" : "border-2 border-control",
        )}
      >
        {props.on && <Check size={12} strokeWidth={3.4} />}
      </span>
      <span className="flex flex-col">
        <span className="font-extrabold">
          Use this for the {count === 1 ? "other" : `${count} other`} {tag}
          {count === 1 ? "file" : "files"} here
        </span>
        {numbers.length > 0 && (
          <span className="text-12 text-fg-muted">
            {numbers.length === 1 ? "Episode" : "Episodes"} {listed(numbers)}, numbered from their
            names
          </span>
        )}
      </span>
    </label>
  );
}

function UpNext({ files, following }: { files: WaitingFile[]; following: number[] }) {
  return (
    <section
      aria-labelledby="next-title"
      className="flex animate-fade-up flex-col gap-2.5 rounded-22 border border-white/6 bg-white/3 px-5.5 py-5 [animation-delay:180ms]"
    >
      <h2 id="next-title" className="font-extrabold text-15">
        Up next
      </h2>
      <ul className="flex flex-col">
        {files.map((file) => {
          const [name, folder] = split(file.path);
          return (
            <li
              key={file.id}
              className="flex min-h-11 flex-wrap items-center gap-3 border-white/6 border-b last:border-b-0"
            >
              <span className="flex-[1_1_260px] font-mono text-12 [overflow-wrap:anywhere]">
                {name}
              </span>
              <span className="text-12 text-fg-muted">
                {following.includes(file.id)
                  ? "follows this choice"
                  : `${folder} · ${describe(file)}`}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function AllMatched() {
  const navigate = useNavigate();
  return (
    <>
      <h1 className="type-title animate-fade-up">Which anime is this?</h1>
      <EmptyState
        title="Every file is matched"
        illustration={<ShelfIllustration />}
        action={
          <Button variant="primary" onClick={() => void navigate("/")}>
            Go to Home
          </Button>
        }
      >
        Kura knows which anime each video is. New files are identified as they arrive.
      </EmptyState>
    </>
  );
}

function asKind(kind: WaitingFile["kind"]): Kind {
  if (kind === "movie") return "movie";
  if (kind === "special" || kind === "extra") return "special";
  return "episode";
}

function confirmText(guess: Guess, kind: Kind, number: string): string {
  if (kind === "episode" && number !== "") return `Confirm ${guess.title}, episode ${number}`;
  if (kind === "special" && number !== "") return `Confirm ${guess.title}, special ${number}`;
  return `Confirm ${guess.title}`;
}

function describe(file: WaitingFile): string {
  const length = file.minutes !== null ? clockLength(file.minutes) : "length unknown";
  if (file.kind === "dvd") return `DVD file, ${length}`;
  if (file.kind === "extra") return `extra, ${length}`;
  if (file.kind === "movie" || (file.minutes ?? 0) >= 60) return `${length}, probably a film`;
  return length;
}

function split(path: string): [string, string] {
  const at = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
  return [path.slice(at + 1), path.slice(0, at)];
}

/** 24:10, or 1:32:05 past an hour. */
function clockTime(seconds: number): string {
  const whole = Math.round(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const rest = String(whole % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

/** "1 h 32 min", or "24 min". */
function clockLength(minutes: number): string {
  const whole = Math.round(minutes);
  return whole >= 60 ? `${Math.floor(whole / 60)} h ${whole % 60} min` : `${whole} min`;
}

function size(bytes: number): string {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`;
}

const CODECS: Record<string, string> = {
  h264: "H.264",
  hevc: "HEVC",
  av1: "AV1",
  mpeg2video: "MPEG-2",
  mpeg4: "MPEG-4",
  vp9: "VP9",
};

function codecName(codec: string): string {
  return CODECS[codec] ?? codec.toUpperCase();
}

const LANGUAGES: Record<string, string> = {
  jpn: "Japanese",
  eng: "English",
  ger: "German",
  deu: "German",
  fre: "French",
  fra: "French",
  spa: "Spanish",
  ita: "Italian",
  por: "Portuguese",
  rus: "Russian",
  chi: "Chinese",
  zho: "Chinese",
  kor: "Korean",
  ara: "Arabic",
  unknown: "unnamed",
};

function languages(codes: string[]): string {
  if (codes.length === 0) return "none";
  return codes.map((code) => LANGUAGES[code] ?? code.toUpperCase()).join(", ");
}

function listed(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}
