import { invoke } from "@tauri-apps/api/core";

/** Asks for a folder with Windows' folder picker. Null when it's cancelled. */
export function pickFolder(title: string) {
  return invoke<string | null>("pick_folder", { title });
}
