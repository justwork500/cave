import {
  Button, Dialog, DialogActions, DialogBody, DialogContent, DialogSurface, DialogTitle, Field, Input,
} from "@fluentui/react-components";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, message } from "../api/client";
import type { IntegrationInfo } from "../api/types";
import { ErrorBar } from "./Page";

interface Probe {
  device_id: string;
  host: string;
  model: string;
  name: string;
  added: boolean;
}

const SECRET_LABEL = { password: "Password", key: "Encryption key", pin: "PIN" } as const;

/** Add and remove devices for one integration: address, check, pairing step, Add. */
export function AddIntegration({ integration, onDone }: { integration: IntegrationInfo; onDone: () => void }) {
  const client = useQueryClient();
  const base = `/integrations/${integration.domain}`;
  const [host, setHost] = useState("");
  const [secret, setSecret] = useState("");
  const [removing, setRemoving] = useState<IntegrationInfo["devices"][number] | null>(null);
  const kind = integration.pairing;
  const label = kind === "password" || kind === "key" || kind === "pin" ? SECRET_LABEL[kind] : null;
  const changed = () => {
    void client.invalidateQueries({ queryKey: ["integrations"] });
    void client.invalidateQueries({ queryKey: ["states"] });
  };

  const probe = useMutation({ mutationFn: () => api.post<Probe>(`${base}/probe`, { host: host.trim() }) });
  const add = useMutation({
    mutationFn: () => api.post(`${base}/devices`, { host: host.trim(), ...(label ? { secret } : {}) }),
    onSuccess: () => {
      setSecret("");
      setHost("");
      changed();
      onDone();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.del(`${base}/devices/${id}`),
    onSuccess: () => {
      setRemoving(null);
      changed();
    },
  });
  const found = probe.data;

  return (
    <div className="stack">
      {integration.devices.length > 0 && (
        <ul className="found">
          {integration.devices.map((d) => (
            <li key={d.device_id}>
              <span>
                <b>{d.name}</b>
                <span className="muted">{`${d.model}, ${d.host}`}</span>
              </span>
              <Button aria-label={`Remove ${d.name}`} onClick={() => setRemoving(d)}>Remove</Button>
            </li>
          ))}
        </ul>
      )}
      <form className="stack" onSubmit={(e) => {
        e.preventDefault();
        probe.mutate();
      }}>
        <Field label="Device address" validationState={probe.error ? "error" : "none"}
               validationMessage={probe.error ? message(probe.error) : undefined}>
          <Input inputMode="decimal" spellCheck={false} placeholder="192.168.1.40…" value={host}
                 onChange={(_, d) => {
                   setHost(d.value);
                   probe.reset();
                 }} />
        </Field>
        <div>
          <Button type="submit" disabled={!host.trim() || probe.isPending}>Check</Button>
        </div>
      </form>
      {found && (
        <form className="stack" onSubmit={(e) => {
          e.preventDefault();
          add.mutate();
        }}>
          <p>
            <b>{found.model}</b> <span className="muted">{found.name}</span>
          </p>
          {found.added && <p>Already added. Adding it again updates its address.</p>}
          {label && (
            <Field label={label} hint={integration.pairing_hint} validationState={add.error ? "error" : "none"}
                   validationMessage={add.error ? message(add.error) : undefined}>
              <Input type="password" autoComplete="off" value={secret} onChange={(_, d) => setSecret(d.value)} />
            </Field>
          )}
          {kind === "button" && <p>{integration.pairing_hint}</p>}
          {!label && <ErrorBar error={add.error} />}
          <div>
            <Button appearance="primary" type="submit" disabled={add.isPending}>
              Add
            </Button>
          </div>
        </form>
      )}
      <Dialog open={removing !== null} onOpenChange={(_, d) => {
        if (!d.open) {
          setRemoving(null);
          remove.reset();
        }
      }}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>{`Remove ${removing?.name ?? ""}?`}</DialogTitle>
            <DialogContent className="stack">
              <p>CAVE stops controlling this device and forgets its saved key. You can add it again later.</p>
              <ErrorBar error={remove.error} />
            </DialogContent>
            <DialogActions>
              <Button onClick={() => {
                setRemoving(null);
                remove.reset();
              }}>Cancel</Button>
              <Button appearance="primary" disabled={remove.isPending}
                      onClick={() => removing && remove.mutate(removing.device_id)}>
                Remove
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </div>
  );
}
