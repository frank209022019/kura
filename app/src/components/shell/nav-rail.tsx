import { Link, useLocation } from "react-router";
import { cn } from "@/lib/utils";
import { sectionOf, sections } from "./sections";

/**
 * The main navigation. A column of tiles beside the page; in a compact window (under 900 px) the
 * tiles flow into a row on top. It never scrolls with the page. The section a page sits in stays
 * lit while it's open (a title's page lights Home).
 */
export function NavRail() {
  const location = useLocation();
  const lit = sectionOf(location.pathname, location.search);
  return (
    <nav
      aria-label="Main"
      className="flex shrink-0 flex-col px-2.5 pt-2 pb-3 standard:w-24 standard:pb-5"
    >
      <div className="flex flex-wrap gap-1.5">
        {sections.map(({ path, label, icon: Icon }) => (
          <Link
            key={path}
            to={path}
            aria-current={path === lit ? "page" : undefined}
            className={cn(
              "press relative flex min-h-16 flex-[1_1_72px] flex-col items-center justify-center gap-1 rounded-16 px-1 py-1.5 font-bold text-11",
              path === lit ? "bg-accent/12 text-accent-fg" : "text-fg-muted",
            )}
          >
            <Icon size={22} strokeWidth={1.8} aria-hidden="true" />
            {label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
