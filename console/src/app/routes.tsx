import { Spinner } from "@fluentui/react-components";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes, useOutletContext } from "react-router";
import { ApiError, api } from "../api/client";
import type { Me } from "../api/types";
import { LiveFeed } from "../api/ws";
import { Dashboard } from "../pages/Dashboard";
import { Login } from "../pages/Login";
import { NoAccess } from "../pages/NoAccess";
import { Profile } from "../pages/Profile";
import { Setup } from "../pages/Setup";
import { LiveContext } from "./live";
import { MenuBar } from "./shell/MenuBar";

/** Admin pages and the section each needs. Filled in by the admin tasks. */
const ADMIN: { path: string; title: string; section: string | null }[] = [
  { path: "", title: "Home", section: null },
  { path: "devices", title: "Devices", section: "section:devices" },
  { path: "users", title: "Users", section: "section:users" },
  { path: "groups", title: "Groups", section: "section:users" },
  { path: "screens", title: "Screens", section: "section:users" },
  { path: "access", title: "Access", section: "section:users" },
  { path: "tokens", title: "Tokens", section: "section:users" },
  { path: "audit", title: "Audit log", section: "section:audit" },
  { path: "signins", title: "Sign-in log", section: "section:signin_log" },
  { path: "automations", title: "Automations", section: "section:automations" },
  { path: "scripts", title: "Scripts", section: "section:scripts" },
  { path: "dashboards", title: "Dashboards", section: "section:dashboards" },
  { path: "system", title: "System", section: "section:system" },
];

const useMe = () => useOutletContext<Me>();

function Guard({ section, children }: { section: string | null; children: React.ReactNode }) {
  const me = useMe();
  const ok = section === null ? me.sections.length > 0 : me.sections.includes(section);
  return ok ? children : <NoAccess />;
}

function SignedOut() {
  const setup = useQuery({ queryKey: ["setup"], queryFn: () => api.get<{ needed: boolean }>("/setup") });
  if (setup.isPending) return <Spinner label="Loading" />;
  return <Navigate to={setup.data?.needed ? "/setup" : "/login"} replace />;
}

function Shell() {
  const client = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("/me") });
  const [feed] = useState(() => {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    // the browser socket matches the small shape LiveFeed uses; its handler types are just wider
    return new LiveFeed(`${scheme}://${location.host}/api/v1/ws`, WebSocket as never, () => void client.invalidateQueries());
  });
  const signedIn = Boolean(me.data);

  useEffect(() => {
    if (!signedIn) return;
    feed.start();
    return () => feed.stop();
  }, [signedIn, feed]);

  if (me.error instanceof ApiError && me.error.status === 401) return <SignedOut />;
  if (me.isError) return <p role="alert">CAVE isn't answering. Check the server and reload.</p>;
  if (!me.data) return <Spinner label="Loading" />;
  return (
    <LiveContext.Provider value={feed}>
      <MenuBar me={me.data} />
      <main className="main">
        <Outlet context={me.data} />
      </main>
    </LiveContext.Provider>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/setup" element={<Setup />} />
      <Route element={<Shell />}>
        <Route index element={<Dashboard />} />
        <Route path="/d/:slug" element={<Dashboard />} />
        <Route path="/profile" element={<Profile />} />
        {ADMIN.map((p) => (
          <Route
            key={p.path}
            path={`/admin/${p.path}`}
            element={
              <Guard section={p.section}>
                <h1 className="page">{p.title}</h1>
              </Guard>
            }
          />
        ))}
        <Route path="*" element={<NoAccess />} />
      </Route>
    </Routes>
  );
}
