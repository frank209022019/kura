import { invoke } from "@tauri-apps/api/core";

/**
 * Opens the downloads page in the browser: every version, newest first, with what changed.
 * The shell holds the address (src-tauri/src/links.rs), so the window can't open anything else.
 */
export function openDownloadsPage() {
  return invoke<void>("open_downloads_page");
}

/** Opens TMDB's page with the account's API keys, where the key for Kura is. */
export function openTmdbApiPage() {
  return invoke<void>("open_tmdb_api_page");
}
