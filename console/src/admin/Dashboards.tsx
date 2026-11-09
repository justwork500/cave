import {
  Button, Dialog, DialogActions, DialogBody, DialogContent, DialogSurface, DialogTitle, Input, Tab, TabList,
} from "@fluentui/react-components";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api } from "../api/client";
import type { DashboardView, Listed } from "../api/types";
import { YamlEditor } from "../editor/YamlEditor";
import { DashboardBody } from "../pages/Dashboard";
import { dashboardPath } from "../app/nav";
import { load, save as savePref } from "../app/prefs";
import { Builder } from "./builder/Builder";
import { type Draft, hasComments, parseDraft, writeDraft } from "./builder/model";
import { DataTable, DeleteButton, ErrorBar, Page } from "./Page";

/** "Garage tablet" → "garage_tablet": the file name the server accepts. */
export const slugOf = (name: string) =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 64);

const starter = (name: string) => `dashboard:
  title: ${JSON.stringify(name)}
  views:
    - id: main
      title: Main
      sections:
        - title: Main
          cards: []
`;

export function Dashboards() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const list = useQuery({ queryKey: ["dashboards"], queryFn: () => api.get<Listed[]>("/dashboards") });
  const [name, setName] = useState("");
  const slug = slugOf(name);
  const create = useMutation({
    // create=true: the server refuses rather than replacing a dashboard with the same name
    mutationFn: () => api.put(`/dashboards/${slug}?create=true`, { yaml: starter(name.trim()) }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["dashboards"] });
      navigate(`/admin/dashboards/${slug}`);
    },
  });
  return (
    <Page
      title="Dashboards"
      commands={
        <form className="row start" onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}>
          <Input aria-label="New dashboard name" placeholder="New dashboard" value={name}
                 onChange={(_, d) => setName(d.value)} />
          <Button appearance="primary" type="submit" disabled={!slug || create.isPending}>Create dashboard</Button>
        </form>
      }
    >
      <ErrorBar error={list.error ?? create.error} />
      <DataTable<Listed>
        label="Dashboards"
        rows={list.data ?? []}
        rowKey={(d) => d.id}
        search={(d) => d.name}
        columns={[
          { label: "Name", sort: (d) => d.name.toLowerCase(), render: (d) => d.name },
          {
            label: "Actions",
            render: (d) => (
              <span className="row start">
                {d.allowed && <Link to={dashboardPath(`dashboard:${d.id}`)}>Open</Link>}
                <Link to={`/admin/dashboards/${d.id}`} aria-label={`Edit ${d.name}`}>Edit</Link>
                <Link to={`/admin/access#dashboard:${d.id}`} aria-label={`Access for ${d.name}`}>Access</Link>
              </span>
            ),
          },
        ]}
      />
    </Page>
  );
}

// shortcut: preview shows the saved version; add a draft-view endpoint if editing feels slow
export function DashboardEditor() {
  const { slug = "" } = useParams();
  const client = useQueryClient();
  const navigate = useNavigate();
  const doc = useQuery({
    queryKey: ["doc", "dashboards", slug],
    queryFn: () => api.get<{ name: string; yaml: string }>(`/dashboards/${encodeURIComponent(slug)}`),
  });
  const [text, setText] = useState<string>();
  const [mode, setMode] = useState<"visual" | "yaml">();
  const [waiting, setWaiting] = useState<Draft>(); // a visual change held until comments are dealt with
  const [previewing, setPreviewing] = useState(false);
  const yaml = text ?? doc.data?.yaml ?? "";
  const parsed = doc.data ? parseDraft(yaml) : undefined;
  const draft = parsed && "draft" in parsed ? parsed.draft : undefined;
  const reason = parsed && "reason" in parsed ? parsed.reason : undefined;
  const shown = draft && mode !== "yaml" ? "visual" : "yaml";
  const unsaved = text !== undefined && text !== doc.data?.yaml;
  const preview = useQuery({
    queryKey: ["dashboards", slug, "view"],
    queryFn: () => api.get<DashboardView>(`/dashboards/${encodeURIComponent(slug)}/view`),
    enabled: previewing && shown === "yaml",
  });
  const save = useMutation({
    mutationFn: () => api.put(`/dashboards/${encodeURIComponent(slug)}`, { yaml }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["doc", "dashboards", slug] });
      await client.invalidateQueries({ queryKey: ["dashboards", slug, "view"] });
      setText(undefined);
      setPreviewing(true);
    },
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/dashboards/${encodeURIComponent(slug)}`),
    onSuccess: async () => {
      client.removeQueries({ queryKey: ["dashboards", slug] });
      if (load("defaultDashboard") === `dashboard:${slug}`) savePref("defaultDashboard", "");
      await client.invalidateQueries({ queryKey: ["dashboards"] });
      navigate("/admin/dashboards");
    },
  });
  useEffect(() => {
    if (!unsaved) return undefined;
    // shortcut: BrowserRouter has no in-app blocker, move to a data router to warn between pages
    const ask = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", ask);
    return () => window.removeEventListener("beforeunload", ask);
  }, [unsaved]);

  const change = (next: Draft) => {
    if (hasComments(yaml)) setWaiting(next);
    else setText(writeDraft(next));
  };

  return (
    <Page
      title={doc.data?.name ?? slug}
      commands={
        <>
          <Button appearance="primary" disabled={save.isPending || !doc.data} onClick={() => save.mutate()}>
            {shown === "yaml" ? "Save and preview" : "Save"}
          </Button>
          <Button disabled={!unsaved} onClick={() => setText(undefined)}>Discard</Button>
          <Link to={`/admin/access#dashboard:${slug}`}>Access</Link>
          {doc.data && (
            <DeleteButton what="dashboard" name={doc.data.name} pending={remove.isPending}
                          onDelete={() => remove.mutate()} />
          )}
        </>
      }
    >
      <ErrorBar error={doc.error ?? save.error ?? preview.error ?? remove.error} />
      {doc.data && (
        <div className="row start">
          <TabList selectedValue={shown} onTabSelect={(_, t) => setMode(t.value as "visual" | "yaml")}>
            <Tab value="visual" disabled={!draft}>Visual</Tab>
            <Tab value="yaml">YAML</Tab>
          </TabList>
          {reason && <span className="muted">{reason}</span>}
        </div>
      )}
      {shown === "visual" && draft && <Builder draft={draft} onChange={change} />}
      {shown === "yaml" && (
        <div className="split">
          {doc.data && <YamlEditor label="YAML" schema="dashboard" value={yaml} onChange={setText} />}
          <section className="preview" aria-label="Preview">
            {preview.data ? <DashboardBody view={preview.data} /> : <p className="muted">Save to see the preview.</p>}
          </section>
        </div>
      )}
      <Dialog open={waiting !== undefined} onOpenChange={(_, d) => !d.open && setWaiting(undefined)}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>Remove the comments in this YAML?</DialogTitle>
            <DialogContent>The visual builder rewrites the YAML, so any comments in it will be removed.</DialogContent>
            <DialogActions>
              <Button onClick={() => {
                setWaiting(undefined);
                setMode("yaml");
              }}>
                Keep editing in YAML
              </Button>
              <Button appearance="primary" onClick={() => {
                if (waiting) setText(writeDraft(waiting));
                setWaiting(undefined);
              }}>
                Remove comments
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </Page>
  );
}
