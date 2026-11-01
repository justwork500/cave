import {
  Button, Checkbox, Dialog, DialogActions, DialogBody, DialogContent, DialogSurface, DialogTitle, Field, Input,
} from "@fluentui/react-components";
import { AddRegular } from "@fluentui/react-icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { api } from "../api/client";
import { DataTable, ErrorBar, Page, when } from "./Page";

export interface Screen {
  id: string;
  name: string;
  status: "pending" | "approved" | "revoked";
  fingerprint: string | null;
  created_at: string;
}

interface Created {
  screen: Screen;
  enroll_url: string;
  expires_at: string;
}

function Countdown({ until }: { until: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const left = Math.max(0, Math.floor((new Date(until).getTime() - now) / 1000));
  if (left === 0) return <p role="status">This link has expired. Add the screen again for a new one.</p>;
  return (
    <p>
      Expires in {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}
    </p>
  );
}

function AddScreen({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [qr, setQr] = useState<string>();
  const create = useMutation({
    mutationFn: () => api.post<Created>("/screens", { name: name.trim() }),
    onSuccess: (r) => {
      void client.invalidateQueries({ queryKey: ["screens"] });
      QRCode.toDataURL(r.enroll_url, { margin: 1, width: 220 }).then(setQr, () => setQr(undefined));
    },
  });
  const made = create.data;
  return (
    <Dialog open onOpenChange={(_, d) => !d.open && onClose()}>
      <DialogSurface>
        <DialogBody>
          <DialogTitle>Add a screen</DialogTitle>
          <DialogContent className="stack">
            {made ? (
              <>
                <p>Open this link on the tablet, or scan the code with its camera.</p>
                {qr && <img className="qr" src={qr} width={220} height={220} alt="QR code of the enrollment link" />}
                <code className="secret">{made.enroll_url}</code>
                <Countdown until={made.expires_at} />
                <p>Once the tablet shows its fingerprint, approve it here.</p>
              </>
            ) : (
              <form
                id="add-screen"
                onSubmit={(e) => {
                  e.preventDefault();
                  create.mutate();
                }}
              >
                <Field label="Screen name" hint="Where it lives, like Garage tablet.">
                  <Input value={name} onChange={(_, d) => setName(d.value)} />
                </Field>
              </form>
            )}
            <ErrorBar error={create.error} />
          </DialogContent>
          <DialogActions>
            {made ? (
              <Button appearance="primary" onClick={onClose}>
                Done
              </Button>
            ) : (
              <>
                <Button onClick={onClose}>Cancel</Button>
                <Button appearance="primary" type="submit" form="add-screen" disabled={!name.trim() || create.isPending}>
                  Create enrollment link
                </Button>
              </>
            )}
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}

function Confirm({ screen, verb, onClose }: { screen: Screen; verb: "approve" | "revoke"; onClose: () => void }) {
  const client = useQueryClient();
  const [match, setMatch] = useState(false);
  const act = useMutation({
    // spelled out, so the console/server contract test can check both paths
    mutationFn: () => api.post(verb === "approve" ? `/screens/${encodeURIComponent(screen.id)}/approve`
                                                  : `/screens/${encodeURIComponent(screen.id)}/revoke`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["screens"] });
      onClose();
    },
  });
  const approving = verb === "approve";
  return (
    <Dialog open onOpenChange={(_, d) => !d.open && onClose()}>
      <DialogSurface>
        <DialogBody>
          <DialogTitle>
            {approving ? "Approve" : "Revoke"} {screen.name}?
          </DialogTitle>
          <DialogContent className="stack">
            {approving ? (
              <>
                <p>Check this fingerprint is the one the tablet shows. If it isn't, someone else may have the link.</p>
                <code className="fingerprint">{screen.fingerprint}</code>
                <Checkbox label="They match" checked={match} onChange={(_, d) => setMatch(Boolean(d.checked))} />
              </>
            ) : (
              <p>The screen is signed out at once and has to be added again to come back.</p>
            )}
            <ErrorBar error={act.error} />
          </DialogContent>
          <DialogActions>
            <Button onClick={onClose}>Cancel</Button>
            <Button
              appearance="primary"
              disabled={(approving && !match) || act.isPending}
              onClick={() => act.mutate()}
            >
              {approving ? "Approve" : "Revoke"}
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}

const STATUS = { pending: "Waiting for approval", approved: "Approved", revoked: "Revoked" };

export function Screens() {
  const [params] = useSearchParams();
  const screens = useQuery({ queryKey: ["screens"], queryFn: () => api.get<Screen[]>("/screens") });
  const [adding, setAdding] = useState(false);
  const [acting, setActing] = useState<{ screen: Screen; verb: "approve" | "revoke" } | null>(null);

  return (
    <Page
      title="Wall tablets"
      commands={
        <Button appearance="primary" icon={<AddRegular />} onClick={() => setAdding(true)}>
          Add screen
        </Button>
      }
    >
      <ErrorBar error={screens.error} />
      <DataTable<Screen>
        label="Screens"
        rows={screens.data ?? []}
        rowKey={(s) => s.id}
        search={(s) => s.name}
        initialFilter={params.get("filter")}
        filters={[
          { id: "pending", label: "Waiting for approval", test: (s) => s.status === "pending" },
          { id: "approved", label: "Approved", test: (s) => s.status === "approved" },
        ]}
        columns={[
          { label: "Name", sort: (s) => s.name.toLowerCase(), render: (s) => s.name },
          { label: "Status", sort: (s) => s.status, render: (s) => STATUS[s.status] },
          { label: "Fingerprint", render: (s) => s.fingerprint && <code>{s.fingerprint}</code> },
          { label: "Added", sort: (s) => s.created_at, render: (s) => when(s.created_at) },
          {
            label: "Actions",
            render: (s) => (
              <div className="row start">
                {s.status === "pending" && s.fingerprint && (
                  <Button size="small" aria-label={`Approve ${s.name}`}
                          onClick={() => setActing({ screen: s, verb: "approve" })}>
                    Approve
                  </Button>
                )}
                {s.status !== "revoked" && (
                  <Button size="small" aria-label={`Revoke ${s.name}`}
                          onClick={() => setActing({ screen: s, verb: "revoke" })}>
                    Revoke
                  </Button>
                )}
              </div>
            ),
          },
        ]}
      />
      {adding && <AddScreen onClose={() => setAdding(false)} />}
      {acting && <Confirm {...acting} onClose={() => setActing(null)} />}
    </Page>
  );
}
