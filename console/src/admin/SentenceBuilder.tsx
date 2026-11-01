import { Button, Input, Select } from "@fluentui/react-components";
import { AddRegular, DismissRegular } from "@fluentui/react-icons";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { EntityView, Listed, Me } from "../api/types";
import { isFull } from "../cards/entity";
import type { Action, Condition, Sentence, Trigger } from "./sentence";

interface Choice {
  value: string;
  name: string;
}

/** Device, routine and script choices, by name. Devices only if you can control them. */
export function useChoices() {
  const states = useQuery({ queryKey: ["states"], queryFn: () => api.get<EntityView[]>("/states") });
  const sequences = useQuery({ queryKey: ["sequences"], queryFn: () => api.get<Listed[]>("/sequences") });
  const scripts = useQuery({
    queryKey: ["scripts"],
    queryFn: () => api.get<{ file: string; name: string; allowed: boolean }[]>("/scripts").catch(() => []),
  });
  const me = useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("/me") });
  return {
    devices: (states.data ?? []).filter(isFull).map((e) => ({ value: e.entity_id, name: e.name })),
    routines: (sequences.data ?? []).filter((s) => s.allowed).map((s) => ({ value: `sequence.${s.id}`, name: s.name })),
    scripts: (scripts.data ?? []).filter((s) => s.allowed).map((s) => ({ value: `scripts/${s.file}`, name: s.name })),
    me: me.data,
  };
}

function Pick({ label, value, choices, onChange }: {
  label: string;
  value: string;
  choices: Choice[];
  onChange: (v: string) => void;
}) {
  const known = choices.some((c) => c.value === value);
  return (
    <Select aria-label={label} value={value} onChange={(_, d) => onChange(d.value)} className="pick-inline">
      {!known && <option value={value}>{value ? "Something you can't see" : "Choose…"}</option>}
      {choices.map((c) => (
        <option key={c.value} value={c.value}>
          {c.name}
        </option>
      ))}
    </Select>
  );
}

function Text({ label, value, onChange, width = 8 }: {
  label: string;
  value: string | number | undefined;
  onChange: (v: string) => void;
  width?: number;
}) {
  return (
    <Input
      aria-label={label}
      className="text-inline"
      style={{ width: `${width + 2}ch` }}
      value={value === undefined ? "" : String(value)}
      onChange={(_, d) => onChange(d.value)}
    />
  );
}

const num = (v: string) => (v.trim() === "" || Number.isNaN(Number(v)) ? undefined : Number(v));
/** Drops keys set to undefined, so cleared blanks leave no trace in the YAML. */
function clean<T extends object>(o: T): T {
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && v !== "")) as T;
}

function TriggerPart({ t, set, devices }: { t: Trigger; set: (t: Trigger) => void; devices: Choice[] }) {
  const kind = (
    <Select aria-label="Trigger type" value={t.type} className="pick-inline" onChange={(_, d) => {
      const entity = "entity" in t ? t.entity : devices[0]?.value ?? "";
      set(d.value === "time" ? { type: "time", at: "07:00" } : d.value === "state"
        ? { type: "state", entity, to: "on" } : { type: "numeric_state", entity, below: 10 });
    }}>
      <option value="state">a device changes</option>
      <option value="numeric_state">a reading crosses a value</option>
      <option value="time">it's a set time</option>
    </Select>
  );
  if (t.type === "time") {
    return <>When {kind}: <Text label="Time" value={t.at} onChange={(at) => set({ ...t, at })} width={5} /></>;
  }
  const device = <Pick label="Trigger device" value={t.entity} choices={devices} onChange={(entity) => set({ ...t, entity })} />;
  const forPart = (
    <>
      for <Text label="For how long" value={t.for} onChange={(v) => set(clean({ ...t, for: v || undefined }))} width={6} />
    </>
  );
  if (t.type === "state") {
    return <>When {kind}: {device} switches to <Text label="New state" value={t.to} onChange={(to) => set(clean({ ...t, to }))} /> {forPart}</>;
  }
  return (
    <>
      When {kind}: {device} goes{" "}
      <Select aria-label="Above or below" className="pick-inline" value={t.above !== undefined ? "above" : "below"}
              onChange={(_, d) => set(clean({ ...t, above: d.value === "above" ? t.below ?? t.above : undefined,
                                                 below: d.value === "below" ? t.above ?? t.below : undefined }))}>
        <option value="above">above</option>
        <option value="below">below</option>
      </Select>{" "}
      <Text label="Value" value={t.above ?? t.below} width={5}
            onChange={(v) => set(t.above !== undefined ? { ...t, above: num(v) } : { ...t, below: num(v) })} /> {forPart}
    </>
  );
}

function ConditionPart({ c, set, devices }: { c: Condition | undefined; set: (c?: Condition) => void; devices: Choice[] }) {
  const kind = (
    <Select aria-label="Condition" value={c?.type ?? "none"} className="pick-inline" onChange={(_, d) => {
      const entity = c && "entity" in c ? c.entity : devices[0]?.value ?? "";
      set(d.value === "none" ? undefined : d.value === "time" ? { type: "time", after: "08:00", before: "22:00" }
        : d.value === "state" ? { type: "state", entity, state: "on" } : { type: "numeric_state", entity, below: 15 });
    }}>
      <option value="none">always</option>
      <option value="state">only if a device is in a state</option>
      <option value="numeric_state">only if a reading is above or below</option>
      <option value="time">only between two times</option>
    </Select>
  );
  if (!c) return <>, {kind}</>;
  if (c.type === "time") {
    return <>, {kind}: <Text label="After" value={c.after} width={5} onChange={(after) => set(clean({ ...c, after }))} /> and{" "}
      <Text label="Before" value={c.before} width={5} onChange={(before) => set(clean({ ...c, before }))} /></>;
  }
  const device = <Pick label="Condition device" value={c.entity} choices={devices} onChange={(entity) => set({ ...c, entity })} />;
  if (c.type === "state") {
    return <>, {kind}: {device} is <Text label="State" value={c.state} onChange={(state) => set({ ...c, state })} /></>;
  }
  return (
    <>
      , {kind}: {device} is {c.above !== undefined ? "above" : "below"}{" "}
      <Text label={c.above !== undefined ? "Above" : "Below"} value={c.above ?? c.below} width={5}
            onChange={(v) => set(c.above !== undefined ? { ...c, above: num(v) } : { ...c, below: num(v) })} />
    </>
  );
}

function ActionPart({ a, i, set, remove, choices }: {
  a: Action;
  i: number;
  set: (a: Action) => void;
  remove: () => void;
  choices: ReturnType<typeof useChoices>;
}) {
  const me = choices.me?.username;
  let body;
  if (a.type === "notify") {
    body = (
      <>
        notify{" "}
        <Select aria-label="Who to notify" className="pick-inline" value={a.targets?.length ? "me" : "saver"}
                onChange={(_, d) => set(clean({ ...a, targets: d.value === "me" && me ? [`user:${me}`] : undefined }))}>
          <option value="saver">whoever saved this</option>
          {me && <option value="me">me</option>}
        </Select>{" "}
        with <Text label="Message" value={a.message} width={28} onChange={(message) => set({ ...a, message })} />
      </>
    );
  } else if (a.type === "call") {
    body = (
      <>
        <Select aria-label="Command" className="pick-inline" value={a.command} onChange={(_, d) => set({ ...a, command: d.value })}>
          <option value="turn_on">turn on</option>
          <option value="turn_off">turn off</option>
          <option value="toggle">toggle</option>
          {!["turn_on", "turn_off", "toggle"].includes(a.command) && <option value={a.command}>{a.command}</option>}
        </Select>{" "}
        <Pick label="Device to control" value={a.target} choices={choices.devices} onChange={(target) => set({ ...a, target })} />
      </>
    );
  } else if (a.type === "sequence") {
    body = <>run <Pick label="Routine to run" value={a.ref} choices={choices.routines} onChange={(ref) => set({ ...a, ref })} /></>;
  } else {
    body = <>run the script <Pick label="Script to run" value={a.ref} choices={choices.scripts} onChange={(ref) => set({ ...a, ref })} /></>;
  }
  return (
    <li>
      {i === 0 ? "then " : "and "}
      {body}
      <Button size="small" appearance="transparent" icon={<DismissRegular />} aria-label={`Remove step ${i + 1}`} onClick={remove} />
    </li>
  );
}

const NEW_ACTION: Record<Action["type"], (c: ReturnType<typeof useChoices>) => Action> = {
  notify: () => ({ type: "notify", message: "" }),
  call: (c) => ({ type: "call", target: c.devices[0]?.value ?? "", command: "turn_on" }),
  sequence: (c) => ({ type: "sequence", ref: c.routines[0]?.value ?? "" }),
  script: (c) => ({ type: "script", ref: c.scripts[0]?.value ?? "" }),
};

/** "When UPS on battery switches to on for 2m, only if UPS runtime is below 15, then notify me and run Lab safe shutdown." */
export function SentenceBuilder({ sentence, onChange }: { sentence: Sentence; onChange: (s: Sentence) => void }) {
  const choices = useChoices();
  const a = sentence.automation;
  const update = (patch: Partial<Sentence["automation"]>) => onChange({ automation: clean({ ...a, ...patch }) });
  const actions = a.actions;
  return (
    <div className="sentence">
      <p>
        <TriggerPart t={a.triggers[0]} devices={choices.devices} set={(t) => update({ triggers: [t] })} />
        <ConditionPart c={a.conditions?.[0]} devices={choices.devices}
                       set={(c) => update({ conditions: c ? [c] : undefined })} />
      </p>
      <ol className="sentence-actions">
        {actions.map((x, i) => (
          <ActionPart key={i} a={x} i={i} choices={choices}
                      set={(n) => update({ actions: actions.map((y, j) => (j === i ? n : y)) })}
                      remove={() => actions.length > 1 && update({ actions: actions.filter((_, j) => j !== i) })} />
        ))}
      </ol>
      <div className="row start">
        {(["notify", "call", "sequence", "script"] as const).map((t) => (
          <Button key={t} size="small" icon={<AddRegular />}
                  onClick={() => update({ actions: [...actions, NEW_ACTION[t](choices)] })}>
            {{ notify: "Notify", call: "Control a device", sequence: "Run a routine", script: "Run a script" }[t]}
          </Button>
        ))}
      </div>
    </div>
  );
}
