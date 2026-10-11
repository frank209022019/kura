import { Clock, House, Layers, ListChecks, type LucideIcon, SlidersHorizontal } from "lucide-react";

export interface Section {
  path: string;
  label: string;
  icon: LucideIcon;
  /** What the section is for, as the Workflows canvas describes it. */
  summary: string;
}

/** The five places in Kura, in nav rail order. */
export const sections: Section[] = [
  {
    path: "/",
    label: "Home",
    icon: House,
    summary: "Every anime in every folder, what is missing or broken, and what to do next.",
  },
  {
    path: "/tidy",
    label: "Tidy up",
    icon: ListChecks,
    summary:
      "Sort mixed folders, give every file a clean name, settle duplicates and unknown files.",
  },
  {
    path: "/convert",
    label: "Convert",
    icon: Layers,
    summary: "See the result first, queue it, and keep a record of every file changed.",
  },
  {
    path: "/history",
    label: "History",
    icon: Clock,
    summary: "Everything Kura changed, newest first. Renames and moves can be undone at any time.",
  },
  {
    path: "/settings",
    label: "Settings",
    icon: SlidersHorizontal,
    summary: "Your data and backups, updates, and uninstalling with an export first.",
  },
];
