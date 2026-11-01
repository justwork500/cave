import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../api/client";
import type { Summary } from "../api/types";
import { ErrorBar, Page } from "./Page";

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** What needs attention, each linking to the list that explains it. Only what your sections cover. */
export function Home() {
  const summary = useQuery({ queryKey: ["summary"], queryFn: () => api.get<Summary>("/summary") });
  const s = summary.data ?? {};
  const tiles: { text: string; to: string; alert: boolean }[] = [];
  if (s.mqtt) {
    tiles.push({ text: `MQTT ${s.mqtt.status}, ${plural(s.mqtt.entities, "device", "devices")}`,
                 to: "/admin/system", alert: s.mqtt.status !== "connected" && s.mqtt.status !== "disabled" });
  }
  if (s.unavailable !== undefined) {
    tiles.push({ text: `${plural(s.unavailable, "device", "devices")} not responding`,
                 to: "/admin/devices?filter=unavailable", alert: s.unavailable > 0 });
  }
  if (s.failures_24h !== undefined) {
    tiles.push({ text: `${plural(s.failures_24h, "automation failure", "automation failures")} in the last day`,
                 to: "/admin/automations?filter=failed", alert: s.failures_24h > 0 });
  }
  if (s.screens_pending !== undefined) {
    tiles.push({ text: `${plural(s.screens_pending, "screen", "screens")} waiting for approval`,
                 to: "/admin/screens?filter=pending", alert: s.screens_pending > 0 });
  }
  return (
    <Page title="Home">
      <ErrorBar error={summary.error} />
      <ul className="summary">
        {tiles.map((t) => (
          <li key={t.to}>
            <Link to={t.to} className={t.alert ? "alert" : undefined}>
              {t.text}
            </Link>
          </li>
        ))}
      </ul>
    </Page>
  );
}
