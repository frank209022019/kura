import { useState } from "react";
import { Button } from "@/components/ui/button";
import { type Damage, restartEngine, useRecordsAction } from "@/lib/engine";
import { madeAt } from "@/lib/format";

/**
 * Kura's records are damaged past use (kura.db won't open): the engine answers nothing else, so
 * this stands in for every page till a way back is taken. The newest backup that opens takes the
 * records back to when it was made; with none, Kura starts again with new records, as on its
 * first day. The damaged file stays beside them either way, and the library isn't touched.
 */
export function DamagedRecords({ damage }: { damage: Damage }) {
  const action = useRecordsAction();
  const [starting, setStarting] = useState(false);
  const [trying, setTrying] = useState(false); // starting again as it was, to look once more
  const when = damage.made ? madeAt(damage.made) : null;

  function take(path: string) {
    action.mutate(
      { path },
      {
        onSuccess: () => {
          setStarting(true);
          void restartEngine();
        },
      },
    );
  }

  return (
    <>
      <header className="page-top flex max-w-2xl animate-fade-up flex-col gap-1.5">
        <h1 className="type-title">Kura's records are damaged</h1>
        <p className="text-14 text-fg-muted">
          Kura can't read kura.db, where it keeps what it knows about your library. Your anime files
          are as they were.
        </p>
      </header>
      <section
        aria-label="The way back"
        className="flex max-w-2xl animate-fade-up flex-col items-start gap-4 rounded-24 border border-edge bg-glass p-6"
      >
        {starting ? (
          <p role="status" className="text-15">
            {trying
              ? "Kura is starting again, to look at its records once more."
              : `Kura is starting again ${when ? `with the backup from ${when}` : "with new records"}.`}
          </p>
        ) : when ? (
          <>
            <p className="text-15">
              The newest backup that opens is from {when}. Restoring it takes Kura's records back to
              then.
            </p>
            <Button
              variant="primary"
              disabled={action.isPending}
              onClick={() => take("/records/restore")}
            >
              Restore the backup from {when}
            </Button>
          </>
        ) : (
          <>
            <p className="text-15">
              No backup opens either. Kura can start again with new records, as on its first day:
              you choose your folders again, and nothing in them changes.
            </p>
            <Button
              variant="primary"
              disabled={action.isPending}
              onClick={() => take("/records/new")}
            >
              Start with new records
            </Button>
          </>
        )}
        {action.error && (
          <p role="alert" className="text-13 text-broken-fg">
            {action.error.message}
          </p>
        )}
        <p className="text-12 text-fg-faint">
          Kura keeps the damaged file beside its records, as it is. SQLite says: {damage.problem}.
          If the disk was only busy a moment, trying again may be all it needs.
        </p>
        {!starting && (
          <Button
            size="sm"
            variant="ghost"
            disabled={action.isPending}
            onClick={() => {
              setStarting(true);
              setTrying(true);
              void restartEngine();
            }}
          >
            Try again
          </Button>
        )}
      </section>
    </>
  );
}
