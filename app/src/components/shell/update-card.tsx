import { ArrowDownToLine } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useInstallUpdate, useReadyUpdate } from "@/lib/updates";

/** Shown once an update has downloaded in the background. */
export function UpdateCard() {
  const update = useReadyUpdate();
  const install = useInstallUpdate();
  const [later, setLater] = useState(false);

  if (!update.data || later) return null;

  return (
    <section
      aria-labelledby="update-title"
      className="fixed right-6 bottom-6 z-10 flex w-[min(26rem,calc(100vw-3rem))] animate-pop flex-col gap-4.5 rounded-28 border border-white/10 bg-dialog p-7 shadow-dialog"
    >
      <div className="flex items-center gap-3.5">
        <span className="inline-flex size-12 shrink-0 items-center justify-center rounded-full bg-accent text-on-accent">
          <ArrowDownToLine size={22} strokeWidth={2.4} aria-hidden="true" />
        </span>
        <div className="flex flex-col">
          <h2 id="update-title" className="font-extrabold text-22 tracking-[-0.01em]">
            Kura {update.data.version} is ready
          </h2>
          <span className="text-13 text-fg-muted">Downloaded in the background</span>
        </div>
      </div>
      <p className="text-13 text-fg-soft">
        Kura closes, updates and opens again. Your settings and library stay as they are.
      </p>
      <div className="flex flex-wrap gap-2.5">
        <Button variant="primary" disabled={install.isPending} onClick={() => install.mutate()}>
          Restart and update
        </Button>
        <Button variant="ghost" onClick={() => setLater(true)}>
          Later
        </Button>
      </div>
      {install.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          The update didn't start: {String(install.error)}
        </p>
      )}
    </section>
  );
}
