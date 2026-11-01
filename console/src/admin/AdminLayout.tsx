import type { ReactNode } from "react";
import { NavLink, Outlet, useOutletContext } from "react-router";
import type { Me } from "../api/types";
import { NoAccess } from "../pages/NoAccess";
import { Access } from "./Access";
import { Audit, SignIns } from "./Logs";
import { Devices } from "./Devices";
import { Groups } from "./Groups";
import { Home } from "./Home";
import { Screens } from "./Screens";
import { Tokens } from "./Tokens";
import { Users } from "./Users";

/** Every admin page, the section it needs, and what it shows. null means any console section. */
export const ADMIN_PAGES: { path: string; title: string; section: string | null; element: ReactNode }[] = [
  { path: "", title: "Home", section: null, element: <Home /> },
  { path: "devices", title: "Devices", section: "section:devices", element: <Devices /> },
  { path: "users", title: "Users", section: "section:users", element: <Users /> },
  { path: "groups", title: "Groups", section: "section:users", element: <Groups /> },
  { path: "screens", title: "Screens", section: "section:users", element: <Screens /> },
  { path: "access", title: "Access", section: "section:users", element: <Access /> },
  { path: "tokens", title: "API tokens", section: "section:users", element: <Tokens /> },
  { path: "automations", title: "Automations", section: "section:automations", element: <h1>Automations</h1> },
  { path: "scripts", title: "Scripts", section: "section:scripts", element: <h1>Scripts</h1> },
  { path: "dashboards", title: "Dashboards", section: "section:dashboards", element: <h1>Dashboards</h1> },
  { path: "system", title: "System", section: "section:system", element: <h1>System</h1> },
  { path: "audit", title: "Audit log", section: "section:audit", element: <Audit /> },
  { path: "signins", title: "Sign-in log", section: "section:signin_log", element: <SignIns /> },
];

export const useMe = () => useOutletContext<Me>();

export function Guard({ section, children }: { section: string | null; children: ReactNode }) {
  const me = useMe();
  const ok = section === null ? me.sections.length > 0 : me.sections.includes(section);
  return ok ? children : <NoAccess />;
}

export function AdminLayout() {
  const me = useMe();
  if (me.sections.length === 0) return <NoAccess />;
  const pages = ADMIN_PAGES.filter((p) => p.section === null || me.sections.includes(p.section));
  return (
    <div className="admin">
      <nav aria-label="Admin console" className="admin-nav">
        <ul>
          {pages.map((p) => (
            <li key={p.path}>
              <NavLink to={`/admin/${p.path}`} end>
                {p.title}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <div className="admin-main">
        <Outlet context={me} />
      </div>
    </div>
  );
}
