import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The core serves the build from core/cave/web/console. In development, `pnpm dev` proxies the API
// to a local CAVE (plain HTTP on 127.0.0.1:8098, development only).
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../core/cave/web/console", emptyOutDir: true, assetsDir: "assets" },
  server: {
    proxy: { "/api": { target: "http://127.0.0.1:8098", ws: true } },
    // the recipe tests read the repo's JSON schemas; nothing else outside the console is reachable
    fs: { allow: [".", "../schemas"] },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    // dialog-heavy tests (the automation editor's save diff) run past 5 s on GitHub's shared runners
    testTimeout: 15_000,
  },
});
