import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";

/**
 * Light or dark: as Windows is (the default), or always one. The shell keeps the choice and gives
 * the window its theme, and the page's colours follow it (styles/tokens.css), so nothing here
 * paints. Mirrors `Look` in src-tauri/src/look.rs.
 */
export type Look = "windows" | "light" | "dark";

export const LOOKS: readonly { value: Look; label: string }[] = [
  { value: "windows", label: "Same as Windows" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

const KEY = ["shell", "look"];

/** The look chosen. */
export function useLook() {
  return useQuery({ queryKey: KEY, queryFn: () => invoke<Look>("look") });
}

/** Chooses the look, from now and at every start. */
export function useSetLook() {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (look: Look) => invoke<Look>("set_look", { look }),
    onSuccess: (look) => queries.setQueryData(KEY, look),
  });
}
