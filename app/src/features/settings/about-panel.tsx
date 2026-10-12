import { Link } from "react-router";
import { TmdbCredit } from "@/components/tmdb-credit";
import { useEngine, useHealth, useTmdb } from "@/lib/engine";
import { openDownloadsPage } from "@/lib/links";
import { useReadyUpdate } from "@/lib/updates";
import { Panel } from "./panel";

const LINK =
  "cursor-pointer text-accent-fg underline-offset-3 hover:text-accent-fg-hover hover:underline";

/** About Kura: this copy at a glance (engine, data folder, database, lookups and updates), its
 * licence, and whose work it stands on. */
export function AboutPanel() {
  const engine = useEngine();
  const health = useHealth();
  const tmdb = useTmdb();
  const update = useReadyUpdate();

  const engineText = { starting: "Starting…", ready: "Running", failed: "Not running" }[
    engine.state
  ];

  let updateText = "Checked in installed copies of Kura";
  if (import.meta.env.PROD) {
    if (update.isPending) updateText = "Checking…";
    else if (update.isError) updateText = `Can't check right now: ${String(update.error)}`;
    else if (update.data) updateText = `Kura ${update.data.version} is ready to install`;
    else updateText = "Up to date";
  }

  return (
    <Panel title="About Kura" note="蔵, a storehouse: a personal tool for one anime library.">
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2.5 text-13">
        <dt className="text-fg-muted">Version</dt>
        <dd className="font-mono">{health.data?.version ?? "…"}</dd>
        <dt className="text-fg-muted">Engine</dt>
        <dd className="flex items-center gap-2">
          {engine.state === "starting" && (
            <span className="size-2 animate-pulse rounded-full bg-accent" aria-hidden="true" />
          )}
          {engineText}
        </dd>
        <dt className="text-fg-muted">Data folder</dt>
        <dd className="font-mono text-12 text-fg-soft [overflow-wrap:anywhere]">
          {health.data?.dataDir ?? "…"}
        </dd>
        <dt className="text-fg-muted">Database</dt>
        <dd>{health.data ? `Ready · schema version ${health.data.schemaVersion}` : "…"}</dd>
        <dt className="text-fg-muted">Titles and artwork</dt>
        <dd>
          {tmdb.data?.connected && `TMDB connected · key ending ${tmdb.data.keyEnd}`}
          {tmdb.data && !tmdb.data.connected && (
            <>
              AniList only: no episode titles yet ·{" "}
              <Link to="/settings/titles" className={LINK}>
                Add your TMDB key
              </Link>
            </>
          )}
          {!tmdb.data && "…"}
        </dd>
        <dt className="text-fg-muted">Updates</dt>
        <dd>{updateText}</dd>
        <dt className="text-fg-muted">Versions</dt>
        <dd>
          <button type="button" className={LINK} onClick={() => void openDownloadsPage()}>
            Every version and what changed
          </button>
        </dd>
        <dt className="text-fg-muted">Licence</dt>
        <dd>MIT. Anyone may fork it; the repo takes no contributions.</dd>
      </dl>
      <p className="text-13 text-fg-muted">
        Kura stands on others' work: ffmpeg reads and converts the videos, Real-ESRGAN's anime model
        and Anime4K's shaders upscale them, AniList and TMDB say what each one is.
        THIRD-PARTY-NOTICES.txt, next to Kura, lists every part with its licence.
      </p>
      <TmdbCredit>
        This product uses the TMDB API but is not endorsed or certified by TMDB.
      </TmdbCredit>
    </Panel>
  );
}
