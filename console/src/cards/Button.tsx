import {
  Button, Dialog, DialogActions, DialogBody, DialogContent, DialogSurface, DialogTitle,
} from "@fluentui/react-components";
import { LockClosedRegular, PlayRegular } from "@fluentui/react-icons";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, message } from "../api/client";
import type { ButtonCard } from "../api/types";
import { CardIcon } from "./look";

function run(card: ButtonCard) {
  if (card.action) {
    const dot = card.action.indexOf("."); // a script's file name has dots of its own
    const kind = card.action.slice(0, dot);
    const id = encodeURIComponent(card.action.slice(dot + 1));
    return api.post(`/${{ automation: "automations", sequence: "sequences" }[kind] ?? "scripts"}/${id}/run`);
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
        icon={card.icon ? <CardIcon name={card.icon} /> : <PlayRegular />}
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
