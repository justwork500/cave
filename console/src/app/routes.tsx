import { Spinner } from "@fluentui/react-components";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router";
import { ADMIN_PAGES, AdminLayout, Guard } from "../admin/AdminLayout";
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
        <Route path="/admin" element={<AdminLayout />}>
          {ADMIN_PAGES.map((p) => (
            <Route
              key={p.path}
              index={p.path === ""}
              path={p.path || undefined}
              element={<Guard section={p.section}>{p.element}</Guard>}
            />
          ))}
          <Route path="*" element={<NoAccess />} />
        </Route>
        <Route path="*" element={<NoAccess />} />
      </Route>
    </Routes>
  );
}
