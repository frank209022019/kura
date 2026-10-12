import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Vite serves the UI to Kura's window in development and bundles it for release.
// See docs/stack/react.md.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { tsconfigPaths: true }, // "@/…" imports, from tsconfig.json
  clearScreen: false, // keep the shell's Rust output visible during `tauri dev`
  // Lists every package bundled into the UI, with its licence, for the third-party notices
  // (engine/tools/third_party_notices.py).
  build: { license: { fileName: ".vite/licenses.json" } },
  server: {
    port: 1420, // must match devUrl in src-tauri/tauri.conf.json
    strictPort: true,
    watch: { ignored: ["**/src-tauri/**"] },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: { include: [/tokens\.css/] }, // a test reads the tokens file itself
    // A page's first render takes well under a second, but on a busy CI runner it has taken
    // over five, Vitest's default limit, failing tests that were fine.
    testTimeout: 15_000,
  },
});
