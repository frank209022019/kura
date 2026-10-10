import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Vite serves the UI to Kura's window in development and bundles it for release.
// See docs/stack/react.md.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { tsconfigPaths: true }, // "@/…" imports, from tsconfig.json
  clearScreen: false, // keep the shell's Rust output visible during `tauri dev`
  server: {
    port: 1420, // must match devUrl in src-tauri/tauri.conf.json
    strictPort: true,
    watch: { ignored: ["**/src-tauri/**"] },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: { include: [/tokens\.css/] }, // a test reads the tokens file itself
  },
});
