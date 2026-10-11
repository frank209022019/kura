import { invoke } from "@tauri-apps/api/core";

/**
 * Opens a folder in Explorer, such as a show's own folder. The shell opens only folders
 * (src-tauri/src/explorer.rs), so nothing is ever run.
 */
export function openFolder(path: string) {
  return invoke<void>("open_folder", { path });
}

/** Shows a file in Explorer, selected in its folder, such as a show's gap analysis. */
export function showInFolder(path: string) {
  return invoke<void>("show_in_folder", { path });
}
