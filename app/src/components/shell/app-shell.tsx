import { Outlet, useLocation } from "react-router";
import { ScreenError } from "@/components/screen-error";
import { DamagedRecords } from "@/features/records/damaged-records";
import { useRecords } from "@/lib/engine";
import { NavRail } from "./nav-rail";
import { Notices } from "./notices";
import { Offline } from "./offline";
import { TitleBar } from "./title-bar";
import { UpdateCard } from "./update-card";

/**
 * The window: title bar on top, the nav rail and the current page below. Only the page scrolls:
 * the title bar and the nav rail stay where they are. While Kura's records are damaged, the way
 * back stands in for every page.
 */
export function AppShell() {
  const location = useLocation();
  const damage = useRecords().data;

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <TitleBar />
      <div className="flex min-h-0 flex-1 flex-col standard:flex-row">
        <NavRail />
        {/* A fresh start on every screen: it opens at its top, and one that failed to draw
            doesn't follow you around. */}
        <main
          key={location.pathname}
          id="main"
          className="flex min-h-0 min-w-0 flex-1 flex-col gap-8 overflow-y-auto pr-8 pb-14 pl-3.5"
        >
          <ScreenError>{damage ? <DamagedRecords damage={damage} /> : <Outlet />}</ScreenError>
        </main>
      </div>
      <UpdateCard />
      {/* Notes at the foot of the window, over the page: being offline, and what the engine
          tells of. */}
      <div className="pointer-events-none fixed bottom-6 left-1/2 z-10 flex w-[min(30rem,calc(100vw-3rem))] -translate-x-1/2 flex-col gap-3 *:pointer-events-auto">
        <Offline />
        <Notices />
      </div>
    </div>
  );
}
