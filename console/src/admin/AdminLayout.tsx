import type { ReactNode } from "react";
import { Outlet, useOutletContext } from "react-router";
import type { Me } from "../api/types";
import { NoAccess } from "../pages/NoAccess";
import { Access } from "./Access";
import { AutomationEditor, Automations } from "./Automations";
import { Certificate } from "./Certificate";
import { ConfigErrors } from "./ConfigErrors";
import { DashboardEditor, Dashboards } from "./Dashboards";
import { Audit, SignIns } from "./Logs";
import { Devices } from "./Devices";
import { Groups } from "./Groups";
import { Home } from "./Home";
import { Networks } from "./Networks";
import { Page } from "./Page";
import { ScriptEditor, Scripts } from "./Scripts";
import { Screens } from "./Screens";
import { TestCenter } from "./TestCenter";
import { Tokens } from "./Tokens";
import { Users } from "./Users";

/** Every admin page, the section it needs, and what it shows. null means any console section. */
export const ADMIN_PAGES: { path: string; title: string; section: string | null; element: ReactNode; inNav?: false }[] = [
  { path: "", title: "Home", section: null, element: <Home /> },
  { path: "devices", title: "Devices", section: "section:devices", element: <Devices /> },
  { path: "users", title: "Users", section: "section:users", element: <Users /> },
  { path: "groups", title: "Groups", section: "section:users", element: <Groups /> },
  { path: "screens", title: "Screens", section: "section:users", element: <Screens /> },
  { path: "access", title: "Access", section: "section:users", element: <Access /> },
  { path: "tokens", title: "API tokens", section: "section:users", element: <Tokens /> },
  { path: "automations", title: "Automations", section: "section:automations", element: <Automations /> },
  { path: "automations/new", title: "New automation", section: "section:automations", element: <AutomationEditor />,
    inNav: false },
  { path: "automations/:kinds/:id", title: "Automation", section: "section:automations", element: <AutomationEditor />,
    inNav: false },
  { path: "test-center", title: "Test Center", section: "section:automations", element: <TestCenter />, inNav: false },
  { path: "scripts", title: "Scripts", section: "section:scripts", element: <Scripts /> },
  { path: "scripts/:file", title: "Script", section: "section:scripts", element: <ScriptEditor />, inNav: false },
  { path: "dashboards", title: "Dashboards", section: "section:dashboards", element: <Dashboards /> },
  { path: "dashboards/:slug", title: "Dashboard", section: "section:dashboards", element: <DashboardEditor />,
    inNav: false },
  // shortcut: no General page in Phase 1; time zone comes from the host
  { path: "system", title: "System", section: "section:system", element: <System /> },
  { path: "audit", title: "Audit log", section: "section:audit", element: <Audit /> },
  { path: "signins", title: "Sign-in log", section: "section:signin_log", element: <SignIns /> },
];

function System() {
  return (
    <Page title="Network and certificate">
      <Networks />
      <Certificate />
      <ConfigErrors />
    </Page>
  );
}

export const useMe = () => useOutletContext<Me>();

export function Guard({ section, children }: { section: string | null; children: ReactNode }) {
  const me = useMe();
  const ok = section === null ? me.sections.length > 0 : me.sections.includes(section);
  return ok ? children : <NoAccess />;
}

export function AdminLayout() {
  const me = useMe();
  if (me.sections.length === 0) return <NoAccess />;
  return <Outlet context={me} />;  // the sidebar (MenuBar) lists these pages, from app/nav.ts
}
