import { useMutation, useQuery } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";

/** An update the shell has downloaded and checked. Mirrors src-tauri/src/updater.rs. */
export interface ReadyUpdate {
  version: string;
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
