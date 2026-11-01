import { FluentProvider } from "@fluentui/react-components";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";
import { themes } from "../app/theme";

type Handler = unknown | ((body: unknown) => unknown);
export interface Call {
  method: string;
  path: string;
  /** The query string, like "?create=true", or "". */
  query: string;
  body: unknown;
}

/** Fakes the API: keys are "GET /me", values are the JSON to return, or [status, json], or a function of the body. */
export function mockApi(routes: Record<string, Handler>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const path = decodeURIComponent(url.replace(/^\/api\/v1/, "").split("?")[0] ?? "");
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      const query = url.includes("?") ? url.slice(url.indexOf("?")) : "";
      calls.push({ method, path, query, body });
      const key = `${method} ${path}`;
      if (!(key in routes)) return new Response(JSON.stringify({ detail: `no mock for ${key}` }), { status: 404 });
      const handler = routes[key];
      let out = typeof handler === "function" ? (handler as (b: unknown) => unknown)(body) : handler;
      let status = 200;
      if (Array.isArray(out) && out.length === 2 && typeof out[0] === "number") [status, out] = out as [number, unknown];
      if (status === 204 || out === undefined) return new Response(null, { status: status === 200 ? 204 : status });
      return new Response(JSON.stringify(out), { status, headers: { "content-type": "application/json" } });
    }),
  );
  return calls;
}

export function setNarrow(narrow: boolean) {
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: narrow && q.includes("max-width"),
    media: q,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

export function renderWith(ui: ReactElement, path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FluentProvider theme={themes.light}>
        <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
      </FluentProvider>
    </QueryClientProvider>,
  );
}

export const ADMIN = {
  kind: "user", id: "a", username: "admin", display_name: "Alex", role: "admin", has_totp: true,
  sections: ["section:devices", "section:automations", "section:scripts", "section:dashboards", "section:users",
             "section:system", "section:audit", "section:signin_log", "section:run_history"],
};
export const SAM = { kind: "user", id: "s", username: "sam", display_name: "Sam", role: "household",
                     has_totp: false, sections: [] };
