import { describe, expect, it } from "vitest";
import type { EntityView } from "../api/types";
import { finding, greeting, rooms } from "./glance";

const e = (entity_id: string, name: string, area_id: string | null, state: string): EntityView => ({
  entity_id, name, area_id, capability: entity_id.split(".")[0] ?? "", state, attributes: {}, last_changed: null,
});
const HOUSE: EntityView[] = [
  e("light.ceiling", "Ceiling light", "living_room", "on"),
  e("light.lamp", "Reading lamp", "living_room", "off"),
  e("light.night", "Night light", "kids_room", "on"),
  e("cover.garage", "Garage door", "garage", "closed"),
  e("lock.front", "Front door", "front_yard", "unlocked"),
  e("switch.heater", "Heater", "office", "unavailable"),
  { entity_id: "cover.shed", name: "Shed door", area_id: "garage", restricted: true },
];

describe("the house at a glance", () => {
  it("greets by the time of day", () => {
    expect(greeting(new Date(2026, 10, 1, 7), "Jordan")).toBe("Good morning, Jordan");
    expect(greeting(new Date(2026, 10, 1, 13), "Jordan")).toBe("Good afternoon, Jordan");
    expect(greeting(new Date(2026, 10, 1, 21))).toBe("Good evening");
  });

  it("says what is on, open and not responding, in words", () => {
    expect(finding(HOUSE)).toBe("2 lights on, garage door closed, front door unlocked, 1 device not responding.");
    expect(finding([e("light.a", "A", null, "off")])).toBe("All lights off.");
    expect(finding([])).toBe("");
  });

  it("counts what is on in each room, and leaves restricted devices out", () => {
    expect(rooms(HOUSE)).toEqual([
      { name: "Living room", on: 1, text: "1 on" },
      { name: "Kids room", on: 1, text: "1 on" },
      { name: "Garage", on: 0, text: "closed" },
      { name: "Front yard", on: 1, text: "unlocked" },
      { name: "Office", on: 0, text: "not responding" },
    ]);
  });
});
