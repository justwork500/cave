import {
  Button, Dialog, DialogActions, DialogBody, DialogContent, DialogSurface, DialogTitle, Select, Switch, Tab, TabList,
} from "@fluentui/react-components";
import { DismissRegular } from "@fluentui/react-icons";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useLocation } from "react-router";
import { api } from "../api/client";
import type { Assignment, Item } from "../api/types";
import type { Group } from "./Groups";
import { DataTable, ErrorBar, Page, UndoBar } from "./Page";
import type { Screen } from "./Screens";
import { ROLES, type User } from "./Users";

type Field = "status" | "visibility" | "others_see" | "network";
const KINDS: { id: Assignment["kind"]; label: string }[] = [
  { id: "user", label: "Users" },
  { id: "group", label: "Groups" },
  { id: "role", label: "Roles" },
  { id: "screen", label: "Screens" },
];
const TYPE = { dashboard: "Dashboard", section: "Console section", action: "Action", feature: "Feature" };
const FIELD_NAME: Record<Field, string> = {
  status: "Status", visibility: "Visibility", others_see: "Others see it", network: "Network",
};

function useTargets() {
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>("/users") });
  const groups = useQuery({ queryKey: ["groups"], queryFn: () => api.get<Group[]>("/groups") });
  const screens = useQuery({ queryKey: ["screens"], queryFn: () => api.get<Screen[]>("/screens") });
  const targets: Record<Assignment["kind"], { id: string; name: string }[]> = {
    user: (users.data ?? []).map((u) => ({ id: u.id, name: u.display_name || u.username })),
    group: (groups.data ?? []).map((g) => ({ id: g.id, name: g.name })),
    role: ROLES,
    screen: (screens.data ?? []).filter((s) => s.status !== "revoked").map((s) => ({ id: s.id, name: s.name })),
  };
  const nameOf = (a: Assignment) => targets[a.kind].find((t) => t.id === a.id)?.name ?? a.id;
  return { targets, nameOf };
}

function Picker({ item, current, targets, onAdd, onClose }: {
  item: Item;
  current: Assignment[];
  targets: ReturnType<typeof useTargets>["targets"];
  onAdd: (a: Assignment) => void;
  onClose: () => void;
}) {
  const [kind, setKind] = useState<Assignment["kind"]>("user");
  const has = (id: string) => current.some((a) => a.kind === kind && a.id === id);
  return (
    <Dialog open onOpenChange={(_, d) => !d.open && onClose()}>
      <DialogSurface>
        <DialogBody>
          <DialogTitle>Assign {item.name}</DialogTitle>
          <DialogContent className="stack">
            <TabList selectedValue={kind} onTabSelect={(_, d) => setKind(d.value as Assignment["kind"])}>
              {KINDS.map((k) => (
                <Tab key={k.id} value={k.id}>
                  {k.label}
                </Tab>
              ))}
            </TabList>
            <ul className="pick">
              {targets[kind].map((t) => (
                <li key={t.id}>
                  <Button
                    disabled={has(t.id)}
                    aria-label={`Add ${t.name}`}
                    onClick={() => onAdd({ kind, id: t.id })}
                  >
                    {t.name}
                    {has(t.id) && " (assigned)"}
                  </Button>
                </li>
              ))}
              {targets[kind].length === 0 && <li className="muted">None yet.</li>}
            </ul>
          </DialogContent>
          <DialogActions>
            <Button appearance="primary" onClick={onClose}>
              Done
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}

/** One row per item: enable/disable, show/hide/restrict, and who it's restricted to. Saves per change. */
export function Access() {
  const client = useQueryClient();
  const items = useQuery({ queryKey: ["items"], queryFn: () => api.get<Item[]>("/items") });
  const rows = items.data ?? [];
  const assigned = useQueries({
    queries: rows.map((i) => ({
      queryKey: ["assignments", i.id],
      queryFn: () => api.get<Assignment[]>(`/items/${encodeURIComponent(i.id)}/assignments`),
    })),
  });
  const assignmentsOf = (i: Item) => assigned[rows.indexOf(i)]?.data ?? [];
  const { targets, nameOf } = useTargets();
  const [picking, setPicking] = useState<Item | null>(null);
  const [undo, setUndo] = useState<{ item: Item; field: Field; old: string } | null>(null);
  const { hash } = useLocation();
  useEffect(() => {  // links like /admin/access#dashboard:kids land on that row
    if (hash && items.data) document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView({ block: "center" });
  }, [hash, items.data]);

  const patch = useMutation({
    mutationFn: ({ item, field, value }: { item: Item; field: Field; value: string }) =>
      api.patch<Item>(`/items/${encodeURIComponent(item.id)}`, { [field]: value }),
    onSuccess: (updated) =>
      client.setQueryData<Item[]>(["items"], (old) => old?.map((i) => (i.id === updated.id ? { ...i, ...updated } : i))),
  });
  const change = (item: Item, field: Field, value: string) => {
    setUndo({ item, field, old: String(item[field]) });
    patch.mutate({ item, field, value });
  };
  const assign = useMutation({
    mutationFn: ({ item, list }: { item: Item; list: Assignment[] }) =>
      api.put<Assignment[]>(`/items/${encodeURIComponent(item.id)}/assignments`, list),
    onSuccess: (list, { item }) => client.setQueryData(["assignments", item.id], list),
  });

  return (
    <Page title="Access">
      <p className="muted">
        Restrict an item to choose who can use it. Anything put on a dashboard can be seen and used by everyone who can
        open that dashboard.
      </p>
      <ErrorBar error={items.error ?? patch.error ?? assign.error} />
      {undo && patch.isSuccess && (
        <UndoBar
          text={`${FIELD_NAME[undo.field]} for ${undo.item.name} changed.`}
          onUndo={() => {
            patch.mutate({ item: undo.item, field: undo.field, value: undo.old });
            setUndo(null);
          }}
          onDismiss={() => setUndo(null)}
        />
      )}
      <DataTable<Item>
        label="Access"
        rows={rows}
        rowKey={(i) => i.id}
        rowId={(i) => i.id}
        rowClass={(i) => (hash === `#${i.id}` ? "target" : undefined)}
        search={(i) => `${i.name} ${TYPE[i.kind]}`}
        filters={[
          { id: "dashboard", label: "Dashboards", test: (i) => i.kind === "dashboard" },
          { id: "section", label: "Console sections", test: (i) => i.kind === "section" },
          { id: "action", label: "Actions", test: (i) => i.kind === "action" },
          { id: "restricted", label: "Restricted", test: (i) => i.visibility === "restrict" },
        ]}
        columns={[
          { label: "Name", sort: (i) => i.name.toLowerCase(), render: (i) => i.name },
          { label: "Type", sort: (i) => i.kind, render: (i) => TYPE[i.kind] },
          {
            label: "Status",
            render: (i) => (
              <Switch
                aria-label={`${i.name} enabled`}
                checked={i.status === "enabled"}
                onChange={(_, d) => change(i, "status", d.checked ? "enabled" : "disabled")}
              />
            ),
          },
          {
            label: "Visibility",
            render: (i) => (
              <div className="stack tight">
                <Select
                  aria-label={`Visibility for ${i.name}`}
                  value={i.visibility}
                  onChange={(_, d) => change(i, "visibility", d.value)}
                >
                  <option value="show">Show</option>
                  <option value="hide">Hide</option>
                  <option value="restrict">Restrict</option>
                </Select>
                {i.visibility === "restrict" && (
                  <Select
                    aria-label={`Others see ${i.name}`}
                    value={i.others_see}
                    onChange={(_, d) => change(i, "others_see", d.value)}
                  >
                    <option value="locked">Others see it locked</option>
                    <option value="none">Others don't see it</option>
                  </Select>
                )}
              </div>
            ),
          },
          {
            label: "Network",
            render: (i) => (
              <Select aria-label={`Network for ${i.name}`} value={i.network}
                      onChange={(_, d) => change(i, "network", d.value)}>
                <option value="anywhere">Anywhere</option>
                <option value="local">Local network only</option>
              </Select>
            ),
          },
          {
            label: "Assigned to",
            render: (i) => {
              const list = assignmentsOf(i);
              return (
                <div className="chips">
                  {list.map((a) => (
                    <span key={`${a.kind}:${a.id}`} className="chip">
                      {nameOf(a)}
                      <Button
                        size="small"
                        appearance="transparent"
                        icon={<DismissRegular />}
                        aria-label={`Remove ${nameOf(a)} from ${i.name}`}
                        onClick={() => assign.mutate({ item: i, list: list.filter((x) => x !== a) })}
                      />
                    </span>
                  ))}
                  <Button size="small" aria-label={`Assign ${i.name}`} onClick={() => setPicking(i)}>
                    Assign
                  </Button>
                </div>
              );
            },
          },
        ]}
      />
      {picking && (
        <Picker
          item={picking}
          current={assignmentsOf(picking)}
          targets={targets}
          onAdd={(a) => assign.mutate({ item: picking, list: [...assignmentsOf(picking), a] })}
          onClose={() => setPicking(null)}
        />
      )}
    </Page>
  );
}
