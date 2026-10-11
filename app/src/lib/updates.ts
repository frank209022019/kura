import { useMutation, useQuery } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";

/** An update the shell has downloaded and checked. Mirrors src-tauri/src/updater.rs. */
export interface ReadyUpdate {
  version: string;
  /** The version's notes from CHANGELOG.md (Markdown), when the release has them. */
  notes: string | null;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * Checks for an update once a day and downloads it in the background.
 * Resolves to the update once it is ready to install, or null when Kura is up to date.
 * Installed builds only: a development build has nothing to update.
 */
export function useReadyUpdate() {
  return useQuery({
    queryKey: ["update"],
    queryFn: () => invoke<ReadyUpdate | null>("prepare_update"),
    enabled: import.meta.env.PROD,
    refetchInterval: DAY_MS,
    refetchOnWindowFocus: false,
    staleTime: DAY_MS,
    retry: false,
  });
}

/** Closes Kura, installs the update and opens Kura again. */
export function useInstallUpdate() {
  return useMutation({ mutationFn: () => invoke<void>("install_update") });
}

/**
 * What a version's notes list, as plain sentences: each "- " entry, with its wrapped lines
 * joined and its Markdown (links, bold, code) reduced to text.
 */
export function whatsNew(notes: string | null): string[] {
  const entries: string[] = [];
  let current: string | null = null;
  for (const raw of (notes ?? "").replaceAll("\r\n", "\n").split("\n")) {
    const line = raw.trim();
    if (line.startsWith("- ")) {
      if (current) entries.push(current);
      current = line.slice(2);
    } else if (current && line && /^\s/.test(raw)) {
      current += ` ${line}`;
    } else if (current) {
      entries.push(current);
      current = null;
    }
  }
  if (current) entries.push(current);
  return entries.map((entry) =>
    entry
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/`([^`]+)`/g, "$1"),
  );
}
