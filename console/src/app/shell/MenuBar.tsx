import {
  Button, DrawerBody, DrawerHeader, DrawerHeaderTitle, Menu, MenuItem, MenuList, MenuPopover, MenuTrigger,
  OverlayDrawer,
} from "@fluentui/react-components";
import { DismissRegular, LockClosedRegular, NavigationRegular, PersonRegular } from "@fluentui/react-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router";
import { api } from "../../api/client";
import type { Item, Me } from "../../api/types";
import { useFolded, useLive } from "../live";
import { dashboardPath, navFor } from "../nav";
import { Bell } from "./Bell";

export { dashboardPath } from "../nav";

async function signOut(live: ReturnType<typeof useLive>) {
  live?.stop(); // otherwise the server closing its socket redirects too, racing this one
  await api.post("/auth/logout").catch(() => undefined);
  location.assign("/login");
}

/** CAVE's mark: the mouth of a cave, an arch on its ground line. */
export function Mark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" className="mark">
      <path d="M5 20V12.5a7 7 0 0 1 14 0V20" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M2.5 20.5h19" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

function Nav({ me, onGo }: { me: Me; onGo?: () => void }) {
  const items = useQuery({ queryKey: ["items"], queryFn: () => api.get<Item[]>("/items") });
  const dashboards = (items.data ?? []).filter((i) => i.kind === "dashboard" && !i.missing);
  return (
    <nav aria-label="Main" className="nav">
      {dashboards.length > 0 && (
        <div className="nav-group">
          <p className="nav-label">Dashboards</p>
          <ul>
            {dashboards.map((d) => (
              <li key={d.id}>
                {d.allowed ? (
                  <NavLink to={dashboardPath(d.id)} end onClick={onGo}>{d.name}</NavLink>
                ) : (
                  <span className="nav-locked" title="You don't have access to this dashboard">
                    {d.name} <LockClosedRegular aria-label="restricted" />
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {navFor(me.sections).map((g) => (
        <div key={g.group} className="nav-group">
          <p className="nav-label">{g.group}</p>
          <ul>
            {g.items.map((i) => (
              <li key={i.path}>
                <NavLink to={i.path} end={i.path === "/admin"} onClick={onGo}>{i.title}</NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function UserMenu({ me }: { me: Me }) {
  const live = useLive();
  const navigate = useNavigate();
  return (
    <Menu positioning="above-start">
      <MenuTrigger disableButtonEnhancement>
        <Button className="user-button" appearance="subtle" icon={<PersonRegular />}>{me.display_name}</Button>
      </MenuTrigger>
      <MenuPopover>
        <MenuList>
          <MenuItem onClick={() => navigate("/profile")}>Profile and theme</MenuItem>
          <MenuItem onClick={() => void signOut(live)}>Sign out</MenuItem>
        </MenuList>
      </MenuPopover>
    </Menu>
  );
}

/** The sidebar on the page ground; on a phone, a 48px bar with the same navigation in a sheet. */
export function MenuBar({ me }: { me: Me }) {
  const narrow = useFolded();
  const [open, setOpen] = useState(false);
  const home = (
    <Link to="/" className="brand" aria-label="CAVE home">
      <Mark />
      <span>CAVE</span>
    </Link>
  );

  if (narrow) {
    return (
      <header className="topbar">
        {home}
        <Bell />
        <Button appearance="subtle" icon={<NavigationRegular />} aria-label="Menu" onClick={() => setOpen(true)} />
        <OverlayDrawer position="start" open={open} onOpenChange={(_, d) => setOpen(d.open)}>
          <DrawerHeader>
            <DrawerHeaderTitle action={<Button appearance="subtle" icon={<DismissRegular />} aria-label="Close menu"
                                               onClick={() => setOpen(false)} />}>
              Menu
            </DrawerHeaderTitle>
          </DrawerHeader>
          <DrawerBody>
            <Nav me={me} onGo={() => setOpen(false)} />
            <div className="sidebar-foot"><UserMenu me={me} /></div>
          </DrawerBody>
        </OverlayDrawer>
      </header>
    );
  }

  return (
    <aside className="sidebar">
      {home}
      <Nav me={me} />
      <div className="sidebar-foot">
        <Bell />
        <UserMenu me={me} />
      </div>
    </aside>
  );
}
