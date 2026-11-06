import {
  Button, DrawerBody, DrawerFooter, DrawerHeader, DrawerHeaderTitle, Field, Input, OverlayDrawer, Select,
} from "@fluentui/react-components";
import { DeleteRegular, EditRegular, LockClosedRegular } from "@fluentui/react-icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { api } from "../api/client";
import type { EntityView, FullEntity } from "../api/types";
import { isFull, stateText } from "../cards/entity";
import { AddDevice } from "./AddDevice";
import { DataTable, ErrorBar, Page } from "./Page";

interface Area {
  id: string;
  name: string;
  floor: string | null;
}

function EditPanel({ entity, areas, onClose }: { entity: FullEntity; areas: Area[]; onClose: () => void }) {
  const client = useQueryClient();
  const [name, setName] = useState(entity.name);
  const [area, setArea] = useState(entity.area_id ?? "");
  const save = useMutation({
    mutationFn: () => api.patch(`/entities/${encodeURIComponent(entity.entity_id)}`, { name, area_id: area || null }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["states"] });
      onClose();
    },
  });
  return (
    <OverlayDrawer position="end" open onOpenChange={(_, d) => !d.open && onClose()}>
      <DrawerHeader>
        <DrawerHeaderTitle>{entity.name}</DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody className="stack">
        <p className="muted">{entity.entity_id}</p>
        <Field label="Name">
          <Input value={name} onChange={(_, d) => setName(d.value)} />
        </Field>
        <Field label="Room">
          <Select value={area} onChange={(_, d) => setArea(d.value)}>
            <option value="">No room</option>
            {areas.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
        </Field>
        <ErrorBar error={save.error} />
      </DrawerBody>
      <DrawerFooter>
        <Button appearance="primary" disabled={!name.trim() || save.isPending} onClick={() => save.mutate()}>
          Save
        </Button>
        <Button onClick={onClose}>Cancel</Button>
      </DrawerFooter>
    </OverlayDrawer>
  );
}

function Rooms({ areas }: { areas: Area[] }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const done = () => void client.invalidateQueries({ queryKey: ["areas"] });
  const add = useMutation({ mutationFn: () => api.post("/areas", { name: name.trim() }), onSuccess: () => {
    setName("");
    done();
  } });
  const remove = useMutation({ mutationFn: (id: string) => api.del(`/areas/${encodeURIComponent(id)}`),
                               onSuccess: done });
  return (
    <section className="stack">
      <h2>Rooms</h2>
      <ul className="chips">
        {areas.map((a) => (
          <li key={a.id} className="chip">
            {a.name}
            <Button
              size="small"
              appearance="transparent"
              icon={<DeleteRegular />}
              aria-label={`Delete room ${a.name}`}
              onClick={() => remove.mutate(a.id)}
            />
          </li>
        ))}
      </ul>
      <form
        className="row start"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate();
        }}
      >
        <Input aria-label="New room name" placeholder="New room" value={name} onChange={(_, d) => setName(d.value)} />
        <Button type="submit" disabled={!name.trim() || add.isPending}>
          Add room
        </Button>
      </form>
      <ErrorBar error={add.error ?? remove.error} />
    </section>
  );
}

export function Devices() {
  const [params] = useSearchParams();
  const states = useQuery({ queryKey: ["states"], queryFn: () => api.get<EntityView[]>("/states") });
  const areas = useQuery({ queryKey: ["areas"], queryFn: () => api.get<Area[]>("/areas") });
  const [editing, setEditing] = useState<FullEntity | null>(null);
  const [adding, setAdding] = useState(false);
  const roomName = (id: string | null) => areas.data?.find((a) => a.id === id)?.name ?? "";

  return (
    <Page
      title="Devices"
      commands={<Button appearance="primary" onClick={() => setAdding(true)}>Add device</Button>}
    >
      <ErrorBar error={states.error ?? areas.error} />
      <DataTable<EntityView>
        label="Devices"
        rows={states.data ?? []}
        rowKey={(e) => e.entity_id}
        search={(e) => `${e.name} ${e.entity_id} ${roomName(e.area_id)}`}
        initialFilter={params.get("filter")}
        filters={[
          { id: "unavailable", label: "Not responding", test: (e) => isFull(e) && e.state === "unavailable" },
          { id: "restricted", label: "Restricted", test: (e) => !isFull(e) },
        ]}
        rowClass={(e) => (isFull(e) ? undefined : "locked")}
        columns={[
          { label: "Name", sort: (e) => e.name.toLowerCase(), render: (e) => e.name },
          { label: "Room", sort: (e) => roomName(e.area_id), render: (e) => roomName(e.area_id) },
          {
            label: "State",
            render: (e) =>
              isFull(e) ? (
                stateText(e.state, e.attributes)
              ) : (
                <span className="locked-text">
                  <LockClosedRegular aria-hidden /> Restricted
                </span>
              ),
          },
          {
            label: "Actions",
            render: (e) =>
              isFull(e) && (
                <Button
                  size="small"
                  icon={<EditRegular />}
                  aria-label={`Edit ${e.name}`}
                  onClick={() => setEditing(e)}
                />
              ),
          },
        ]}
      />
      <Rooms areas={areas.data ?? []} />
      {editing && <EditPanel entity={editing} areas={areas.data ?? []} onClose={() => setEditing(null)} />}
      {adding && <AddDevice onClose={() => setAdding(false)} />}
    </Page>
  );
}
