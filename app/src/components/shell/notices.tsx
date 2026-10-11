import { listen } from "@tauri-apps/api/event";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { Button } from "@/components/ui/button";

/** A note from the engine. Mirrors `Notice` in app/src-tauri/src/tray.rs. */
interface Notice {
  title: string;
  body: string;
  /** Where in Kura it leads: "/titles/12". */
  link: string | null;
}

const SHOWN_FOR = 12_000; // milliseconds a note stays

/**
 * What the engine tells while the window is open (a batch done, the queue paused), one note at a
 * time at the foot of the window, for a few seconds. Away from the window, Windows shows them.
 */
export function Notices() {
  const [notice, setNotice] = useState<Notice | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const stopListening = listen<Notice>("notice", (event) => setNotice(event.payload));
    return () => {
      stopListening.then((unlisten) => unlisten());
    };
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), SHOWN_FOR);
    return () => clearTimeout(timer);
  }, [notice]);

  if (!notice) return null;
  const { link } = notice;
  return (
    <div
      role="status"
      className="fixed bottom-6 left-1/2 z-10 flex w-[min(30rem,calc(100vw-3rem))] -translate-x-1/2 animate-pop items-center gap-3.5 rounded-18 bg-featured px-4 py-3.5 text-white shadow-toast"
    >
      <span
        aria-hidden="true"
        className="relative size-11 shrink-0 overflow-hidden rounded-12 bg-[#2449b8]"
      >
        <span className="absolute -top-2.5 -right-2.5 size-8 rounded-full bg-featured-orb" />
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="font-extrabold">{notice.title}</span>
        <span className="text-12 text-white/80">{notice.body}</span>
      </span>
      {link && (
        <Button
          size="sm"
          variant="primary"
          onClick={() => {
            setNotice(null);
            void navigate(link);
          }}
        >
          View
        </Button>
      )}
    </div>
  );
}
