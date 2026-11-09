import {
  Badge, Button, Checkbox, Field, Input, MessageBar, MessageBarBody, Select,
} from "@fluentui/react-components";
import { PlayRegular } from "@fluentui/react-icons";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api, message } from "../api/client";
import { YamlEditor } from "../editor/YamlEditor";
import { DataTable, ErrorBar, Page, when } from "./Page";

interface Param {
  type: "int" | "float" | "str" | "bool";
  default: unknown;
  min: number | null;
  max: number | null;
  choices: string[] | null;
}

interface Script {
  file: string;
  name: string;
  language: "ps1" | "py" | "sh";
  text: string;
  header: { name: string; target: string; timeout: string; params: Record<string, Param>; secrets: string[] };
}

interface Run {
  id: number;
  started_by: string;
  started_at: string;
  duration_ms: number | null;
  outcome: string;
  log: string[];
  result: unknown;
}

const LANGUAGE = { ps1: "PowerShell", py: "Python", sh: "Shell" } as const;
const EDITOR = { ps1: "powershell", py: "python", sh: "shell" } as const;

interface Listed {
  file: string;
  name: string;
  language: Script["language"];
  allowed: boolean;
}

const runs = (file: string) => api.get<Run[]>(`/scripts/${encodeURIComponent(file)}/runs`);

/** The Scripts page: every script with its language and how its last run ended. */
export function Scripts() {
  const list = useQuery({
    queryKey: ["scripts"],
    queryFn: () => api.get<Listed[]>("/scripts"),
  });
  const rows = list.data ?? [];
  const last = useQueries({
    queries: rows.map((s) => ({ queryKey: ["script-runs", s.file], queryFn: () => runs(s.file).catch(() => []) })),
  });
  const outcome = (file: string) => last[rows.findIndex((r) => r.file === file)]?.data?.[0]?.outcome ?? "";
  return (
    <Page title="Scripts">
      <ErrorBar error={list.error} />
      <DataTable<Listed>
        label="Scripts"
        rows={rows}
        rowKey={(s) => s.file}
        search={(s) => `${s.name} ${s.file}`}
        filters={(["ps1", "py", "sh"] as const).map((l) => ({ id: l, label: LANGUAGE[l], test: (s) => s.language === l }))}
        columns={[
          { label: "Name", sort: (s) => s.name.toLowerCase(),
            render: (s) => <Link to={`/admin/scripts/${encodeURIComponent(s.file)}`}>{s.name}</Link> },
          { label: "Language", sort: (s) => s.language,
            render: (s) => <Badge appearance="tint" color="brand">{LANGUAGE[s.language]}</Badge> },
          { label: "Last run", render: (s) => outcome(s.file).replaceAll("_", " ") },
        ]}
      />
    </Page>
  );
}

function initial(params: Record<string, Param>) {
  return Object.fromEntries(Object.entries(params).map(([k, p]) => [k, p.default ?? (p.type === "bool" ? false : "")]));
}

function TestRun({ script }: { script: Script }) {
  const client = useQueryClient();
  const [values, setValues] = useState<Record<string, unknown>>(() => initial(script.header.params));
  const run = useMutation({
    mutationFn: () => api.post<{ result: unknown }>(`/scripts/${encodeURIComponent(script.file)}/run`, { params: values }),
    onSettled: () => void client.invalidateQueries({ queryKey: ["script-runs", script.file] }),
  });
  const set = (k: string, v: unknown) => setValues({ ...values, [k]: v });
  return (
    <form className="stack" onSubmit={(e) => {
      e.preventDefault();
      run.mutate();
    }}>
      <h2>Test run</h2>
      {Object.entries(script.header.params).map(([k, p]) => {
        const v = values[k];
        if (p.type === "bool") return <Checkbox key={k} label={k} checked={v === true} onChange={(_, d) => set(k, d.checked === true)} />;
        if (p.choices) {
          return (
            <Field key={k} label={k}>
              <Select value={String(v)} onChange={(_, d) => set(k, d.value)}>
                {p.choices.map((c) => <option key={c}>{c}</option>)}
              </Select>
            </Field>
          );
        }
        const numeric = p.type === "int" || p.type === "float";
        const hint = numeric && (p.min !== null || p.max !== null) ? `From ${p.min ?? "any"} to ${p.max ?? "any"}.` : undefined;
        return (
          <Field key={k} label={k} hint={hint}>
            <Input
              type={numeric ? "number" : "text"}
              step={p.type === "float" ? "any" : 1}
              min={p.min ?? undefined}
              max={p.max ?? undefined}
              value={v === undefined || v === null ? "" : String(v)}
              onChange={(_, d) => set(k, numeric ? (d.value === "" ? "" : Number(d.value)) : d.value)}
            />
          </Field>
        );
      })}
      <div className="row start">
        <Button appearance="primary" type="submit" icon={<PlayRegular />} disabled={run.isPending}>
          Test run
        </Button>
      </div>
      {run.isSuccess && (
        <div role="status">
          <p>Finished. The script returned:</p>
          <pre className="output">{JSON.stringify(run.data.result, null, 2)}</pre>
        </div>
      )}
      {run.isError && (
        <div role="alert" className="run-failed">
          <p>The run failed. The last lines it printed:</p>
          <pre className="output">{message(run.error)}</pre>
        </div>
      )}
    </form>
  );
}

/** Edit one script, test-run it with parameters, and see its recent runs. */
export function ScriptEditor() {
  const { file = "" } = useParams();
  const client = useQueryClient();
  const script = useQuery({ queryKey: ["script", file], queryFn: () => api.get<Script>(`/scripts/${encodeURIComponent(file)}`) });
  const log = useQuery({ queryKey: ["script-runs", file], queryFn: () => runs(file) });
  const [text, setText] = useState<string>();
  const save = useMutation({
    mutationFn: () => api.put<Script>(`/scripts/${encodeURIComponent(file)}`, { text }),
    onSuccess: (s) => {
      client.setQueryData(["script", file], s);
      setText(undefined);
    },
  });
  const s = script.data;
  return (
    <Page
      title={s?.name ?? file}
      commands={
        <Button appearance="primary" disabled={text === undefined || text === s?.text || save.isPending}
                onClick={() => save.mutate()}>
          Save
        </Button>
      }
    >
      <ErrorBar error={script.error ?? save.error} />
      {s && (
        <>
          <p className="muted">
            {LANGUAGE[s.language]}, runs in the {s.header.target}, stops after {s.header.timeout.replace(/^PT/, "").toLowerCase()}.
          </p>
          {s.header.secrets.length > 0 && (
            <MessageBar intent="warning">
              <MessageBarBody>
                This script uses secrets ({s.header.secrets.join(", ")}). Only an Admin can save this.
              </MessageBarBody>
            </MessageBar>
          )}
          <YamlEditor label="Script" language={EDITOR[s.language]} value={text ?? s.text} onChange={setText} />
          <TestRun script={s} />
          <section className="stack">
            <h2>Runs</h2>
            {log.data?.length === 0 && <p className="muted">No runs yet.</p>}
            {log.data?.map((r) => (
              <details key={r.id} className="run">
                <summary>
                  {when(r.started_at)}: {r.outcome.replaceAll("_", " ")}
                  {r.duration_ms !== null && ` in ${(r.duration_ms / 1000).toFixed(1)} s`}, by {r.started_by}
                </summary>
                <pre className="output">{r.log.join("\n") || "(nothing printed)"}</pre>
              </details>
            ))}
          </section>
        </>
      )}
    </Page>
  );
}
