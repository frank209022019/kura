import { Outlet, useLocation } from "react-router";
import { ScreenError } from "@/components/screen-error";
import { NavRail } from "./nav-rail";
import { TitleBar } from "./title-bar";
import { UpdateCard } from "./update-card";

/**
 * The window: title bar on top, the nav rail and the current page below. Only the page scrolls:
 * the title bar and the nav rail stay where they are.
 */
export function AppShell() {
  const location = useLocation();

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
          <ScreenError>
            <Outlet />
          </ScreenError>
        </main>
      </div>
      <UpdateCard />
    </div>
  );
}
