import { Button, Popover, PopoverSurface, PopoverTrigger, CounterBadge } from "@fluentui/react-components";
import { AlertRegular } from "@fluentui/react-icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Notification } from "../../api/types";
import type { NotificationEvent } from "../../api/ws";
import { useLive } from "../live";

/** The notification bell: unread count, live updates over the websocket, and mark-as-read. */
export function Bell() {
  const live = useLive();
  const client = useQueryClient();
  const list = useQuery({ queryKey: ["notifications"], queryFn: () => api.get<Notification[]>("/notifications") });
  const [arrived, setArrived] = useState<NotificationEvent[]>([]);
  useEffect(() => live?.onNotification((n) => setArrived((a) => [n, ...a.filter((x) => x.id !== n.id)])), [live]);

  const known = new Set(arrived.map((n) => n.id));
  const unread = [
    ...arrived,
    ...(list.data ?? []).filter((n) => !n.read_at && !known.has(n.id)),
  ];
  const read = (list.data ?? []).filter((n) => n.read_at && !known.has(n.id));
  const markRead = useMutation({
    mutationFn: (ids: number[]) => api.post("/notifications/read", { ids }),
    onSuccess: () => {
      setArrived([]);
      void client.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  const label = unread.length ? `Notifications, ${unread.length} unread` : "Notifications";
  return (
    <Popover
      positioning="below-end"
      onOpenChange={(_, d) => {
        if (!d.open && unread.length) markRead.mutate(unread.map((n) => n.id));
      }}
    >
      <PopoverTrigger disableButtonEnhancement>
        <Button
          className="bar-button"
          appearance="transparent"
          aria-label={label}
          icon={
            <span className="bell">
              <AlertRegular />
              {unread.length > 0 && <CounterBadge count={unread.length} size="small" color="danger" aria-hidden />}
            </span>
          }
        />
      </PopoverTrigger>
      <PopoverSurface aria-label="Notifications" className="notes">
        {unread.length + read.length === 0 && <p>Nothing new.</p>}
        <ul>
          {[...unread, ...read].slice(0, 20).map((n, i) => (
            <li key={n.id} className={i < unread.length ? "unread" : undefined}>
              {n.title && <strong>{n.title}</strong>}
              <span>{n.message}</span>
            </li>
          ))}
        </ul>
      </PopoverSurface>
    </Popover>
  );
}
