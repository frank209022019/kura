import { EmptyState } from "@/components/empty-state";
import type { Section } from "@/components/shell/sections";

/** Stands in for a section until it is built (see docs/design/ for how it will look). */
export function NotBuiltPage({ section }: { section: Section }) {
  return (
    <>
      <h1 className="type-title animate-fade-up">{section.label}</h1>
      <EmptyState title="Not built yet">{section.summary}</EmptyState>
    </>
  );
}
