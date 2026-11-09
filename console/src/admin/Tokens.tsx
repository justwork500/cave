import {
  Button, Dialog, DialogActions, DialogBody, DialogContent, DialogSurface, DialogTitle, Field, Input,
} from "@fluentui/react-components";
import { AddRegular, CopyRegular } from "@fluentui/react-icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { DataTable, ErrorBar, Page, when } from "./Page";

interface Token {
  id: string;
  user_id: string;
  name: string;
  created_at: string;
}

function NewToken({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [copied, setCopied] = useState(false);
  const create = useMutation({
    mutationFn: () => api.post<{ token: string }>("/tokens", { name: name.trim() }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["tokens"] }),
  });
  const token = create.data?.token;
  return (
    <Dialog open onOpenChange={(_, d) => !d.open && onClose()}>
      <DialogSurface>
        <DialogBody>
          <DialogTitle>New API token</DialogTitle>
          <DialogContent className="stack">
            {token ? (
              <>
                <p>Copy it now. CAVE keeps only a hash, so it can't show this token again.</p>
                <code className="secret">{token}</code>
                <Button
                  icon={<CopyRegular />}
                  onClick={() => void navigator.clipboard.writeText(token).then(() => setCopied(true))}
                >
                  {copied ? "Copied" : "Copy token"}
                </Button>
              </>
            ) : (
              <form
                id="new-token"
                onSubmit={(e) => {
                  e.preventDefault();
                  create.mutate();
                }}
              >
                <Field label="Token name" hint="What uses it, like Node-RED.">
                  <Input value={name} onChange={(_, d) => setName(d.value)} />
                </Field>
              </form>
            )}
            <ErrorBar error={create.error} />
          </DialogContent>
          <DialogActions>
            {token ? (
              <Button appearance="primary" onClick={onClose}>
                Done
              </Button>
            ) : (
              <>
                <Button onClick={onClose}>Cancel</Button>
                <Button appearance="primary" type="submit" form="new-token" disabled={!name.trim() || create.isPending}>
                  Create token
                </Button>
              </>
            )}
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}

/** The API tokens page: create a token (shown once) and revoke tokens. */
export function Tokens() {
  const client = useQueryClient();
  const tokens = useQuery({ queryKey: ["tokens"], queryFn: () => api.get<Token[]>("/tokens") });
  const [adding, setAdding] = useState(false);
  const revoke = useMutation({
    mutationFn: (id: string) => api.del(`/tokens/${encodeURIComponent(id)}`),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["tokens"] }),
  });
  return (
    <Page
      title="API tokens"
      commands={
        <Button appearance="primary" icon={<AddRegular />} onClick={() => setAdding(true)}>
          New token
        </Button>
      }
    >
      <ErrorBar error={tokens.error ?? revoke.error} />
      <DataTable<Token>
        label="API tokens"
        rows={tokens.data ?? []}
        rowKey={(t) => t.id}
        search={(t) => t.name}
        columns={[
          { label: "Name", sort: (t) => t.name.toLowerCase(), render: (t) => t.name },
          { label: "Created", sort: (t) => t.created_at, render: (t) => when(t.created_at) },
          {
            label: "Actions",
            render: (t) => (
              <Button size="small" aria-label={`Revoke ${t.name}`} onClick={() => revoke.mutate(t.id)}>
                Revoke
              </Button>
            ),
          },
        ]}
      />
      {adding && <NewToken onClose={() => setAdding(false)} />}
    </Page>
  );
}
