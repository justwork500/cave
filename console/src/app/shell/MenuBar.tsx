import { Button, Menu, MenuItem, MenuList, MenuPopover, MenuTrigger } from "@fluentui/react-components";
import { LockClosedRegular, NavigationRegular } from "@fluentui/react-icons";
import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, useNavigate } from "react-router";
import { api } from "../../api/client";
import type { Item, Me } from "../../api/types";
import { useLive, useNarrow } from "../live";
import { Bell } from "./Bell";

export const dashboardPath = (id: string) => (id === "dashboard:home" ? "/" : `/d/${id.replace(/^dashboard:/, "")}`);

async function signOut(live: ReturnType<typeof useLive>) {
  live?.stop(); // otherwise the server closing its socket redirects too, racing this one
  await api.post("/auth/logout").catch(() => undefined);
  location.assign("/login");
}

export function MenuBar({ me }: { me: Me }) {
  const narrow = useNarrow();
  const live = useLive();
  const navigate = useNavigate();
  const items = useQuery({ queryKey: ["items"], queryFn: () => api.get<Item[]>("/items") });
  const dashboards = (items.data ?? []).filter((i) => i.kind === "dashboard");
  const admin = me.sections.length > 0;

  const dashboardItems = dashboards.map((d) => (
    <MenuItem
      key={d.id}
      disabled={!d.allowed}
      icon={d.allowed ? undefined : <LockClosedRegular />}
      onClick={() => navigate(dashboardPath(d.id))}
    >
      {d.allowed ? d.name : `${d.name} (restricted)`}
    </MenuItem>
  ));
  const userItems = [
    <MenuItem key="profile" onClick={() => navigate("/profile")}>
      Profile and theme
    </MenuItem>,
    <MenuItem key="out" onClick={() => void signOut(live)}>
      Sign out
    </MenuItem>,
  ];

  return (
    <header className="bar">
      <Link to="/" className="logo" aria-label="CAVE home">
        CAVE
      </Link>
      <nav aria-label="Main" className="bar-nav">
        {!narrow && dashboards.length > 1 && (
          <Menu>
            <MenuTrigger disableButtonEnhancement>
              <Button className="bar-button" appearance="transparent">
                Dashboards
              </Button>
            </MenuTrigger>
            <MenuPopover>
              <MenuList>{dashboardItems}</MenuList>
            </MenuPopover>
          </Menu>
        )}
        {!narrow && admin && (
          <NavLink to="/admin" className="bar-link">
            Admin console
          </NavLink>
        )}
      </nav>
      <Bell />
      {narrow ? (
        <Menu>
          <MenuTrigger disableButtonEnhancement>
            <Button className="bar-button" appearance="transparent" icon={<NavigationRegular />} aria-label="Menu" />
          </MenuTrigger>
          <MenuPopover>
            <MenuList>
              {dashboardItems}
              {admin && <MenuItem onClick={() => navigate("/admin")}>Admin console</MenuItem>}
              {userItems}
            </MenuList>
          </MenuPopover>
        </Menu>
      ) : (
        <Menu>
          <MenuTrigger disableButtonEnhancement>
            <Button className="bar-button" appearance="transparent">
              {me.display_name}
            </Button>
          </MenuTrigger>
          <MenuPopover>
            <MenuList>{userItems}</MenuList>
          </MenuPopover>
        </Menu>
      )}
    </header>
  );
}
