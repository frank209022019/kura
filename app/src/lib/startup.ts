import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";

const KEY = ["shell", "start-with-windows"];

/**
 * Whether Kura starts with Windows and waits in the tray. Windows keeps the answer (the shell
 * asks it, src-tauri/src/tray.rs), so it's true even when it was set before this launch.
 */
export function useStartWithWindows() {
  return useQuery({ queryKey: KEY, queryFn: () => invoke<boolean>("start_with_windows") });
}

/** Turns starting with Windows on or off. On, closing the window keeps Kura in the tray. */
export function useSetStartWithWindows() {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (on: boolean) => invoke<boolean>("set_start_with_windows", { on }),
    onSuccess: (on) => queries.setQueryData(KEY, on),
  });
}
