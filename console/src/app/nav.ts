/** Where things are: the sidebar's groups, each admin page with the section it needs. Routes live in AdminLayout. */

export interface NavItem {
  path: string;
  title: string;
  /** The console section it needs; null means any section. */
  section: string | null;
}

export const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Set up",
    items: [
      { path: "/admin", title: "Overview", section: null },
      { path: "/admin/devices", title: "Devices", section: "section:devices" },
      { path: "/admin/dashboards", title: "Dashboards", section: "section:dashboards" },
      { path: "/admin/automations", title: "Automations", section: "section:automations" },
      { path: "/admin/scripts", title: "Scripts", section: "section:scripts" },
    ],
  },
  {
    group: "People and access",
    items: [
      { path: "/admin/users", title: "People", section: "section:users" },
      { path: "/admin/groups", title: "Groups", section: "section:users" },
      { path: "/admin/screens", title: "Wall tablets", section: "section:users" },
      { path: "/admin/access", title: "Who can use what", section: "section:users" },
      { path: "/admin/tokens", title: "API tokens", section: "section:users" },
    ],
  },
  {
    group: "System",
    items: [
      { path: "/admin/system", title: "Network and certificate", section: "section:system" },
      { path: "/admin/audit", title: "Audit log", section: "section:audit" },
      { path: "/admin/signins", title: "Sign-in log", section: "section:signin_log" },
    ],
  },
];

/** The groups and items this person can open. */
export function navFor(sections: string[]) {
  return NAV.map((g) => ({
    ...g,
    items: g.items.filter((i) => (i.section === null ? sections.length > 0 : sections.includes(i.section))),
  })).filter((g) => g.items.length > 0);
}

export const dashboardPath = (id: string) => (id === "dashboard:home" ? "/" : `/d/${id.replace(/^dashboard:/, "")}`);
