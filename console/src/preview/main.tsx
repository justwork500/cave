/**
 * Design preview, development only (`pnpm dev`, then /preview.html?path=/admin/users&theme=light).
 * Renders the real console routes against sample data with the API faked in the page, so screens can be
 * photographed and measured without a server or a sign-in. Not part of the production build.
 */
import { FluentProvider } from "@fluentui/react-components";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { ThemeContext } from "../app/prefs";
import { AppRoutes } from "../app/routes";
import { type ThemeName, themes } from "../app/theme";
import "../app/app.css";
import * as F from "./fixtures";

const GET: Record<string, unknown> = {
  "/me": F.me, "/items": F.items, "/notifications": F.notifications, "/summary": F.summary,
  "/dashboards/default": { slug: "home" }, "/dashboards/home/view": F.dashboardView, "/states": F.states,
  "/areas": F.areas,
  "/users": F.users, "/groups": F.groups, "/screens": F.screens, "/tokens": F.tokens, "/audit": F.audit,
  "/signin-log": F.signins, "/automations": F.listed.automations, "/sequences": F.listed.sequences,
  "/dashboards": F.listed.dashboards, "/scripts": F.scripts, "/scripts/Stop-LabHosts.ps1": F.script,
  "/scripts/Stop-LabHosts.ps1/runs": F.scriptRuns, "/scripts/backup-photos.sh/runs": [],
  "/automations/ups-on-battery": { id: "ups-on-battery", name: "UPS on battery", yaml: F.automationYaml },
  "/automations/ups-on-battery/traces": F.traces, "/automations/porch-at-dusk/traces": [],
  "/sequences/lab_safe_shutdown/traces": [], "/system/networks": F.networks, "/system/certificate": F.certificate,
  "/config/errors": F.configErrors, "/setup": { needed: false },
};

function reply(body: unknown, status = 200) {
  return Promise.resolve(new Response(body === undefined ? null : JSON.stringify(body),
                                      { status, headers: { "content-type": "application/json" } }));
}

window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
  const url = new URL(String(input), location.origin);
  const path = decodeURIComponent(url.pathname.replace(/^\/api\/v1/, ""));
  const method = init?.method ?? "GET";
  if (method !== "GET") return reply({ ok: true });
  if (path.startsWith("/items/") && path.endsWith("/assignments")) {
    return reply(F.assignments[path.split("/")[2] ?? ""] ?? []);
  }
  return path in GET ? reply(GET[path]) : reply({ detail: `No sample data for ${path}` }, 404);
};

// no live feed in the preview
window.WebSocket = class { onopen = null; onmessage = null; onclose = null; send() {} close() {} } as never;

const params = new URLSearchParams(location.search);
const path = params.get("path") ?? "/";
const theme = (params.get("theme") ?? "light") as ThemeName;
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

function Preview() {
  const [current, setTheme] = useState<ThemeName>(theme);
  return (
    <ThemeContext.Provider value={{ theme: current, setTheme }}>
      <QueryClientProvider client={client}>
        <FluentProvider theme={themes[current]} className="root" data-theme={current}>
          <MemoryRouter initialEntries={[path]}>
            <AppRoutes />
          </MemoryRouter>
        </FluentProvider>
      </QueryClientProvider>
    </ThemeContext.Provider>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<StrictMode><Preview /></StrictMode>);
