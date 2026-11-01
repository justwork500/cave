import { Button } from "@fluentui/react-components";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import type { DashboardView, Listed } from "../api/types";
import { YamlEditor } from "../editor/YamlEditor";
import { DashboardBody } from "../pages/Dashboard";
import { dashboardPath } from "../app/shell/MenuBar";
import { DataTable, ErrorBar, Page } from "./Page";

export function Dashboards() {
  const list = useQuery({ queryKey: ["dashboards"], queryFn: () => api.get<Listed[]>("/dashboards") });
  return (
    <Page title="Dashboards">
      <ErrorBar error={list.error} />
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
  const doc = useQuery({
    queryKey: ["doc", "dashboards", slug],
    queryFn: () => api.get<{ name: string; yaml: string }>(`/dashboards/${encodeURIComponent(slug)}`),
  });
  const [text, setText] = useState<string>();
  const [previewing, setPreviewing] = useState(false);
  const preview = useQuery({
    queryKey: ["dashboards", slug, "view"],
    queryFn: () => api.get<DashboardView>(`/dashboards/${encodeURIComponent(slug)}/view`),
    enabled: previewing,
  });
  const save = useMutation({
    mutationFn: () => api.put(`/dashboards/${encodeURIComponent(slug)}`, { yaml: text ?? doc.data?.yaml ?? "" }),
    onSuccess: async () => {
      setText(undefined);
      await client.invalidateQueries({ queryKey: ["doc", "dashboards", slug] });
      await client.invalidateQueries({ queryKey: ["dashboards", slug, "view"] });
      setPreviewing(true);
    },
  });
  return (
    <Page
      title={doc.data?.name ?? slug}
      commands={
        <>
          <Button appearance="primary" disabled={save.isPending || !doc.data} onClick={() => save.mutate()}>
            Save and preview
          </Button>
          <Link to={`/admin/access#dashboard:${slug}`}>Access</Link>
        </>
      }
    >
      <ErrorBar error={doc.error ?? save.error ?? preview.error} />
      <div className="split">
        {doc.data && (
          <YamlEditor label="YAML" schema="dashboard" value={text ?? doc.data.yaml} onChange={setText} />
        )}
        <section className="preview" aria-label="Preview">
          {preview.data ? <DashboardBody view={preview.data} /> : <p className="muted">Save to see the preview.</p>}
        </section>
      </div>
    </Page>
  );
}
