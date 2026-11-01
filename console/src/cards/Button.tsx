import {
  Button, Dialog, DialogActions, DialogBody, DialogContent, DialogSurface, DialogTitle,
} from "@fluentui/react-components";
import { LockClosedRegular, PlayRegular } from "@fluentui/react-icons";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, message } from "../api/client";
import type { ButtonCard } from "../api/types";

function run(card: ButtonCard) {
  if (card.action) {
    const [kind, id = ""] = card.action.split(".", 2);
    return api.post(`/${kind === "automation" ? "automations" : "sequences"}/${encodeURIComponent(id)}/run`);
  }
  return api.post(
    `/entities/${encodeURIComponent(card.entity ?? "")}/commands/${encodeURIComponent(card.command ?? "")}`,
  );
}

export function ActionButton({ card }: { card: ButtonCard }) {
  const [asking, setAsking] = useState(false);
  const go = useMutation({ mutationFn: () => run(card) });

  if (!card.allowed) {
    return (
      <div className="action">
        <Button size="large" disabled icon={<LockClosedRegular />}>
          {card.name}
        </Button>
        <span className="action-status">Restricted</span>
      </div>
    );
  }

  return (
    <div className="action">
      <Button
        size="large"
        appearance="primary"
        icon={<PlayRegular />}
        disabled={go.isPending}
        onClick={() => (card.confirm ? setAsking(true) : go.mutate())}
      >
        {card.name}
      </Button>
      <span className="action-status" role="status">
        {go.isSuccess && `${card.name} started.`}
        {go.isError && message(go.error)}
      </span>
      <Dialog open={asking} onOpenChange={(_, d) => setAsking(d.open)}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>Run {card.name}?</DialogTitle>
            <DialogContent>This runs {card.name} now.</DialogContent>
            <DialogActions>
              <Button onClick={() => setAsking(false)}>Cancel</Button>
              <Button
                appearance="primary"
                onClick={() => {
                  setAsking(false);
                  go.mutate();
                }}
              >
                Run
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </div>
  );
}
