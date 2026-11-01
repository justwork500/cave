import { Button, Field, Input, Select, Textarea } from "@fluentui/react-components";
import { PlayRegular } from "@fluentui/react-icons";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { parse } from "yaml";
import { api } from "../api/client";
import type { EntityView, Listed, Trace } from "../api/types";
import { isFull } from "../cards/entity";
import { ErrorBar, Page } from "./Page";
import { TraceView } from "./Traces";

export interface Draft {
  kind: "automation" | "sequence";
  id: string;
  yaml: string;
}

const ENTITY = /^[a-z_]+\.[a-z0-9_]+$/;
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;

/** What the file names: devices it reads or controls, scripts it runs, and every step's path. */
export function references(yaml: string) {
  const devices = new Set<string>();
  const scripts = new Set<string>();
  const steps: { path: string; label: string; depth: number }[] = [];
  let doc: unknown;
  try {
    doc = parse(yaml, { version: "1.1" });
  } catch {
    return { devices: [], scripts: [], steps };
  }
  const walk = (v: unknown) => {
    if (Array.isArray(v)) v.forEach(walk);
    else if (isObj(v)) {
      for (const [k, x] of Object.entries(v)) {
        if ((k === "entity" || k === "target") && typeof x === "string" && ENTITY.test(x)) devices.add(x);
        if (k === "type" && x === "script" && typeof v.ref === "string") scripts.add(v.ref);
        walk(x);
      }
    }
  };
  walk(doc);
  const tree = (actions: unknown, base: string, depth: number) => {
    if (!Array.isArray(actions)) return;
    actions.forEach((a, i) => {
      if (!isObj(a)) return;
      const path = `${base}[${i}]`;
      steps.push({ path, label: `${String(a.type)}${typeof a.ref === "string" ? ` ${a.ref}` : ""}`, depth });
      if (Array.isArray(a.options)) {
        a.options.forEach((o, j) => isObj(o) && tree(o.actions, `${path}.options[${j}].actions`, depth + 1));
      }
      tree(a.default, `${path}.default`, depth + 1);
      if (a.type === "repeat") tree(a.actions, `${path}.actions`, depth + 1);
    });
  };
  const body = isObj(doc) ? (doc.automation ?? doc.sequence) : undefined;
  if (isObj(body)) tree(body.actions, "actions", 0);
  return { devices: [...devices], scripts: [...scripts], steps };
}

/** Run an automation or routine against made-up device values. Nothing real happens. */
export function TestCenter({ draft }: { draft?: Draft }) {
  const automations = useQuery({ queryKey: ["automations"], queryFn: () => api.get<Listed[]>("/automations") });
  const sequences = useQuery({ queryKey: ["sequences"], queryFn: () => api.get<Listed[]>("/sequences") });
  const states = useQuery({ queryKey: ["states"], queryFn: () => api.get<EntityView[]>("/states") });
  const [picked, setPicked] = useState("");
  const [kind, id] = (draft ? `${draft.kind}:${draft.id}` : picked).split(":") as [Draft["kind"], string];
  const saved = useQuery({
    queryKey: ["doc", kind, id],
    queryFn: () => api.get<{ yaml: string }>(`/${kind}s/${encodeURIComponent(id)}`),
    enabled: Boolean(id) && !draft,
  });
  const yaml = draft?.yaml ?? saved.data?.yaml ?? "";
  const refs = references(yaml);
  const [values, setValues] = useState<Record<string, string>>({});
  const [samples, setSamples] = useState<Record<string, string>>({});
  const [startAt, setStartAt] = useState("");
  const [trigger, setTrigger] = useState("");

  const run = useMutation({
    mutationFn: () => {
      const sampleObjs = Object.fromEntries(
        Object.entries(samples).filter(([, v]) => v.trim()).map(([k, v]) => [k, JSON.parse(v) as object]),
      );
      return api.post<{ trace: Trace }>("/test-center/run", {
        kind, id,
        yaml: draft?.yaml,
        trigger: trigger.trim() ? (JSON.parse(trigger) as object) : undefined,
        states: Object.fromEntries(Object.entries(values).filter(([, v]) => v !== "")),
        start_at: startAt || undefined,
        script_samples: sampleObjs,
      });
    },
  });
  const name = (e: string) => states.data?.find((s) => s.entity_id === e)?.name ?? e;
  const current = (e: string) => {
    const s = states.data?.find((x) => x.entity_id === e);
    return s && isFull(s) ? (s.state ?? "") : "";
  };
  const summary = run.data?.trace.steps.find((s) => s.type === "summary");
  const shown = run.data && { ...run.data.trace, steps: run.data.trace.steps.filter((s) => s.type !== "summary") };

  const body = (
    <div className="test-center stack">
      {!draft && (
        <Field label="Automation or routine">
          <Select value={picked} onChange={(_, d) => {
            setPicked(d.value);
            setValues({});
            setStartAt("");
          }}>
            <option value="">Choose…</option>
            {automations.data?.filter((a) => a.allowed).map((a) => (
              <option key={a.id} value={`automation:${a.id}`}>{a.name}</option>
            ))}
            {sequences.data?.filter((s) => s.allowed).map((s) => (
              <option key={s.id} value={`sequence:${s.id}`}>Routine: {s.name}</option>
            ))}
          </Select>
        </Field>
      )}
      <ErrorBar error={saved.error} />
      {yaml && (
        <>
          {refs.devices.length > 0 && (
            <fieldset className="stack tight">
              <legend>Pretend these devices read</legend>
              {refs.devices.map((e) => (
                <Field key={e} label={name(e)}>
                  <Input
                    placeholder={current(e) ? `now ${current(e)}` : "as it is now"}
                    value={values[e] ?? ""}
                    onChange={(_, d) => setValues({ ...values, [e]: d.value })}
                  />
                </Field>
              ))}
            </fieldset>
          )}
          {kind === "automation" && (
            <Field label="Trigger details (optional)" hint='JSON, like {"to_state": "on"}. Empty means no trigger data.'>
              <Input value={trigger} onChange={(_, d) => setTrigger(d.value)} />
            </Field>
          )}
          <Field label="Start at step" hint="Skips the conditions and everything before it.">
            <Select value={startAt} onChange={(_, d) => setStartAt(d.value)}>
              <option value="">The beginning</option>
              {refs.steps.map((s) => (
                <option key={s.path} value={s.path}>
                  {"  ".repeat(s.depth)}
                  {s.path}: {s.label}
                </option>
              ))}
            </Select>
          </Field>
          {refs.scripts.map((ref) => (
            <Field key={ref} label={`Pretend ${ref} returned`} hint="JSON. Empty uses the sample from the script's header.">
              <Textarea value={samples[ref] ?? ""} onChange={(_, d) => setSamples({ ...samples, [ref]: d.value })} />
            </Field>
          ))}
          <div className="row start">
            <Button appearance="primary" icon={<PlayRegular />} disabled={run.isPending} onClick={() => run.mutate()}>
              Run test
            </Button>
          </div>
        </>
      )}
      <ErrorBar error={run.error instanceof SyntaxError ? null : run.error} />
      {run.error instanceof SyntaxError && <p role="alert">One of the JSON boxes isn't valid JSON.</p>}
      {summary && (
        <p role="status" className="summary-box">
          {summary.detail}
        </p>
      )}
      {shown && <TraceView trace={shown} />}
    </div>
  );
  return draft ? body : <Page title="Test Center">{body}</Page>;
}
