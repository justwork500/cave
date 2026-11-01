import { describe, expect, it, vi } from "vitest";
import { LiveFeed, backoff } from "./ws";

class FakeSocket {
  static last: FakeSocket;
  sent: string[] = [];
  onopen?: () => void;
  onmessage?: (e: { data: string }) => void;
  onclose?: (e: { code: number }) => void;
  constructor(public url: string) {
    FakeSocket.last = this;
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {}
}

describe("live feed", () => {
  it("backs off 1, 2, 4 … up to 30 seconds", () => {
    expect([0, 1, 2, 3, 4, 5, 6].map(backoff)).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000]);
  });

  it("subscribes on open and delivers state and notifications", () => {
    const feed = new LiveFeed("wss://cave/api/v1/ws", FakeSocket as never, vi.fn());
    const states = vi.fn();
    const notes = vi.fn();
    feed.onState("light.kitchen", states);
    feed.onNotification(notes);
    feed.start();
    FakeSocket.last.onopen?.();
    expect(JSON.parse(FakeSocket.last.sent[0]!)).toMatchObject({ type: "subscribe", events: ["state_changed"] });
    FakeSocket.last.onmessage?.({ data: JSON.stringify({ type: "event", event: { entity_id: "light.kitchen", new: "on" } }) });
    FakeSocket.last.onmessage?.({ data: JSON.stringify({ type: "notification", id: 3, message: "hi" }) });
    expect(states).toHaveBeenCalledWith(expect.objectContaining({ new: "on" }));
    expect(notes).toHaveBeenCalledWith(expect.objectContaining({ message: "hi" }));
  });

  it("reconnects after a drop and resubscribes", () => {
    vi.useFakeTimers();
    const resync = vi.fn();
    const feed = new LiveFeed("wss://x", FakeSocket as never, resync);
    feed.start();
    const first = FakeSocket.last;
    first.onclose?.({ code: 1006 });
    vi.advanceTimersByTime(1000);
    expect(FakeSocket.last).not.toBe(first);
    FakeSocket.last.onopen?.();
    expect(FakeSocket.last.sent.length).toBe(1);
    expect(resync).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("sends you to sign in when the server says 4401", () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { pathname: "/", search: "", assign });
    const feed = new LiveFeed("wss://x", FakeSocket as never, vi.fn());
    feed.start();
    FakeSocket.last.onclose?.({ code: 4401 });
    expect(assign).toHaveBeenCalledWith("/login?next=%2F");
    vi.unstubAllGlobals();
  });

  it("sends a kiosk screen to its key sign-in on 4401", () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { pathname: "/", search: "", assign });
    localStorage.setItem("cave-screen-id", "scr1");
    new LiveFeed("wss://x", FakeSocket as never, vi.fn()).start();
    FakeSocket.last.onclose?.({ code: 4401 });
    expect(assign).toHaveBeenCalledWith("/enroll");
    localStorage.removeItem("cave-screen-id");
    vi.unstubAllGlobals();
  });
});
