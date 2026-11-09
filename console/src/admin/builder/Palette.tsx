import { Button, Input } from "@fluentui/react-components";
import { AddRegular, SearchRegular } from "@fluentui/react-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import type { EntityView, Listed } from "../../api/types";
import { isFull } from "../../cards/entity";
import type { Source } from "./model";

const SENSORS = new Set(["sensor", "binary_sensor", "device_tracker", "weather"]);

/** The type a drag carries, so a drop of anything else is ignored. */
export const DRAG_TYPE = "application/x-cave-builder";

interface Row {
  name: string;
  source: Source;
}

interface ScriptRow {
  file: string;
  name: string;
  allowed: boolean;
  runnable: boolean;
}

function Section({ title, rows, onAdd }: { title: string; rows: Row[]; onAdd: (s: Source) => void }) {
  if (rows.length === 0) return null;
  return (
    <section>
      <h3>{title}</h3>
      <ul className="palette-list">
        {rows.map((r) => (
          <li
            key={r.name + JSON.stringify(r.source).length}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData(DRAG_TYPE, JSON.stringify({ source: r.source }));
              e.dataTransfer.effectAllowed = "copy";
            }}
          >
            <span>{r.name}</span>
            <Button size="small" appearance="subtle" icon={<AddRegular />} aria-label={`Add ${r.name}`}
                    onClick={() => onAdd(r.source)} />
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Everything this person can put on a dashboard. A list they can't read simply isn't shown. */
export function Palette({ states, onAdd }: { states: EntityView[]; onAdd: (s: Source) => void }) {
  const [query, setQuery] = useState("");
  const automations = useQuery({ queryKey: ["automations"], queryFn: () => api.get<Listed[]>("/automations") });
  const sequences = useQuery({ queryKey: ["sequences"], queryFn: () => api.get<Listed[]>("/sequences") });
  const scripts = useQuery({ queryKey: ["scripts"], queryFn: () => api.get<ScriptRow[]>("/scripts") });

  const q = query.trim().toLowerCase();
  const match = (rows: Row[]) => rows.filter((r) => r.name.toLowerCase().includes(q));
  const entities = (sensors: boolean): Row[] => states.filter(isFull)
    .filter((e) => SENSORS.has(e.capability) === sensors)
    .map((entity) => ({ name: entity.name, source: { kind: sensors ? "sensor" : "device", entity } }));
  const listed = (kind: "automation" | "routine", rows: Listed[] = []): Row[] => rows.filter((r) => r.allowed)
    .map((r) => ({ name: r.name, source: { kind, id: r.id, name: r.name } }));

  return (
    <aside className="builder-panel" aria-label="Add to dashboard">
      <h2>Add to dashboard</h2>
      <Input
        contentBefore={<SearchRegular />}
        placeholder="Search"
        aria-label="Search what you can add"
        value={query}
        onChange={(_, d) => setQuery(d.value)}
      />
      <Section title="Devices" rows={match(entities(false))} onAdd={onAdd} />
      <Section title="Sensors" rows={match(entities(true))} onAdd={onAdd} />
      <Section title="Automations" rows={match(listed("automation", automations.data))} onAdd={onAdd} />
      <Section title="Routines" rows={match(listed("routine", sequences.data))} onAdd={onAdd} />
      <Section
        title="Scripts"
        rows={match((scripts.data ?? []).filter((s) => s.allowed && s.runnable)
          .map((s) => ({ name: s.name, source: { kind: "script", id: s.file, name: s.name } })))}
        onAdd={onAdd}
      />
      <Section
        title="Other"
        rows={match([{ name: "Text note", source: { kind: "note" } }, { name: "List tile", source: { kind: "list" } }])}
        onAdd={onAdd}
      />
    </aside>
  );
}
