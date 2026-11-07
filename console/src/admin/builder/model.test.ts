import { describe, expect, it } from "vitest";
import type { FullEntity } from "../../api/types";
import {
  type Draft, addCard, addGroup, afterRemove, cardFor, hasComments, moveCard, moveGroup, parseDraft, removeCard,
  removeGroup, renameGroup, sizeOf, updateCard, viewCard, writeDraft,
} from "./model";

const YAML = `dashboard:
  title: Home
  custom_key: kept
  views:
    - id: main
      title: Main
      sections:
        - title: Bedroom
          cards:
            - type: tile
              entity: switch.left
              w: 5
              h: 3
            - type: gauge
              entity: sensor.load
              severity: { green: 0, red: 85 }
        - title: Office
          cards:
            - type: tile
              entity: switch.lamp
`;

function draft(text = YAML): Draft {
  const out = parseDraft(text);
  if (!("draft" in out)) throw new Error(out.reason);
  return out.draft;
}

const entity = (id: string, capability: string, state = "off"): FullEntity => ({
  entity_id: id, name: id, area_id: null, capability, state, attributes: {}, last_changed: null });

const cards = (d: Draft, group: number) =>
  (d.dashboard.views?.[0]?.sections?.[group]?.cards ?? []).map((c) => c.entity);

describe("the draft", () => {
  it("keeps fields it has no control for", () => {
    const changed = updateCard(draft(), { view: 0, group: 0, card: 1 }, { label: "Load" });
    const out = writeDraft(changed);
    const again = draft(out);
    expect(again.dashboard.custom_key).toBe("kept");
    const [tile, gauge] = again.dashboard.views?.[0]?.sections?.[0]?.cards ?? [];
    expect(tile).toMatchObject({ w: 5, h: 3 });
    expect(gauge).toMatchObject({ label: "Load", severity: { green: 0, red: 85 } });
  });

  it("never changes the draft it was given", () => {
    const before = draft();
    const copy = JSON.stringify(before);
    moveCard(before, { view: 0, group: 0, card: 0 }, { view: 0, group: 1, card: 0 });
    updateCard(before, { view: 0, group: 0, card: 0 }, { label: "x" });
    removeGroup(before, 0, 0);
    expect(JSON.stringify(before)).toBe(copy);
  });

  it.each([
    ["dashboard: [", "This YAML has a mistake"],
    ["title: Home\n", "no dashboard"],
    ["dashboard:\n  title: A\n  views: 3\n", "views"],
    ["dashboard:\n  title: A\n  views:\n    - id: m\n      title: M\n      sections:\n        - title: S\n          cards:\n            - type: clock\n", "clock"],
  ])("explains YAML it can't use: %s", (text, reason) => {
    const out = parseDraft(text);
    expect("reason" in out && out.reason).toContain(reason);
  });

  it("adds a view when the dashboard has none", () => {
    const d = addGroup(draft("dashboard:\n  title: Gate\n"), 0, "Doors");
    expect(d.dashboard.views).toEqual([{ id: "main", title: "Main", sections: [{ title: "Doors", cards: [] }] }]);
  });

  it("moves a tile within a group and between groups", () => {
    const within = moveCard(draft(), { view: 0, group: 0, card: 0 }, { view: 0, group: 0, card: 1 });
    expect(cards(within, 0)).toEqual(["sensor.load", "switch.left"]);
    const across = moveCard(draft(), { view: 0, group: 0, card: 1 }, { view: 0, group: 1, card: 0 });
    expect(cards(across, 0)).toEqual(["switch.left"]);
    expect(cards(across, 1)).toEqual(["sensor.load", "switch.lamp"]);
  });

  it("moving to the same place changes nothing", () => {
    const d = draft();
    expect(moveCard(d, { view: 0, group: 0, card: 1 }, { view: 0, group: 0, card: 1 })).toEqual(d);
  });

  it("adds, removes, renames and reorders", () => {
    let d = addCard(draft(), 0, 1, { type: "tile", entity: "switch.new" });
    expect(cards(d, 1)).toEqual(["switch.lamp", "switch.new"]);
    d = removeCard(d, { view: 0, group: 1, card: 0 });
    expect(cards(d, 1)).toEqual(["switch.new"]);
    d = renameGroup(d, 0, 1, "Study");
    d = moveGroup(d, 0, 1, 0);
    expect(d.dashboard.views?.[0]?.sections?.map((s) => s.title)).toEqual(["Study", "Bedroom"]);
  });

  it("removing a group removes its tiles", () => {
    const d = removeGroup(draft(), 0, 0);
    expect(d.dashboard.views?.[0]?.sections?.map((s) => s.title)).toEqual(["Office"]);
  });

  it("a cleared label leaves no label key", () => {
    const at = { view: 0, group: 0, card: 0 };
    const d = updateCard(updateCard(draft(), at, { label: "Fan" }), at, { label: "", icon: null, color: undefined });
    expect(d.dashboard.views?.[0]?.sections?.[0]?.cards?.[0]).not.toHaveProperty("label");
    expect(writeDraft(d)).not.toContain("label");
  });

  it("finds real comments but not a # inside a value", () => {
    expect(hasComments("# note\ndashboard:\n  title: A\n")).toBe(true);
    expect(hasComments("dashboard:\n  title: A # note\n")).toBe(true);
    expect(hasComments("dashboard:\n  views:\n    # note\n    - id: a\n")).toBe(true);
    expect(hasComments('dashboard:\n  title: "a # b"\n')).toBe(false);
    expect(hasComments("dashboard:\n  title: a#b\n")).toBe(false);
  });

  it("keeps the selection on the right tile after a removal", () => {
    const at = (group: number, card: number) => ({ view: 0, group, card });
    expect(afterRemove(at(0, 2), at(0, 0))).toEqual(at(0, 1));
    expect(afterRemove(at(0, 2), at(0, 2))).toBeNull();
    expect(afterRemove(at(0, 2), at(0, 3))).toEqual(at(0, 2));
    expect(afterRemove(at(1, 2), at(0, 0))).toEqual(at(1, 2));
    expect(afterRemove(null, at(0, 0))).toBeNull();
  });

  it("gives each kind of item its default tile", () => {
    const size = { w: 3, h: 1 };
    expect(cardFor({ kind: "device", entity: entity("switch.a", "switch") })).toEqual(
      { type: "tile", entity: "switch.a", tap_action: "toggle", ...size });
    expect(cardFor({ kind: "device", entity: entity("lock.a", "lock") })).toEqual(
      { type: "tile", entity: "lock.a", tap_action: "none", ...size });
    expect(cardFor({ kind: "sensor", entity: entity("sensor.a", "sensor") })).toEqual(
      { type: "tile", entity: "sensor.a", tap_action: "none", ...size });
    expect(cardFor({ kind: "automation", id: "a", name: "A" })).toEqual(
      { type: "button", name: "A", action: "automation.a", ...size });
    expect(cardFor({ kind: "routine", id: "r", name: "R" })).toEqual(
      { type: "button", name: "R", action: "sequence.r", ...size });
    expect(cardFor({ kind: "script", id: "s.sh", name: "S" })).toEqual(
      { type: "button", name: "S", action: "script.s.sh", confirm: true, ...size });
    expect(cardFor({ kind: "note" })).toEqual({ type: "markdown", content: "", ...size });
    expect(cardFor({ kind: "list" })).toEqual({ type: "entities", entities: [], ...size });
  });

  it("names sizes, and calls anything else custom", () => {
    expect(sizeOf({ type: "tile" })).toBe("small");
    expect(sizeOf({ type: "tile", w: 6, h: 1 })).toBe("wide");
    expect(sizeOf({ type: "tile", w: 3, h: 2 })).toBe("tall");
    expect(sizeOf({ type: "tile", w: 6, h: 2 })).toBe("large");
    expect(sizeOf({ type: "tile", w: 5, h: 3 })).toBe("custom");
  });

  it("turns a draft card into what the real cards draw", () => {
    const states = [entity("switch.a", "switch"),
                    { entity_id: "lock.b", name: "Door", area_id: null, restricted: true as const }];
    expect(viewCard({ type: "tile", entity: "switch.a" }, states)).toMatchObject({
      w: 3, h: 1, tap_action: "toggle", locked: false, entity: { name: "switch.a" } });
    expect(viewCard({ type: "tile", entity: "lock.b" }, states)).toMatchObject({ locked: true });
    expect(viewCard({ type: "tile", entity: "switch.gone" }, states)).toMatchObject({
      entity: { entity_id: "switch.gone", name: "switch.gone" } });
    expect(viewCard({ type: "markdown", content: "Hi" }, states)).toMatchObject({ text: "Hi" });
    expect(viewCard({ type: "button", name: "Go", action: "automation.a" }, states)).toMatchObject({ allowed: true });
    expect(viewCard({ type: "gauge", entity: "switch.a" }, states)).toMatchObject({ min: 0, max: 100, severity: null });
    expect(viewCard({ type: "entities", entities: ["switch.a"] }, states)).toMatchObject({ entities: [states[0]] });
  });
});
