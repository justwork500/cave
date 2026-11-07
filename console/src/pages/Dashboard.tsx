import { Spinner, Tab, TabList } from "@fluentui/react-components";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useOutletContext, useParams } from "react-router";
import { ApiError, api, message } from "../api/client";
import type { Card, DashboardView, EntityView, Me } from "../api/types";
import { ActionButton } from "../cards/Button";
import { Gauge } from "../cards/Gauge";
import { Markdown } from "../cards/Markdown";
import { Entities, Tile } from "../cards/Tile";
import { useNarrow } from "../app/live";
import { load } from "../app/prefs";
import { NoAccess } from "./NoAccess";
import { finding, greeting, rooms } from "./glance";

export function CardBody({ card, section }: { card: Card; section: string }) {
  switch (card.type) {
    case "tile":
      return (
        <Tile
          entity={card.entity}
          label={card.label}
          icon={card.icon}
          tapAction={card.locked ? "none" : card.tap_action}
          section={section}
        />
      );
    case "gauge":
      return <Gauge card={card} />;
    case "entities":
      return <Entities entities={card.entities} label={card.label} icon={card.icon} />;
    case "button":
      return <ActionButton card={card} />;
    case "markdown":
      return <Markdown text={card.text} />;
  }
}

function useSlug(): { slug: string | null | undefined; pending: boolean } {
  const params = useParams();
  const preferred = load("defaultDashboard")?.replace(/^dashboard:/, "");
  const fallback = useQuery({
    queryKey: ["dashboards", "default"],
    queryFn: () => api.get<{ slug: string | null }>("/dashboards/default"),
    enabled: !params.slug && !preferred,
  });
  if (params.slug) return { slug: params.slug, pending: false };
  if (preferred) return { slug: preferred, pending: false };
  return { slug: fallback.data?.slug, pending: fallback.isPending };
}

export function Dashboard() {
  const { slug, pending } = useSlug();
  const view = useQuery({
    queryKey: ["dashboards", slug, "view"],
    queryFn: () => api.get<DashboardView>(`/dashboards/${encodeURIComponent(slug ?? "")}/view`),
    enabled: Boolean(slug),
  });

  if (pending || (slug && view.isPending)) return <Spinner label="Loading" />;
  if (!slug) {
    return (
      <section className="page narrow">
        <h1>No dashboards for you yet</h1>
        <p>Ask an Admin to share a dashboard with you.</p>
      </section>
    );
  }
  if (view.error instanceof ApiError && view.error.status === 403) return <NoAccess />;
  if (view.isError || !view.data) return <p role="alert">{message(view.error)}</p>;

  return (
    <section className="page">
      <Greeting view={view.data} />
      <DashboardBody view={view.data} />
    </section>
  );
}

const devices = (d: DashboardView): EntityView[] =>
  d.views.flatMap((v) => v.sections.flatMap((s) => s.cards.flatMap((c) =>
    c.type === "tile" || c.type === "gauge" ? [c.entity] : c.type === "entities" ? c.entities : [])));

/** "Good morning, Jordan", what is on in the house, and each room at a glance. */
function Greeting({ view }: { view: DashboardView }) {
  const me = useOutletContext<Me | undefined>();
  // shortcut: worked out from the states the page loaded with; the tiles below follow the live feed
  const all = devices(view);
  const line = finding(all);
  const strip = rooms(all);
  return (
    <header className="greeting">
      <div className="greeting-head">
        <h1>{greeting(new Date(), me?.display_name)}</h1>
        {me?.sections.includes("section:dashboards") && (
          <Link to={`/admin/dashboards/${view.slug}`} aria-label="Edit dashboard">Edit</Link>
        )}
      </div>
      <p className="finding">{view.title === "Home" ? line : `${view.title}. ${line}`}</p>
      {strip.length > 1 && (
        <ul className="glance" aria-label="Rooms">
          {strip.map((r) => (
            <li key={r.name} className={r.on ? "on" : undefined}><b>{r.name}</b> {r.text}</li>
          ))}
        </ul>
      )}
    </header>
  );
}

/** The views, sections and cards; also the dashboard editor's preview. */
export function DashboardBody({ view: d }: { view: DashboardView }) {
  const narrow = useNarrow();
  const [tab, setTab] = useState<string>();
  const current = d.views.find((v) => v.id === tab) ?? d.views[0];
  return (
    <>
      {d.views.length > 1 && (
        <TabList selectedValue={current?.id} onTabSelect={(_, t) => setTab(String(t.value))}>
          {d.views.map((v) => (
            <Tab key={v.id} value={v.id}>
              {v.title}
            </Tab>
          ))}
        </TabList>
      )}
      {current?.sections.map((s, i) => (
        <section key={i} className="dash-section">
          {s.title && (
            <header>
              <h2>{s.title}</h2>
            </header>
          )}
          <div className={`grid${narrow ? " one-column" : ""}`}>
            {s.cards.map((c, j) => (
              <div
                key={j}
                className={`card card-${c.type}${c.color ? ` tint-${c.color}` : ""}`}
                style={narrow ? undefined : { gridColumn: `span ${c.w}`, gridRow: `span ${c.h}` }}
              >
                <CardBody card={c} section={s.title} />
              </div>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}
