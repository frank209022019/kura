import { useState } from "react";
import { EmptyState, ShelfIllustration } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { restartEngine, useEngine, useHealth } from "@/lib/engine";
import { openDownloadsPage } from "@/lib/links";
import { useReadyUpdate } from "@/lib/updates";

export function HomePage() {
  const engine = useEngine();

  return (
    <>
      <header className="flex animate-fade-up flex-col gap-1.5">
        <h1 className="type-title">Library</h1>
        <p className="text-14 text-fg-muted">No folders yet.</p>
      </header>

      {engine.state === "failed" ? (
        <EngineFailed message={engine.message} details={engine.details} />
      ) : (
        <EmptyState
          title="Your shelf is empty"
          illustration={<ShelfIllustration />}
          action={
            <Button variant="primary" disabled>
              Add a folder
            </Button>
          }
          note="Adding folders arrives with the first scan, the next part to be built."
        >
          Add a folder with anime in it. Any layout, even everything in one folder.
        </EmptyState>
      )}

      <ThisCopy />
    </>
  );
}

/** The engine isn't running: say so, say what Kura did, offer the next step. */
function EngineFailed({ message, details }: { message: string; details: string }) {
  const [retrying, setRetrying] = useState(false);

  return (
    <section
      role="alert"
      className="flex animate-fade-up flex-col gap-3 rounded-18 border border-broken/26 bg-broken/7 px-4.5 py-4"
    >
      <p>
        <strong>Kura's engine isn't running.</strong> {message} Nothing in your folders was touched.
      </p>
      {details && (
        <pre className="max-h-40 overflow-auto rounded-12 bg-inset px-3 py-2.5 font-mono text-11 text-fg-muted leading-[1.7]">
          {details}
        </pre>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="primary"
          size="sm"
          disabled={retrying}
          onClick={() => {
            setRetrying(true);
            restartEngine().finally(() => setRetrying(false));
          }}
        >
          Try again
        </Button>
        {details && (
          <Button variant="ghost" size="sm" onClick={() => navigator.clipboard.writeText(details)}>
            Copy details
          </Button>
        )}
      </div>
    </section>
  );
}

/** Engine, data folder, database and updates at a glance. */
function ThisCopy() {
  const engine = useEngine();
  const health = useHealth();
  const update = useReadyUpdate();

  const engineText = {
    starting: "Starting…",
    ready: health.data ? `Running · version ${health.data.version}` : "Running",
    failed: "Not running",
  }[engine.state];

  let updateText = "Checked in installed copies of Kura";
  if (import.meta.env.PROD) {
    if (update.isPending) updateText = "Checking…";
    else if (update.isError) updateText = `Can't check right now: ${String(update.error)}`;
    else if (update.data) updateText = `Kura ${update.data.version} is ready to install`;
    else updateText = "Up to date";
  }

  return (
    <section
      aria-labelledby="this-copy-title"
      className="flex animate-fade-up flex-col gap-3.5 rounded-22 border border-edge bg-glass p-5 [animation-delay:120ms]"
    >
      <h2 id="this-copy-title" className="font-extrabold text-16">
        This copy of Kura
      </h2>
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2.5 text-13">
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
        <dt className="text-fg-muted">Updates</dt>
        <dd>{updateText}</dd>
        <dt className="text-fg-muted">Versions</dt>
        <dd>
          <button
            type="button"
            className="cursor-pointer text-accent-fg underline-offset-3 hover:text-accent-fg-hover hover:underline"
            onClick={() => void openDownloadsPage()}
          >
            Every version and what changed
          </button>
        </dd>
      </dl>
    </section>
  );
}
