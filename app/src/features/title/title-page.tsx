import { AudioLines, FileText, Play } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { Breadcrumb, LIBRARY } from "@/components/breadcrumb";
import { type Asking, ConfirmDelete, Deleted, DeleteIcon, useDeleting } from "@/components/delete";
import { EngineProblem } from "@/components/engine-problem";
import { Markdown } from "@/components/markdown";
import { Poster } from "@/components/poster";
import { HeaderSkeleton, Loading, PanelSkeleton } from "@/components/skeleton";
import { StatusLegend, StatusShape, statusWord } from "@/components/status";
import { Button } from "@/components/ui/button";
import { type PlayItem, usePlayer, usePlayingFile } from "@/features/player/player-context";
import {
  type EpisodeState,
  type SeasonCount,
  type TidyResult,
  type TitleDetail,
  type TitleFile,
  useFranchiseMissing,
  useReport,
  useTitle,
} from "@/lib/engine";
import { openFolder, showInFolder, useExplorer } from "@/lib/explorer";
import { files, kindWord } from "@/lib/kinds";
import { share } from "@/lib/share";
import { cn } from "@/lib/utils";

/** One anime or film: how much of it is there, its seasons and episode map, what's missing, its
 * specials and OVAs apart, its videos, and the gap analysis next to it. */
export function TitlePage() {
  const { id } = useParams();
  const titleId = Number(id);
  const title = useTitle(titleId);
  // Files that didn't fit the match the owner just gave it.
  const unfit = (useLocation().state as { waiting?: number } | null)?.waiting ?? 0;
  // Deleting asks first, beside what goes; right after, the page says so and offers it back.
  const [asking, setAsking] = useState<Asking | null>(null);
  const [deleted, setDeleted] = useState<TidyResult | null>(null);
  const deleting = useDeleting((result) => {
    setAsking(null);
    setDeleted(result);
  });
  const ask = (next: Asking) => {
    deleting.reset();
    setDeleted(null);
    setAsking(next);
  };
  const confirm = (where: string) =>
    asking?.where === where ? (
      <ConfirmDelete
        asking={asking}
        busy={deleting.busy}
        problem={deleting.problem}
        onConfirm={() => deleting.delete(asking.files)}
        onCancel={() => setAsking(null)}
      />
    ) : null;

  if (!title.data) {
    return (
      <>
        <Breadcrumb trail={[LIBRARY]} current="…" />
        <EngineProblem queries={[title]} />
        <Loading label="Loading the title" queries={[title]}>
          <HeaderSkeleton />
          <div className="flex flex-wrap items-start gap-5">
            <div className="flex min-w-0 flex-[1.4_1_460px] flex-col gap-5">
              <PanelSkeleton rows={4} />
              <PanelSkeleton rows={3} />
            </div>
            <div className="flex min-w-0 flex-[1_1_340px] flex-col gap-5">
              <PanelSkeleton rows={3} />
            </div>
          </div>
        </Loading>
      </>
    );
  }
  const found = title.data;
  const numbered = found.episodes.filter((episode) => episode.season > 0);
  const specials = found.episodes.filter((episode) => episode.season === 0);

  return (
    <>
      <Breadcrumb
        trail={
          found.franchise
            ? [LIBRARY, { label: found.franchise.name, to: `/franchises/${found.franchise.id}` }]
            : [LIBRARY]
        }
        current={found.name}
      />
      <Header title={found} onAsk={ask} />
      {confirm("title")}
      {deleted && <Deleted result={deleted} onPutBack={() => setDeleted(null)} />}
      {unfit > 0 && <Unfit count={unfit} />}
      <EngineProblem queries={[title]} />
      {found.seasons.length > 0 && (
        <div className="flex flex-wrap items-start gap-5">
          <div className="flex min-w-0 flex-[1.4_1_460px] flex-col gap-5">
            <Seasons
              seasons={found.seasons}
              episodes={numbered}
              videos={found.videos}
              onAsk={ask}
              confirm={asking?.where.startsWith("season-") ? confirm(asking.where) : null}
            />
            <EpisodeMap episodes={numbered} />
            <MissingAndBroken title={found} episodes={numbered} />
          </div>
          <div className="flex min-w-0 flex-[1_1_340px] flex-col gap-5">
            {specials.length > 0 && <Specials episodes={specials} />}
            <ReportPanel titleId={found.id} />
          </div>
        </div>
      )}
      <Videos title={found} onAsk={ask} confirm={confirm} />
    </>
  );
}

function Unfit({ count }: { count: number }) {
  const navigate = useNavigate();
  return (
    <section
      aria-label="Files that didn't fit"
      className="flex animate-fade-up flex-wrap items-center justify-between gap-3 rounded-20 border border-edge bg-glass px-5 py-4 shadow-panel"
    >
      <span className="text-13">
        {count === 1 ? "1 file didn't" : `${count} files didn't`} fit this match.{" "}
        {count === 1 ? "It waits" : "They wait"} for you in Need a match.
      </span>
      <Button size="sm" onClick={() => void navigate("/match")}>
        Match {count === 1 ? "it" : "them"}
      </Button>
    </section>
  );
}

function Header({ title, onAsk }: { title: TitleDetail; onAsk: (asking: Asking) => void }) {
  const navigate = useNavigate();
  const explorer = useExplorer();
  // What its franchise lacks, on the franchise's page: a title alone in the library has one too.
  // A title whose videos are all gone has no franchise left to show.
  const franchiseId = title.franchise?.id ?? title.id;
  const missing = useFranchiseMissing(franchiseId);
  const lacking = title.files > 0 && !missing.isError ? (missing.data?.titles.length ?? 0) : 0;
  const seasons = title.seasons.length;
  const facts = [
    title.year ? String(title.year) : null,
    seasons > 0 ? `${seasons} ${seasons === 1 ? "season" : "seasons"}` : null,
    title.aired > 0 ? `${title.aired} episodes` : null,
    title.kind === "movie" || title.aired === 0 ? files(title.files) : null,
    title.franchise ? `part of ${title.franchise.name}` : null,
  ].filter(Boolean);

  return (
    <section
      aria-label={title.name}
      className="flex animate-fade-up flex-wrap items-center gap-6 rounded-24 border border-edge bg-glass p-6 shadow-panel"
    >
      <Poster title={title} className="w-30 shrink-0" />
      <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex h-6.5 items-center rounded-full bg-accent px-2.5 font-extrabold text-12 text-on-accent">
            {kindWord(title.kind)}
          </span>
          <span className="text-12 text-fg-muted">
            {title.source === "tmdb" ? "Matched on TMDB and AniList" : "Matched on AniList"}
          </span>
          {title.airing && <span className="text-12 text-accent-fg">Still airing</span>}
        </div>
        <h1 className="type-title">{title.name}</h1>
        <span className="text-14 text-fg-muted">{facts.join(" · ")}</span>
        {title.folder && (
          <span className="font-mono text-12 text-fg-soft [overflow-wrap:anywhere]">
            {title.folder}
          </span>
        )}
        <div className="flex flex-wrap gap-2.5 pt-1.5">
          {title.folder && (
            <Button size="sm" onClick={() => explorer.run(() => openFolder(title.folder ?? ""))}>
              Open folder
            </Button>
          )}
          <Button size="sm" onClick={() => void navigate(`/match?title=${title.id}`)}>
            Change match
          </Button>
          {lacking > 0 && (
            <Button size="sm" asChild>
              <Link to={`/franchises/${franchiseId}?missing`}>
                Missing titles <span className="font-mono text-12 text-fg-muted">{lacking}</span>
              </Link>
            </Button>
          )}
          {title.videos.length > 0 && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onAsk({ what: title.name, where: "title", files: title.videos })}
            >
              Delete
            </Button>
          )}
        </div>
        {explorer.problem && (
          <p role="alert" className="text-13 text-broken-fg">
            {explorer.problem}
          </p>
        )}
      </div>
      {title.aired > 0 && (
        <div className="flex flex-col items-center gap-1">
          <span className="font-extrabold text-36 tracking-[-0.02em]">
            {share(title.present, title.aired)}%
          </span>
          <span className="text-12 text-fg-muted">
            {title.present} of {title.aired} episodes
          </span>
        </div>
      )}
    </section>
  );
}

function Seasons(props: {
  seasons: SeasonCount[];
  episodes: EpisodeState[];
  videos: TitleFile[];
  onAsk: (asking: Asking) => void;
  confirm: ReactNode;
}) {
  const { seasons, episodes } = props;
  return (
    <Panel id="seasons-title" title="Seasons" note="Season folders and order, as TMDB numbers them">
      <ul className="flex flex-col">
        {seasons.map((season) => {
          const mine = episodes.filter((episode) => episode.season === season.season);
          const files = props.videos.filter((video) => video.season === season.season);
          return (
            <li
              key={season.season}
              className="grid min-h-10 grid-cols-[5.5rem_1fr_3.5rem_7rem_2rem] items-center gap-3 border-rule border-b text-13 last:border-b-0"
            >
              <span className="font-bold">Season {season.season}</span>
              <span className="flex h-2 overflow-hidden rounded-3" aria-hidden="true">
                {mine.map((episode) => (
                  <StatusShape
                    key={episode.number}
                    state={episode.state}
                    className="status-joined h-full flex-1 rounded-none"
                  />
                ))}
              </span>
              <span className="text-right font-mono text-12">
                {season.present}/{season.aired}
              </span>
              <span className="text-12 text-fg-muted">{seasonWord(season, mine)}</span>
              {files.length > 0 ? (
                <DeleteIcon
                  label={`Delete season ${season.season}`}
                  onClick={() =>
                    props.onAsk({
                      what: `season ${season.season}`,
                      where: `season-${season.season}`,
                      files,
                    })
                  }
                />
              ) : (
                <span />
              )}
            </li>
          );
        })}
      </ul>
      {props.confirm}
    </Panel>
  );
}

/** Every numbered episode by its state, status by shape: a row of squares to each season, so a
 * long show reads season by season. */
function EpisodeMap({ episodes }: { episodes: EpisodeState[] }) {
  const counted = new Map(episodes.map((episode, index) => [key(episode), index + 1]));
  return (
    <Panel id="map-title" title="Episode map" note="Hover a square for the episode">
      <div className="flex flex-col gap-2.5">
        {seasonsOf(episodes).map(([season, mine]) => (
          <div key={season} className="grid grid-cols-[5rem_1fr] items-start gap-3">
            <span className="font-bold text-12 text-fg-muted leading-3">Season {season}</span>
            <div
              role="img"
              aria-label={`Season ${season}: ${statesIn(mine)}`}
              className="flex flex-wrap gap-1"
            >
              {mine.map((episode) => (
                <span
                  key={key(episode)}
                  className="flex"
                  title={`S${pad(episode.season)}E${pad(episode.number)} · episode ${counted.get(
                    key(episode),
                  )}${episode.name ? ` · ${episode.name}` : ""} · ${statusWord(
                    episode.state,
                  ).toLowerCase()}`}
                >
                  <StatusShape state={episode.state} className="size-3" />
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
      <StatusLegend states={[...new Set(episodes.map((episode) => episode.state))]} />
    </Panel>
  );
}

/** The episodes by season, in order: [season, its episodes]. */
function seasonsOf(episodes: EpisodeState[]): [number, EpisodeState[]][] {
  const seasons = new Map<number, EpisodeState[]>();
  for (const episode of episodes) {
    const mine = seasons.get(episode.season);
    if (mine) mine.push(episode);
    else seasons.set(episode.season, [episode]);
  }
  return [...seasons];
}

/** "29 ready, 1 broken, 2 missing": how many of each state, in the order they first come. */
function statesIn(episodes: EpisodeState[]): string {
  const counts = new Map<EpisodeState["state"], number>();
  for (const episode of episodes) counts.set(episode.state, (counts.get(episode.state) ?? 0) + 1);
  return [...counts]
    .map(([state, count]) => `${count} ${statusWord(state).toLowerCase()}`)
    .join(", ");
}

function MissingAndBroken({ title, episodes }: { title: TitleDetail; episodes: EpisodeState[] }) {
  const absolute = new Map(episodes.map((episode, index) => [key(episode), index + 1]));
  const rows = runs(
    episodes.filter((episode) => episode.state === "missing" || episode.state === "broken"),
  );
  return (
    <Panel id="gaps-title" title="Missing and broken">
      {rows.length === 0 ? (
        <p className="text-13 text-fg-muted">
          {title.upcoming > 0
            ? `Every aired episode is here. ${title.upcoming} still to air.`
            : "Every episode is here."}
        </p>
      ) : (
        <ul className="grid grid-cols-[1rem_auto_1fr] gap-x-3">
          {rows.map(({ first, last, count }) => (
            <li
              key={key(first)}
              className="col-span-3 grid min-h-10 grid-cols-subgrid items-center border-rule border-b text-13 last:border-b-0"
            >
              <StatusShape state={first.state} className="size-3" />
              <span className="font-mono">
                S{pad(first.season)}E{pad(first.number)}
                {count > 1 && `–E${pad(last.number)}`}
              </span>
              <span className="text-fg-muted">
                {count > 1 ? (
                  `Episodes ${absolute.get(key(first))} to ${absolute.get(key(last))} · ${count} missing`
                ) : (
                  <>
                    Episode {absolute.get(key(first))}
                    {first.name && !first.name.startsWith("Episode ") ? ` · ${first.name}` : ""}
                    {` · ${first.state === "broken" ? "won't play" : "missing"}`}
                    {first.aired ? ` · aired ${day(first.aired)}` : ""}
                  </>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

type Run = { first: EpisodeState; last: EpisodeState; count: number };

/** Missing episodes in a row within a season: three or more read as one range, as the gap
 * analysis lists them. A broken episode always stands alone: it needs replacing. */
function runs(episodes: EpisodeState[]): Run[] {
  const found: Run[] = [];
  for (const episode of episodes) {
    const run = found.at(-1);
    if (
      run &&
      run.last.state === "missing" &&
      episode.state === "missing" &&
      run.last.season === episode.season &&
      run.last.number + 1 === episode.number
    ) {
      run.last = episode;
      run.count += 1;
    } else {
      found.push({ first: episode, last: episode, count: 1 });
    }
  }
  return found.flatMap((run) =>
    run.count === 2
      ? [
          { first: run.first, last: run.first, count: 1 },
          { first: run.last, last: run.last, count: 1 },
        ]
      : [run],
  );
}

function Specials({ episodes }: { episodes: EpisodeState[] }) {
  const missing = episodes.filter((episode) => episode.state === "missing").length;
  return (
    <Panel
      id="specials-title"
      title="Specials and OVAs"
      note={missing > 0 ? `${missing} not in the library · never counted as missing` : "All here"}
    >
      <ul className="flex flex-col">
        {episodes.map((episode) => (
          <li
            key={key(episode)}
            className="grid min-h-9 grid-cols-[1rem_4.5rem_1fr] items-center gap-3 border-rule border-b text-13 last:border-b-0"
          >
            <StatusShape state={episode.state} className="size-3" />
            <span className="font-mono">S00E{pad(episode.number)}</span>
            <span className="truncate text-fg-muted">
              {episode.name ?? "Special"}
              {episode.aired ? ` · ${day(episode.aired)}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function ReportPanel({ titleId }: { titleId: number }) {
  const report = useReport(titleId);
  return (
    <Panel
      id="report-title"
      title="Gap Analysis"
      note="Rewritten after every scan"
      icon={<FileText size={16} />}
    >
      {report.data ? (
        <>
          <div className="max-h-[28rem] overflow-auto rounded-12 bg-inset px-4 py-3.5">
            <Markdown text={report.data.text} />
          </div>
          <span className="font-mono text-11 text-fg-muted [overflow-wrap:anywhere]">
            {report.data.path}
          </span>
          <ReportActions path={report.data.path} text={report.data.text} />
        </>
      ) : (
        <p className="text-13 text-fg-muted">
          {report.isPending
            ? "…"
            : "Kura writes it next to the show once its videos have a folder of their own: tidying up gives them one."}
        </p>
      )}
    </Panel>
  );
}

function ReportActions({ path, text }: { path: string; text: string }) {
  const [copied, setCopied] = useState(false);
  const explorer = useExplorer();
  return (
    <div className="flex flex-wrap items-center gap-2.5">
      <Button size="sm" onClick={() => explorer.run(() => showInFolder(path))}>
        Show in folder
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={() =>
          void navigator.clipboard.writeText(text).then(() => {
            setCopied(true);
          })
        }
      >
        {copied ? "Copied" : "Copy"}
      </Button>
      {explorer.problem && (
        <p role="alert" className="basis-full text-13 text-broken-fg">
          {explorer.problem}
        </p>
      )}
    </div>
  );
}

function Videos(props: {
  title: TitleDetail;
  onAsk: (asking: Asking) => void;
  confirm: (where: string) => ReactNode;
}) {
  const { title } = props;
  const { play } = usePlayer();
  const playing = usePlayingFile();
  if (title.videos.length === 0) return null;
  // Each plays with the ones after it next, in the page's order.
  const items = title.videos.map((video) => playItem(title, video));
  return (
    <Panel
      id="videos-title"
      title={title.kind === "movie" ? "Its file" : "Videos"}
      note={files(title.videos.length)}
    >
      <ul className="flex flex-col">
        {title.videos.map((video, index) => (
          <li
            key={video.id}
            className="flex min-h-10 flex-wrap items-center gap-x-3 gap-y-1 border-rule border-b py-1.5 text-12 last:border-b-0"
          >
            {video.season !== null && video.episode !== null && (
              <span
                className={cn(
                  "w-18 shrink-0 font-mono",
                  playing === video.id && "font-bold text-accent-fg",
                )}
              >
                S{pad(video.season)}E{pad(video.episode)}
                {video.episodeEnd ? `-E${pad(video.episodeEnd)}` : ""}
              </span>
            )}
            <span className="min-w-0 flex-[1_1_260px] font-mono text-fg-soft [overflow-wrap:anywhere]">
              {video.path}
            </span>
            {playing === video.id ? (
              <span className="font-bold text-accent-fg">Playing</span>
            ) : (
              <span className="text-fg-muted">
                {video.problem
                  ? "won't play"
                  : video.height
                    ? `${video.height}p · ${video.codec ?? ""}`
                    : ""}
              </span>
            )}
            {/* The same button while it plays, so a keyboard keeps its place. */}
            {!video.problem && (
              <button
                type="button"
                aria-label={`${playing === video.id ? "Playing" : "Play"} ${videoName(video)}`}
                onClick={() => {
                  if (playing !== video.id) play(items, index);
                }}
                className={cn(
                  "press inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full border",
                  playing === video.id
                    ? "border-transparent text-accent-fg"
                    : "border-field-edge bg-field text-fg",
                )}
              >
                {playing === video.id ? (
                  <AudioLines size={16} strokeWidth={2.2} aria-hidden="true" />
                ) : (
                  <Play size={14} fill="currentColor" aria-hidden="true" />
                )}
              </button>
            )}
            <DeleteIcon
              label={`Delete ${videoName(video)}`}
              onClick={() =>
                props.onAsk({ what: videoName(video), where: `video-${video.id}`, files: [video] })
              }
            />
            {props.confirm(`video-${video.id}`) && (
              <div className="basis-full pb-2">{props.confirm(`video-${video.id}`)}</div>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

/** A video as the player names it: "Dragon Ball Z · S01E05" and its episode's title, or the
 * film's name, or its file's name. */
function playItem(title: TitleDetail, video: TitleFile): PlayItem {
  const numbered = video.season !== null && video.episode !== null;
  const episode = title.episodes.find(
    (each) => each.season === video.season && each.number === video.episode,
  );
  const name = video.path.split("\\").at(-1) ?? video.path;
  return {
    fileId: video.id,
    label: numbered ? `${title.name} · ${videoName(video)}` : title.name,
    name: numbered ? (episode?.name ?? null) : name,
    path: video.path,
  };
}

/** "S01E03", "S01E03-E04", or the file's name when it has no episode number. */
function videoName(video: TitleFile): string {
  if (video.season === null || video.episode === null) {
    return video.path.split("\\").at(-1) ?? video.path;
  }
  const last = video.episodeEnd ? `-E${pad(video.episodeEnd)}` : "";
  return `S${pad(video.season)}E${pad(video.episode)}${last}`;
}

function Panel(props: {
  id: string;
  title: string;
  note?: string;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      aria-labelledby={props.id}
      className="flex animate-fade-up flex-col gap-3.5 rounded-22 border border-edge bg-glass p-5 shadow-panel"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id={props.id} className="inline-flex items-center gap-2 font-extrabold text-16">
          {props.icon && (
            <span aria-hidden="true" className="text-accent-fg">
              {props.icon}
            </span>
          )}
          {props.title}
        </h2>
        {props.note && <span className="text-12 text-fg-muted">{props.note}</span>}
      </div>
      {props.children}
    </section>
  );
}

function seasonWord(season: SeasonCount, episodes: EpisodeState[]): string {
  const missing = season.aired - season.present;
  const broken = episodes.filter((episode) => episode.state === "broken").length;
  const toAir = season.total - season.aired;
  if (missing > 0) return `${missing} missing`;
  if (broken > 0) return `${broken} broken`;
  if (toAir > 0) return `${toAir} still to air`;
  return "complete";
}

function key(episode: EpisodeState): string {
  return `${episode.season}-${episode.number}`;
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function day(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
