/** One live connection per tab: device state changes and notifications, reconnecting on its own. */
import { signInAgain } from "./client";

export interface StateEvent {
  entity_id: string;
  old: string | null;
  new: string;
  attributes: Record<string, unknown>;
}

export interface NotificationEvent {
  id: number;
  title: string | null;
  message: string;
}

type SocketCtor = new (url: string) => {
  send(data: string): void;
  close(): void;
  onopen: (() => void) | null;
  onmessage: ((e: { data: string }) => void) | null;
  onclose: ((e: { code: number }) => void) | null;
};

const UNAUTHORIZED = 4401;
const RESYNC = 4408;

export function backoff(attempt: number): number {
  return Math.min(30, 2 ** attempt) * 1000;
}

export class LiveFeed {
  private socket?: InstanceType<SocketCtor>;
  private attempt = 0;
  private stopped = false;
  private readonly states = new Map<string, Set<(e: StateEvent) => void>>();
  private readonly notes = new Set<(e: NotificationEvent) => void>();

  constructor(
    private readonly url: string,
    private readonly Socket: SocketCtor,
    private readonly resync: () => void,
  ) {}

  onState(entityId: string, cb: (e: StateEvent) => void): () => void {
    const set = this.states.get(entityId) ?? new Set();
    set.add(cb);
    this.states.set(entityId, set);
    return () => set.delete(cb);
  }

  onNotification(cb: (e: NotificationEvent) => void): () => void {
    this.notes.add(cb);
    return () => this.notes.delete(cb);
  }

  start(): void {
    this.stopped = false;
    const socket = new this.Socket(this.url);
    this.socket = socket;
    socket.onopen = () => {
      const reconnected = this.attempt > 0;
      this.attempt = 0;
      socket.send(JSON.stringify({ id: 1, type: "subscribe", events: ["state_changed"] }));
      if (reconnected) this.resync(); // anything missed while away is fetched again
    };
    socket.onmessage = (e) => {
      const msg = JSON.parse(e.data) as { type: string; event?: StateEvent } & NotificationEvent;
      const event = msg.event;
      if (msg.type === "event" && event) this.states.get(event.entity_id)?.forEach((cb) => cb(event));
      if (msg.type === "notification") this.notes.forEach((cb) => cb(msg));
    };
    socket.onclose = (e) => {
      if (this.stopped) return;
      if (e.code === UNAUTHORIZED) {
        signInAgain();
        return;
      }
      const wait = e.code === RESYNC ? 0 : backoff(this.attempt);
      this.attempt += 1;
      setTimeout(() => this.start(), wait);
    };
  }

  stop(): void {
    this.stopped = true;
    this.socket?.close();
  }
}
