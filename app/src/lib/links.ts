import { invoke } from "@tauri-apps/api/core";

/**
 * Opens the downloads page in the browser: every version, newest first, with what changed.
 * The shell holds the address (src-tauri/src/links.rs), so the window can't open anything else.
 */
export function openDownloadsPage() {
  return invoke<void>("open_downloads_page");
}
