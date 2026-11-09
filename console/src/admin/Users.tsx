import {
  Button, Dialog, DialogActions, DialogBody, DialogContent, DialogSurface, DialogTitle, DialogTrigger, Field, Input,
  Select, Switch,
} from "@fluentui/react-components";
import { AddRegular } from "@fluentui/react-icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import type { Role } from "../api/types";
import { DataTable, ErrorBar, Page } from "./Page";

export interface User {
  id: string;
  username: string;
  display_name: string;
  role: Role;
  enabled: boolean;
  expires_at: string | null;
}

export const ROLES: { id: Role; name: string }[] = [
  { id: "admin", name: "Admin" },
  { id: "operator", name: "Operator" },
  { id: "household", name: "Household" },
  { id: "guest", name: "Guest" },
  { id: "auditor", name: "Auditor" },
];

const MIN_PASSWORD = 12;

function NewUser() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ username: "", display_name: "", password: "", role: "household" });
  const create = useMutation({
    mutationFn: () => api.post("/users", form),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["users"] });
      setOpen(false);
      setForm({ username: "", display_name: "", password: "", role: "household" });
    },
  });
  const set = (k: keyof typeof form) => (_: unknown, d: { value: string }) => setForm({ ...form, [k]: d.value });
  return (
    <Dialog open={open} onOpenChange={(_, d) => setOpen(d.open)}>
      <DialogTrigger disableButtonEnhancement>
        <Button appearance="primary" icon={<AddRegular />}>
          New user
        </Button>
      </DialogTrigger>
      <DialogSurface>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <DialogBody>
            <DialogTitle>New user</DialogTitle>
            <DialogContent className="stack">
              <Field label="Name">
                <Input value={form.display_name} onChange={set("display_name")} />
              </Field>
              <Field label="Username">
                <Input value={form.username} onChange={set("username")} autoComplete="off" spellCheck={false} />
              </Field>
              <Field label="Password" hint={`At least ${MIN_PASSWORD} characters. They can change it later.`}>
                <Input type="password" value={form.password} onChange={set("password")} autoComplete="new-password" />
              </Field>
              <Field label="Role">
                <Select value={form.role} onChange={set("role")}>
                  {ROLES.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <ErrorBar error={create.error} />
            </DialogContent>
            <DialogActions>
              <DialogTrigger disableButtonEnhancement>
                <Button>Cancel</Button>
              </DialogTrigger>
              <Button
                appearance="primary"
                type="submit"
                disabled={!form.username || form.password.length < MIN_PASSWORD || create.isPending}
              >
                Create user
              </Button>
            </DialogActions>
          </DialogBody>
        </form>
      </DialogSurface>
    </Dialog>
  );
}

/** The People page: add people, change their role, and turn accounts on or off. */
export function Users() {
  const client = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>("/users") });
  const patch = useMutation({
    mutationFn: ({ id, ...body }: { id: string } & Partial<User>) => api.patch(`/users/${encodeURIComponent(id)}`, body),
    onSettled: () => void client.invalidateQueries({ queryKey: ["users"] }),
  });
  const name = (u: User) => u.display_name || u.username;

  return (
    <Page title="People" commands={<NewUser />}>
      <ErrorBar error={users.error ?? patch.error} />
      <DataTable<User>
        label="Users"
        rows={users.data ?? []}
        rowKey={(u) => u.id}
        search={(u) => `${u.username} ${u.display_name} ${u.role}`}
        filters={[
          { id: "disabled", label: "Disabled", test: (u) => !u.enabled },
          { id: "admins", label: "Admins", test: (u) => u.role === "admin" },
        ]}
        columns={[
          { label: "Name", sort: (u) => name(u).toLowerCase(), render: name },
          { label: "Username", sort: (u) => u.username, render: (u) => u.username },
          {
            label: "Role",
            sort: (u) => u.role,
            render: (u) => (
              <Select
                aria-label={`Role for ${name(u)}`}
                value={u.role}
                onChange={(_, d) => patch.mutate({ id: u.id, role: d.value as Role })}
              >
                {ROLES.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </Select>
            ),
          },
          {
            label: "Enabled",
            render: (u) => (
              <Switch
                aria-label={`${name(u)} enabled`}
                checked={u.enabled}
                onChange={(_, d) => patch.mutate({ id: u.id, enabled: d.checked })}
              />
            ),
          },
          {
            label: "Expires",
            render: (u) => (
              <Input
                type="date"
                aria-label={`Account expiry for ${name(u)}`}
                value={u.expires_at?.slice(0, 10) ?? ""}
                onChange={(_, d) =>
                  d.value && patch.mutate({ id: u.id, expires_at: new Date(`${d.value}T23:59:59`).toISOString() })
                }
              />
            ),
          },
        ]}
      />
    </Page>
  );
}
