import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The core serves the build from core/cave/web/console. In development, `pnpm dev` proxies the API
// to a local CAVE (plain HTTP on 127.0.0.1:8098, development only).
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../core/cave/web/console", emptyOutDir: true, assetsDir: "assets" },
  server: {
    proxy: { "/api": { target: "http://127.0.0.1:8098", ws: true } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
  },
});
