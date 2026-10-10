import { Outlet } from "react-router";
import { NavRail } from "./nav-rail";
import { TitleBar } from "./title-bar";
import { UpdateCard } from "./update-card";

/** The window: title bar on top, nav rail and the current page below. */
export function AppShell() {
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <TitleBar />
      <div className="flex flex-1 flex-wrap content-start items-start overflow-y-auto">
        <NavRail />
        <main
          id="main"
          className="flex min-w-0 flex-[999_1_640px] flex-col gap-8 pt-1.5 pr-8 pb-14 pl-3.5"
        >
          <Outlet />
        </main>
      </div>
      <UpdateCard />
    </div>
  );
}
