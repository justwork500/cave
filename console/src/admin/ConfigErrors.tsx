import { Button } from "@fluentui/react-components";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../api/client";
import { ErrorBar } from "./Page";

/** Where each file opens: automations/ups.yaml → the automation editor, and so on. */
export function editorFor(file: string): string | null {
  const m = /^(automations|sequences|dashboards)\/([a-z0-9_-]+)\.yaml$/.exec(file);
  if (m?.[1] === "dashboards") return `/admin/dashboards/${m[2]}`;
  if (m) return `/admin/automations/${m[1]}/${m[2]}`;
  const s = /^scripts\/(.+)$/.exec(file);
  return s?.[1] ? `/admin/scripts/${encodeURIComponent(s[1])}` : null;
}

/** Files that didn't load, with the line to look at. */
export function ConfigErrors() {
  const client = useQueryClient();
  const errors = useQuery({ queryKey: ["config-errors"], queryFn: () => api.get<Record<string, string>>("/config/errors") });
  const reload = useMutation({
    mutationFn: () => api.post("/config/reload"),
    onSuccess: () => void client.invalidateQueries(),
  });
  const entries = Object.entries(errors.data ?? {});
  return (
    <section className="stack">
      <h2>Config files</h2>
      <ErrorBar error={errors.error ?? reload.error} />
      {errors.isSuccess && entries.length === 0 && <p className="muted">Every config file loaded.</p>}
      <ul className="config-errors">
        {entries.map(([file, text]) => {
          const where = /^([^:]+(?::\d+)?)/.exec(text)?.[1] ?? file;
          const to = editorFor(file);
          return (
            <li key={file}>
              {to ? <Link to={to}>{where}</Link> : <code>{where}</code>}
              <span>{text.slice(where.length).replace(/^:\s*/, "")}</span>
            </li>
          );
        })}
      </ul>
      <div>
        <Button onClick={() => reload.mutate()} disabled={reload.isPending}>
          Reload config files
        </Button>
      </div>
    </section>
  );
}
