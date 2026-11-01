import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { StateEvent } from "../api/ws";
import { LiveContext } from "../app/live";
import { expectAccessible } from "../test/axe";
import { mockApi, renderWith, setNarrow } from "../test/render";
import { Dashboard } from "./Dashboard";

const lamp = { entity_id: "light.porch", name: "Porch light", area_id: "front_yard", capability: "switch",
               state: "off", attributes: {}, last_changed: null };
const temp = { entity_id: "sensor.temp", name: "Temperature", area_id: null, capability: "sensor",
               state: "21.5", attributes: { unit: "°C" }, last_changed: null };
const VIEW = {
  slug: "home", title: "Home", icon: null,
  views: [{ id: "main", title: "Main", sections: [
    { title: "Outside", cards: [
      { type: "tile", w: 3, h: 1, entity: lamp, tap_action: "toggle", locked: false },
      { type: "tile", w: 3, h: 1, entity: { entity_id: "cover.garage", name: "Garage door", area_id: null,
        restricted: true }, tap_action: "toggle", locked: true },
      { type: "gauge", w: 3, h: 2, entity: temp, min: 0, max: 40, severity: { green: 0, yellow: 25, red: 32 },
        locked: false },
      { type: "entities", w: 6, h: 2, entities: [temp] },
      { type: "button", w: 3, h: 1, name: "Good night", action: "sequence.good_night", entity: null, command: null,
        confirm: true, allowed: true },
      { type: "button", w: 3, h: 1, name: "Open gate", action: "automation.gate", entity: null, command: null,
        confirm: null, allowed: false },
      { type: "markdown", w: 12, h: 1, text: "## Welcome\nHave a **good** day." },
    ] },
  ] }],
};

function live() {
  const subs = new Map<string, (e: StateEvent) => void>();
  return {
    feed: { onNotification: () => () => undefined, onState: (id: string, cb: (e: StateEvent) => void) => {
      subs.set(id, cb);
      return () => subs.delete(id);
    } },
    push: (e: StateEvent) => subs.get(e.entity_id)?.(e),
  };
}

function show(routes: Record<string, unknown> = {}) {
  const l = live();
  const calls = mockApi({ "GET /dashboards/default": { slug: "home" }, "GET /dashboards/home/view": VIEW, ...routes });
  const view = renderWith(
    <LiveContext.Provider value={l.feed as never}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/d/:slug" element={<Dashboard />} />
      </Routes>
    </LiveContext.Provider>,
  );
  return { ...view, calls, live: l };
}

describe("the actions dashboard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows every card type in plain words", async () => {
    setNarrow(false);
    const { container } = show();
    expect(await screen.findByRole("heading", { name: "Outside" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Porch light/ })).toHaveTextContent("Off");
    expect(screen.getByRole("button", { name: /Porch light/ })).toHaveTextContent("Front yard");
    expect(screen.getByRole("meter", { name: /Temperature/ })).toHaveTextContent("21.5 °C");
    expect(screen.getByText("Normal")).toBeInTheDocument();  // severity in words, not colour alone
    expect(screen.getByRole("heading", { name: "Welcome" })).toBeInTheDocument();
    expect(screen.getByText("good").tagName).toBe("STRONG");
    await expectAccessible(container);
  });

  it("locks a restricted tile: no button, and it says Restricted", async () => {  // Review Focus 1
    setNarrow(false);
    show();
    await screen.findByRole("heading", { name: "Outside" });
    expect(screen.queryByRole("button", { name: /Garage door/ })).not.toBeInTheDocument();
    const tile = screen.getByText("Garage door").closest(".tile") as HTMLElement;
    expect(within(tile).getByText("Restricted")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open gate/ })).toBeDisabled();
  });

  it("toggles through the command API and follows live state", async () => {
    setNarrow(false);
    const { calls, live } = show({ "POST /entities/light.porch/commands/toggle": [202, { accepted: true }] });
    await userEvent.click(await screen.findByRole("button", { name: /Porch light/ }));
    expect(calls.at(-1)).toMatchObject({ method: "POST", path: "/entities/light.porch/commands/toggle" });
    act(() => live.push({ entity_id: "light.porch", old: "off", new: "on", attributes: {} }));
    expect(screen.getByRole("button", { name: /Porch light/ })).toHaveTextContent("On");
  });

  it("runs a confirm button only after you confirm", async () => {
    setNarrow(false);
    const { calls } = show({ "POST /sequences/good_night/run": { trace_id: 7 } });
    await userEvent.click(await screen.findByRole("button", { name: "Good night" }));
    expect(calls.some((c) => c.path === "/sequences/good_night/run")).toBe(false);
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Run" }));
    expect(calls.at(-1)).toMatchObject({ method: "POST", path: "/sequences/good_night/run" });
    expect(await screen.findByText("Good night started.")).toBeInTheDocument();
  });

  it("shows the API's words when a command fails", async () => {
    setNarrow(false);
    show({ "POST /entities/light.porch/commands/toggle": [409, { detail: "This device can't take commands right now." }] });
    await userEvent.click(await screen.findByRole("button", { name: /Porch light/ }));
    expect(await screen.findByText(/can't take commands right now/)).toBeInTheDocument();
  });

  it("is one column on a phone", async () => {  // Review Focus 5
    setNarrow(true);
    show();
    await screen.findByRole("heading", { name: "Outside" });
    const tile = screen.getByRole("button", { name: /Porch light/ }).closest(".card") as HTMLElement;
    expect(tile.style.gridColumn).toBe("");
    expect(tile.closest(".grid")).toHaveClass("one-column");
  });

  it("uses the wide grid otherwise", async () => {
    setNarrow(false);
    show();
    await screen.findByRole("heading", { name: "Outside" });
    const tile = screen.getByRole("button", { name: /Porch light/ }).closest(".card") as HTMLElement;
    expect(tile.style.gridColumn).toBe("span 3");
  });
});
