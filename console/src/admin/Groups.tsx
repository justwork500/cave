import {
  Button, Checkbox, Dialog, DialogActions, DialogBody, DialogContent, DialogSurface, DialogTitle, Input,
} from "@fluentui/react-components";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { DataTable, ErrorBar, Page } from "./Page";
import type { User } from "./Users";

export interface Group {
  id: string;
  name: string;
  members: string[];
}

function Members({ group, users, onClose }: { group: Group; users: User[]; onClose: () => void }) {
  const client = useQueryClient();
  const [members, setMembers] = useState(new Set(group.members));
  const save = useMutation({
    mutationFn: () => api.put(`/groups/${encodeURIComponent(group.id)}/members`, [...members]),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["groups"] });
      onClose();
    },
  });
  return (
    <Dialog open onOpenChange={(_, d) => !d.open && onClose()}>
      <DialogSurface>
        <DialogBody>
          <DialogTitle>Members of {group.name}</DialogTitle>
          <DialogContent className="stack">
            <div className="checklist">
              {users.map((u) => (
                <Checkbox
                  key={u.id}
                  label={u.display_name || u.username}
                  checked={members.has(u.id)}
                  onChange={(_, d) => {
                    const next = new Set(members);
                    if (d.checked) next.add(u.id);
                    else next.delete(u.id);
                    setMembers(next);
                  }}
                />
              ))}
            </div>
            <ErrorBar error={save.error} />
          </DialogContent>
          <DialogActions>
            <Button onClick={onClose}>Cancel</Button>
            <Button appearance="primary" disabled={save.isPending} onClick={() => save.mutate()}>
              Save members
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}

export function Groups() {
  const client = useQueryClient();
  const groups = useQuery({ queryKey: ["groups"], queryFn: () => api.get<Group[]>("/groups") });
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>("/users") });
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<Group | null>(null);
  const done = () => void client.invalidateQueries({ queryKey: ["groups"] });
  const create = useMutation({ mutationFn: () => api.post("/groups", { name: name.trim() }), onSuccess: () => {
    setName("");
    done();
  } });
  const remove = useMutation({ mutationFn: (id: string) => api.del(`/groups/${encodeURIComponent(id)}`),
                               onSuccess: done });
  const userName = (id: string) => {
    const u = users.data?.find((x) => x.id === id);
    return u ? u.display_name || u.username : id;
  };

  return (
    <Page
      title="Groups"
      commands={
        <form
          className="row start"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <Input aria-label="New group name" placeholder="New group" value={name} onChange={(_, d) => setName(d.value)} />
          <Button appearance="primary" type="submit" disabled={!name.trim() || create.isPending}>
            Create group
          </Button>
        </form>
      }
    >
      <ErrorBar error={groups.error ?? create.error ?? remove.error} />
      <DataTable<Group>
        label="Groups"
        rows={groups.data ?? []}
        rowKey={(g) => g.id}
        search={(g) => g.name}
        columns={[
          { label: "Name", sort: (g) => g.name.toLowerCase(), render: (g) => g.name },
          { label: "Members", sort: (g) => g.members.length, render: (g) => g.members.map(userName).join(", ") },
          {
            label: "Actions",
            render: (g) => (
              <div className="row start">
                <Button size="small" onClick={() => setEditing(g)} aria-label={`Edit members of ${g.name}`}>
                  Members
                </Button>
                <Button size="small" onClick={() => remove.mutate(g.id)} aria-label={`Delete ${g.name}`}>
                  Delete
                </Button>
              </div>
            ),
          },
        ]}
      />
      {editing && <Members group={editing} users={users.data ?? []} onClose={() => setEditing(null)} />}
    </Page>
  );
}
