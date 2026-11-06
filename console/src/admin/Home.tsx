import { CheckmarkRegular } from "@fluentui/react-icons";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../api/client";
import type { EntityView, Listed, Notification, Summary } from "../api/types";
import { useMe } from "./AdminLayout";
import { ErrorBar, Page, when } from "./Page";
import type { Screen } from "./Screens";
import type { User } from "./Users";

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

interface Attention {
  key: string;
  text: string;
  detail: string;
  action: string;
  to: string;
}

/** Answers "does anything need me, and what's next to set up?" Only what your console sections cover. */
export function Home() {
  const me = useMe();
  const has = (s: string) => me.sections.includes(s);
  const people = has("section:users");
  const summary = useQuery({ queryKey: ["summary"], queryFn: () => api.get<Summary>("/summary") });
  const states = useQuery({ queryKey: ["states"], queryFn: () => api.get<EntityView[]>("/states") });
  const areas = useQuery({ queryKey: ["areas"], queryFn: () => api.get<{ id: string }[]>("/areas") });
  const dashboards = useQuery({ queryKey: ["dashboards"], queryFn: () => api.get<Listed[]>("/dashboards") });
  const automations = useQuery({ queryKey: ["automations"], queryFn: () => api.get<Listed[]>("/automations") });
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>("/users"), enabled: people });
  const screens = useQuery({ queryKey: ["screens"], queryFn: () => api.get<Screen[]>("/screens"), enabled: people });
  const notes = useQuery({ queryKey: ["notifications"], queryFn: () => api.get<Notification[]>("/notifications") });

  const s = summary.data ?? {};
  const deviceCount = states.data?.length ?? 0;
  const attention: Attention[] = [];
  for (const sc of (screens.data ?? []).filter((x) => x.status === "pending" && x.fingerprint)) {
    attention.push({ key: sc.id, text: `${sc.name} is waiting for approval`, action: "Approve",
                     detail: "Check its fingerprint matches the one on the tablet.", to: "/admin/screens?filter=pending" });
  }
  if (s.unavailable) {
    attention.push({ key: "down", text: `${plural(s.unavailable, "device", "devices")} not responding`,
                     detail: "Check it's powered on and connected to your network.", action: "View devices",
                     to: "/admin/devices?filter=unavailable" });
  }
  if (s.failures_24h) {
    attention.push({ key: "failed", text: `${plural(s.failures_24h, "automation", "automations")} failed today`,
                     detail: "Each run shows the step that failed.", action: "View runs", to: "/admin/automations?filter=failed" });
  }
  if (s.mqtt && s.mqtt.status !== "connected" && s.mqtt.status !== "disabled") {
    attention.push({ key: "mqtt", text: "CAVE can't reach the MQTT broker", action: "Check the network",
                     detail: "Devices stop updating until it reconnects.", to: "/admin/system" });
  }

  const steps = [
    { done: deviceCount > 0, title: "Connect your devices", to: "/admin/devices", link: "Add a device",
      text: "Add Kasa plugs from Devices. Zigbee2MQTT, Tasmota, Shelly and ESPHome devices appear on their own." },
    { done: (areas.data?.length ?? 0) > 0, title: "Put devices in rooms", to: "/admin/devices", link: "Devices",
      text: "Rooms group devices on dashboards and in the house at a glance." },
    { done: (dashboards.data?.length ?? 0) > 1, title: "Make a dashboard for a room or a person", to: "/admin/dashboards",
      link: "Dashboards", text: "Everyone who can open a dashboard can use what's on it." },
    ...(people ? [
      { done: (users.data?.length ?? 0) > 1, title: "Invite your household", to: "/admin/users", link: "People",
        text: "Household members don't need an authenticator app; Admins do." },
      { done: (screens.data ?? []).some((x) => x.status === "approved"), title: "Add a wall tablet",
        to: "/admin/screens", link: "Wall tablets", text: "A tablet signs in with its own key and opens one dashboard." },
    ] : []),
    { done: (automations.data?.length ?? 0) > 0, title: "Automate something, then test it safely",
      to: "/admin/automations/new", link: "New automation", text: "The Test Center runs it with pretend values." },
  ];
  const done = steps.filter((x) => x.done).length;

  return (
    <Page title="Overview" lead={deviceCount ? `${plural(deviceCount, "device", "devices")} in ${
      plural(areas.data?.length ?? 0, "room", "rooms")}` : "Nothing is connected yet"}>
      <ErrorBar error={summary.error ?? states.error} />
      <div className="counts">
        <Link to="/admin/devices"><span>Devices</span><b>{deviceCount}</b></Link>
        <Link to="/admin/devices"><span>Rooms</span><b>{areas.data?.length ?? 0}</b></Link>
        <Link to="/admin/dashboards"><span>Dashboards</span><b>{dashboards.data?.length ?? 0}</b></Link>
        {people ? (
          <Link to="/admin/users"><span>People</span><b>{users.data?.length ?? 0}</b></Link>
        ) : (
          <Link to="/admin/automations"><span>Automations</span><b>{automations.data?.length ?? 0}</b></Link>
        )}
      </div>
      <div className="overview">
        <div className="stack">
        <section className="panel" aria-labelledby="attention">
          <header><h2 id="attention">Needs you</h2><span className="count">{attention.length || "Nothing"}</span></header>
          {attention.length ? (
            <ul className="attention">
              {attention.map((a) => (
                <li key={a.key}>
                  <div><b>{a.text}</b><span className="muted">{a.detail}</span></div>
                  <Link className="link-button" to={a.to}>{a.action}</Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="attention calm">Nothing needs you right now: every device is responding and nothing failed today.</p>
          )}
        </section>
        <section className="panel" aria-labelledby="latest">
          <header><h2 id="latest">Latest from your home</h2></header>
          {(notes.data ?? []).length ? (
            <ul className="latest">
              {(notes.data ?? []).slice(0, 5).map((n) => (
                <li key={n.id}>
                  <span>{n.title ? <b>{n.title}: </b> : null}{n.message}</span>
                  <time className="muted" dateTime={n.created_at}>{when(n.created_at)}</time>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Automations that notify you will show here.</p>
          )}
        </section>
        </div>
        <section className="panel" aria-labelledby="setup">
          <header><h2 id="setup">Set up your home</h2><span className="count num">{done} of {steps.length} done</span></header>
          <div className="setup-progress" aria-hidden="true">
            <div className="track"><div className="fill" style={{ width: `${(done / steps.length) * 100}%` }} /></div>
          </div>
          <ol className="steps">
            {steps.map((x) => (
              <li key={x.title} className={x.done ? "done" : undefined}>
                <span className="tick" role="img" aria-label={x.done ? "Done" : "To do"}>{x.done && <CheckmarkRegular />}</span>
                <div>
                  <b>{x.title}</b>
                  {!x.done && (
                    <p>
                      {x.text}{" "}
                      {x.to.startsWith("http") ? <a href={x.to} target="_blank" rel="noreferrer">{x.link}</a>
                        : <Link to={x.to}>{x.link}</Link>}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </Page>
  );
}
