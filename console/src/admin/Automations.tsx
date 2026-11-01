import {
  Button, Dialog, DialogActions, DialogBody, DialogContent, DialogSurface, DialogTitle, Field, Input, Select, Tab,
  TabList,
} from "@fluentui/react-components";
import { AddRegular, PlayRegular } from "@fluentui/react-icons";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { parse } from "yaml";
import { api, message } from "../api/client";
import type { Listed, Trace } from "../api/types";
import { YamlEditor } from "../editor/YamlEditor";
import { DataTable, DeleteButton, ErrorBar, Page } from "./Page";
import { RECIPES, type Recipe } from "./recipes";
import { SentenceBuilder, useChoices } from "./SentenceBuilder";
import { fromYaml, toYaml } from "./sentence";
import { TestCenter } from "./TestCenter";
import { Traces } from "./Traces";

type Kinds = "automations" | "sequences";

function RunButton({ kinds, item }: { kinds: Kinds; item: Listed }) {
  const run = useMutation({ mutationFn: () => api.post(`/${kinds}/${encodeURIComponent(item.id)}/run`) });
  if (!item.allowed) return null;
  return (
    <span className="row start">
      <Button size="small" icon={<PlayRegular />} aria-label={`Run ${item.name}`} disabled={run.isPending}
              onClick={() => run.mutate()}>
        Run
      </Button>
      <span role="status" className="muted">
        {run.isSuccess && "Started."}
        {run.isError && message(run.error)}
      </span>
    </span>
  );
}

function List({ kinds, title }: { kinds: Kinds; title: string }) {
  const list = useQuery({ queryKey: [kinds], queryFn: () => api.get<Listed[]>(`/${kinds}`) });
  const rows = list.data ?? [];
  const last = useQueries({
    queries: rows.map((r) => ({
      queryKey: ["traces", kinds, r.id],
      queryFn: () => api.get<{ trace: Trace }[]>(`/${kinds}/${encodeURIComponent(r.id)}/traces`).catch(() => []),
      enabled: r.allowed,
    })),
  });
  const outcome = (r: Listed) => last[rows.indexOf(r)]?.data?.[0]?.trace.outcome.replaceAll("_", " ") ?? "";
  return (
    <section className="stack">
      <h2>{title}</h2>
      <ErrorBar error={list.error} />
      <DataTable<Listed>
        label={title}
        rows={rows}
        rowKey={(r) => r.id}
        search={(r) => r.name}
        filters={[{ id: "failed", label: "Last run failed", test: (r) => outcome(r) === "failed" }]}
        columns={[
          {
            label: "Name",
            sort: (r) => r.name.toLowerCase(),
            render: (r) => (r.allowed ? <Link to={`/admin/automations/${kinds}/${r.id}`}>{r.name}</Link> : r.name),
          },
          { label: "Last run", sort: outcome, render: outcome },
          { label: "Actions", render: (r) => <RunButton kinds={kinds} item={r} /> },
        ]}
      />
    </section>
  );
}

export function Automations() {
  const navigate = useNavigate();
  return (
    <Page
      title="Automations"
      commands={
        <>
          <Button appearance="primary" icon={<AddRegular />} onClick={() => navigate("/admin/automations/new")}>
            New automation
          </Button>
          <Button onClick={() => navigate("/admin/test-center")}>Test Center</Button>
        </>
      }
    >
      <List kinds="automations" title="Automations" />
      <List kinds="sequences" title="Routines" />
    </Page>
  );
}

/** Lines only on one side are marked; enough to see what a save changes. */
function Diff({ before, after }: { before: string; after: string }) {
  const a = before.split("\n"), b = after.split("\n");
  const inA = new Set(a), inB = new Set(b);
  return (
    <div className="diff">
      <div>
        <h3>Before</h3>
        <pre>{a.map((l, i) => <div key={i} className={inB.has(l) ? undefined : "removed"}>{l || " "}</div>)}</pre>
      </div>
      <div>
        <h3>After</h3>
        <pre>{b.map((l, i) => <div key={i} className={inA.has(l) ? undefined : "added"}>{l || " "}</div>)}</pre>
      </div>
    </div>
  );
}

function RecipePicker({ onDone }: { onDone: () => void }) {
  const client = useQueryClient();
  const choices = useChoices();
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const create = useMutation({
    mutationFn: async (r: Recipe) => {
      for (const doc of r.build(values)) {
        // create=true: the server refuses rather than replacing an automation with the same id
        await api.put(`/automations/${encodeURIComponent(doc.automation.id)}?create=true`, { yaml: toYaml(doc) });
      }
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["automations"] });
      onDone();
    },
  });
  if (!recipe) {
    return (
      <ul className="recipes">
        {RECIPES.map((r) => (
          <li key={r.id}>
            <Button disabled={r.later} onClick={() => setRecipe(r)}>
              {r.title}
              {r.later && " (coming later)"}
            </Button>
          </li>
        ))}
      </ul>
    );
  }
  const options = (kind: string) =>
    kind === "device" ? choices.devices : kind === "routine" ? choices.routines : kind === "script" ? choices.scripts : null;
  return (
    <form className="stack" onSubmit={(e) => {
      e.preventDefault();
      create.mutate(recipe);
    }}>
      <h2>{recipe.title}</h2>
      {recipe.blanks.map((b) => {
        const opts = options(b.kind);
        return (
          <Field key={b.id} label={b.label}>
            {opts ? (
              <Select value={values[b.id] ?? ""} onChange={(_, d) => setValues({ ...values, [b.id]: d.value })}>
                <option value="">Choose…</option>
                {opts.map((o) => <option key={o.value} value={o.value}>{o.name}</option>)}
              </Select>
            ) : (
              <Input value={values[b.id] ?? ""} placeholder={b.example}
                     onChange={(_, d) => setValues({ ...values, [b.id]: d.value })} />
            )}
          </Field>
        );
      })}
      <ErrorBar error={create.error} />
      <div className="row start">
        <Button onClick={() => setRecipe(null)}>Back</Button>
        <Button appearance="primary" type="submit"
                disabled={recipe.blanks.some((b) => !values[b.id]) || create.isPending}>
          Create
        </Button>
      </div>
    </form>
  );
}

const BLANK = `automation:
  id: "new-automation"
  name: "New automation"
  triggers:
    - type: "time"
      at: "07:00"
  actions:
    - type: "notify"
      message: "Good morning"
`;

export function AutomationEditor() {
  const params = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const isNew = !params.id;
  const kinds = (params.kinds ?? "automations") as Kinds;
  const doc = useQuery({
    queryKey: ["doc", kinds, params.id],
    queryFn: () => api.get<{ name: string; yaml: string }>(`/${kinds}/${encodeURIComponent(params.id ?? "")}`),
    enabled: !isNew,
  });
  const [edited, setEdited] = useState<string>();
  const [tab, setTab] = useState(kinds === "sequences" ? "advanced" : "simple");
  const [reviewing, setReviewing] = useState(false);
  const original = isNew ? "" : (doc.data?.yaml ?? "");
  const text = edited ?? (isNew ? "" : original);
  const sentence = kinds === "automations" && text ? fromYaml(text) : null;
  const id = params.id ?? (() => {
    try {
      const parsed: unknown = parse(text, { version: "1.1" });
      return String((parsed as { automation?: { id?: unknown } }).automation?.id ?? "");
    } catch {
      return "";
    }
  })();
  const save = useMutation({
    mutationFn: () => api.put(`/${kinds}/${encodeURIComponent(id)}${isNew ? "?create=true" : ""}`, { yaml: text }),
    onSuccess: () => {
      setReviewing(false);
      void client.invalidateQueries({ queryKey: [kinds] });
      void client.invalidateQueries({ queryKey: ["doc", kinds, id] });
      if (isNew) navigate(`/admin/automations/${kinds}/${id}`, { replace: true });
      else setEdited(undefined);
    },
    onError: () => setReviewing(false),
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/${kinds}/${encodeURIComponent(id)}`),
    onSuccess: async () => {
      client.removeQueries({ queryKey: ["doc", kinds, id] });
      await client.invalidateQueries({ queryKey: [kinds] });
      navigate("/admin/automations");
    },
  });
  const changed = text !== original && text !== "";
  const blockedHere = tab === "simple" && !sentence;

  return (
    <Page
      title={doc.data?.name ?? (isNew ? "New automation" : "Automation")}
      commands={
        <>
          <Button appearance="primary" disabled={!changed || blockedHere || !id || save.isPending}
                  onClick={() => setReviewing(true)}>
            Save
          </Button>
          {!isNew && doc.data && (
            <DeleteButton what={kinds === "sequences" ? "routine" : "automation"} name={doc.data.name}
                          pending={remove.isPending} onDelete={() => remove.mutate()} />
          )}
        </>
      }
    >
      <ErrorBar error={doc.error ?? save.error ?? remove.error} />
      <TabList selectedValue={tab} onTabSelect={(_, d) => setTab(String(d.value))}>
        <Tab value="simple">Simple</Tab>
        <Tab value="advanced">Advanced</Tab>
        {!isNew && <Tab value="runs">Runs</Tab>}
        <Tab value="test">Test</Tab>
      </TabList>
      {tab === "simple" && (
        isNew && !text ? (
          <div className="stack">
            <p>Start from a recipe, or from a blank automation.</p>
            <RecipePicker onDone={() => navigate("/admin/automations")} />
            <div><Button onClick={() => setEdited(BLANK)}>Start blank</Button></div>
          </div>
        ) : sentence ? (
          <SentenceBuilder sentence={sentence} onChange={(s) => setEdited(toYaml(s))} />
        ) : (
          <p className="muted">
            {kinds === "sequences"
              ? "Routines are edited in Advanced."
              : "This automation uses features the Simple view can't show; use Advanced."}
          </p>
        )
      )}
      {tab === "advanced" && (
        <YamlEditor label="YAML" value={text} onChange={setEdited} schema={kinds === "sequences" ? "sequence" : "automation"} />
      )}
      {tab === "runs" && params.id && <Traces kinds={kinds} id={params.id} />}
      {tab === "test" && id && (
        <TestCenter draft={{ kind: kinds === "sequences" ? "sequence" : "automation", id, yaml: text }} />
      )}
      <Dialog open={reviewing} onOpenChange={(_, d) => setReviewing(d.open)}>
        <DialogSurface className="wide-dialog">
          <DialogBody>
            <DialogTitle>Save these changes?</DialogTitle>
            <DialogContent>
              <Diff before={original} after={text} />
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setReviewing(false)}>Keep editing</Button>
              <Button appearance="primary" disabled={save.isPending} onClick={() => save.mutate()}>
                Save changes
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </Page>
  );
}
