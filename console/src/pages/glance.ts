/** The household dashboard's greeting and the house at a glance, worked out from the devices it shows. */
import type { EntityView, FullEntity } from "../api/types";
import { isFull, roomText } from "../cards/entity";

const SWITCHABLE = new Set(["light", "switch", "fan"]);
const ACTIVE = new Set(["on", "open", "opening", "unlocked"]);

export function greeting(now: Date, name?: string): string {
  const h = now.getHours();
  const part = h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
  return name ? `Good ${part}, ${name}` : `Good ${part}`;
}

/** "Garage door" → "garage door", but "UPS load" stays as it is. */
const lower = (name: string) => (/^.[a-z]/.test(name) ? name.charAt(0).toLowerCase() + name.slice(1) : name);
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** One sentence: what is on, open or not responding. Restricted devices are left out. */
export function finding(entities: EntityView[]): string {
  const full = entities.filter(isFull);
  const working = full.filter((e) => e.state !== "unavailable");
  const lights = working.filter((e) => e.capability === "light");
  const parts: string[] = [];
  if (lights.length) {
    const on = lights.filter((e) => e.state === "on").length;
    parts.push(on ? `${plural(on, "light", "lights")} on` : "all lights off");
  }
  for (const e of working.filter((x) => x.capability === "cover" || x.capability === "lock")) {
    parts.push(`${lower(e.name)} ${e.state ?? "unknown"}`);
  }
  const down = full.length - working.length;
  if (down) parts.push(`${plural(down, "device", "devices")} not responding`);
  if (!parts.length) return "";
  const sentence = parts.join(", ");
  return `${sentence.charAt(0).toUpperCase()}${sentence.slice(1)}.`;
}

export interface Room {
  name: string;
  /** How many things in it are on, open or unlocked. */
  on: number;
  text: string;
}

/** Each room, in the order it first appears, with what is on in it. Rooms with only sensors are left out. */
export function rooms(entities: EntityView[]): Room[] {
  const byRoom = new Map<string, FullEntity[]>();
  for (const e of entities.filter(isFull)) {
    if (!e.area_id) continue;
    byRoom.set(e.area_id, [...(byRoom.get(e.area_id) ?? []), e]);
  }
  const out: Room[] = [];
  for (const [area, list] of byRoom) {
    const working = list.filter((e) => e.state !== "unavailable");
    const switches = working.filter((e) => SWITCHABLE.has(e.capability));
    const doors = working.filter((e) => e.capability === "cover" || e.capability === "lock");
    const on = switches.filter((e) => e.state === "on").length + doors.filter((e) => ACTIVE.has(e.state ?? "")).length;
    let text: string;
    if (switches.length) text = on ? `${on} on` : "all off";
    else if (doors[0]) text = doors[0].state ?? "unknown";
    else if (working.length < list.length) text = "not responding";
    else continue;
    out.push({ name: roomText(area), on, text });
  }
  return out;
}
