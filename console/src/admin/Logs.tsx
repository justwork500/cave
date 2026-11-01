import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { DataTable, ErrorBar, Page, when } from "./Page";

interface AuditEntry {
  time: string;
  actor: string;
  action: string;
  target: string | null;
  old: unknown;
  new: unknown;
}

interface SignIn {
  username: string;
  at: string;
  result: string;
  ip: string;
}

const show = (v: unknown) => (v === null || v === undefined ? "" : JSON.stringify(v, null, 1));

export function Audit() {
  const log = useQuery({ queryKey: ["audit"], queryFn: () => api.get<AuditEntry[]>("/audit?limit=1000") });
  return (
    <Page title="Audit log">
      <ErrorBar error={log.error} />
      <DataTable<AuditEntry>
        label="Audit log"
        rows={log.data ?? []}
        rowKey={(e) => `${e.time}|${e.action}|${e.target ?? ""}|${e.actor}`}
        search={(e) => `${e.actor} ${e.action} ${e.target ?? ""}`}
        columns={[
          { label: "When", sort: (e) => e.time, render: (e) => when(e.time) },
          { label: "Who", sort: (e) => e.actor, render: (e) => e.actor },
          { label: "What", sort: (e) => e.action, render: (e) => e.action },
          { label: "On", render: (e) => e.target },
          { label: "Before", render: (e) => <pre className="value">{show(e.old)}</pre> },
          { label: "After", render: (e) => <pre className="value">{show(e.new)}</pre> },
        ]}
      />
    </Page>
  );
}

export function SignIns() {
  const log = useQuery({ queryKey: ["signins"], queryFn: () => api.get<SignIn[]>("/signin-log?limit=1000") });
  const results = [...new Set((log.data ?? []).map((s) => s.result))];
  return (
    <Page title="Sign-in log">
      <ErrorBar error={log.error} />
      <DataTable<SignIn>
        label="Sign-in log"
        rows={log.data ?? []}
        rowKey={(s) => `${s.at}|${s.username}|${s.ip}`}
        search={(s) => `${s.username} ${s.ip}`}
        filters={results.map((r) => ({ id: r, label: r.charAt(0).toUpperCase() + r.slice(1), test: (s) => s.result === r }))}
        columns={[
          { label: "When", sort: (s) => s.at, render: (s) => when(s.at) },
          { label: "Username", sort: (s) => s.username, render: (s) => s.username },
          { label: "Result", sort: (s) => s.result, render: (s) => s.result },
          { label: "From", sort: (s) => s.ip, render: (s) => s.ip },
        ]}
      />
    </Page>
  );
}
