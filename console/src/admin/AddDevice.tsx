import {
  Button, DrawerBody, DrawerFooter, DrawerHeader, DrawerHeaderTitle, Field, Input, OverlayDrawer, Spinner,
} from "@fluentui/react-components";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ErrorBar } from "./Page";

const MQTT_GUIDE = "https://github.com/justwork500/cave/blob/main/docs/integrations/mqtt.md";

interface Found {
  mac: string;
  host: string;
  model: string;
  added: boolean;
  name: string | null;
}

interface Scan {
  signed_in: boolean;
  login_ok: boolean | null;
  devices: Found[];
}

function SignIn({ refused, onDone }: { refused: boolean; onDone: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => api.put("/kasa/login", { username: username.trim(), password }),
    onSuccess: () => {
      setPassword("");
      onDone();
    },
  });
  return (
    <form className="stack" onSubmit={(e) => {
      e.preventDefault();
      login.mutate();
    }}>
      <p>
        {refused
          ? "Your Kasa devices didn't accept that sign-in. Check the email and password you use in the Kasa app."
          : "Kasa devices only take commands from the TP-Link account they're set up with. Use the sign-in from your Kasa app."}
      </p>
      <Field label="TP-Link email">
        <Input type="email" autoComplete="off" value={username} onChange={(_, d) => setUsername(d.value)} />
      </Field>
      <Field label="TP-Link password">
        <Input type="password" autoComplete="off" value={password} onChange={(_, d) => setPassword(d.value)} />
      </Field>
      <p className="muted">CAVE keeps only a hash of this, never the password, and uses it only on your network.</p>
      <ErrorBar error={login.error} />
      <div>
        <Button appearance="primary" type="submit" disabled={!username.trim() || !password || login.isPending}>
          Sign in
        </Button>
      </div>
    </form>
  );
}

/** Add a device: scans the LAN for Kasa plugs and switches, and links to the MQTT guide. */
export function AddDevice({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const scan = useMutation({ mutationFn: () => api.post<Scan>("/kasa/scan") });
  const { mutate: rescan } = scan;
  useEffect(() => rescan(), [rescan]);
  const changed = () => {
    void client.invalidateQueries({ queryKey: ["states"] });
    rescan();
  };
  const add = useMutation({ mutationFn: (mac: string) => api.post("/kasa/devices", { mac }), onSuccess: changed });
  const remove = useMutation({ mutationFn: (mac: string) => api.del(`/kasa/devices/${mac}`), onSuccess: changed });
  const result = scan.data;
  const ready = result?.signed_in && result.login_ok !== false;

  return (
    <OverlayDrawer position="end" size="medium" open onOpenChange={(_, d) => !d.open && onClose()}>
      <DrawerHeader>
        <DrawerHeaderTitle>Add device</DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody className="stack">
        <ErrorBar error={scan.error ?? add.error ?? remove.error} />
        {scan.isPending && <Spinner label="Looking for Kasa devices on your network" />}
        {result && !ready && <SignIn refused={result.login_ok === false} onDone={rescan} />}
        {result && result.devices.length === 0 && (
          <p>No Kasa devices found. Check they're switched on and on the same network as CAVE, then scan again.</p>
        )}
        {result && result.devices.length > 0 && (
          <ul className="found">
            {result.devices.map((d) => {
              const label = d.name ?? d.model;
              return (
                <li key={d.mac}>
                  <span>
                    <b>{label}</b>
                    <span className="muted">{d.name ? `${d.model}, ${d.host}` : d.host}</span>
                  </span>
                  {d.added ? (
                    <Button aria-label={`Remove ${label}`} disabled={remove.isPending}
                            onClick={() => remove.mutate(d.mac)}>
                      Remove
                    </Button>
                  ) : (
                    <Button appearance="primary" aria-label={`Add ${label}`} disabled={!ready || add.isPending}
                            onClick={() => add.mutate(d.mac)}>
                      Add
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        <p className="muted">
          Zigbee2MQTT, Tasmota, Shelly and ESPHome devices don't need adding: they appear here once they reach
          CAVE's MQTT broker. <a href={MQTT_GUIDE}>How MQTT devices connect</a>
        </p>
      </DrawerBody>
      <DrawerFooter>
        <Button disabled={scan.isPending} onClick={() => rescan()}>Scan again</Button>
        <Button onClick={onClose}>Done</Button>
      </DrawerFooter>
    </OverlayDrawer>
  );
}
