import type { Sentence } from "./sentence";

export interface Blank {
  id: string;
  label: string;
  kind: "device" | "time" | "number" | "routine" | "script" | "text";
  example: string;
}

export interface Recipe {
  id: string;
  title: string;
  blanks: Blank[];
  /** Needs presence, which comes in a later phase. */
  later?: boolean;
  build: (v: Record<string, string>) => Sentence[];
}

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 50) || "new";

export const RECIPES: Recipe[] = [
  {
    id: "lights-schedule",
    title: "Lights on at one time and off at another",
    blanks: [
      { id: "light", label: "Light", kind: "device", example: "light.porch" },
      { id: "on", label: "On at", kind: "time", example: "18:30" },
      { id: "off", label: "Off at", kind: "time", example: "23:00" },
    ],
    // one trigger per automation in the Simple view, so this is a pair
    build: (v) => (["on", "off"] as const).map((when) => ({
      automation: {
        id: `${slug(v.light ?? "")}-${when}`,
        name: `Lights ${when} at ${v[when] ?? ""}`,
        triggers: [{ type: "time", at: v[when] ?? "" }],
        actions: [{ type: "call", target: v.light ?? "", command: when === "on" ? "turn_on" : "turn_off" }],
      },
    })),
  },
  {
    id: "washer-done",
    title: "Tell me when the washer finishes",
    blanks: [
      { id: "power", label: "Washer power sensor", kind: "device", example: "sensor.washer_power" },
      { id: "watts", label: "Finished below (watts)", kind: "number", example: "5" },
    ],
    build: (v) => [{
      automation: {
        id: "washer-finished",
        name: "Washer finished",
        triggers: [{ type: "numeric_state", entity: v.power ?? "", below: Number(v.watts), for: "5m" }],
        actions: [{ type: "notify", message: "The washer has finished." }],
      },
    }],
  },
  {
    id: "ups-on-battery",
    title: "Alert me and run a routine when the UPS is on battery",
    blanks: [
      { id: "ups", label: "UPS on-battery sensor", kind: "device", example: "binary_sensor.ups_on_battery" },
      { id: "routine", label: "Routine to run", kind: "routine", example: "sequence.lab_safe_shutdown" },
    ],
    build: (v) => [{
      automation: {
        id: "ups-on-battery",
        name: "UPS on battery",
        triggers: [{ type: "state", entity: v.ups ?? "", to: "on", for: "2m" }],
        actions: [
          { type: "notify", title: "Power outage", message: "The UPS is on battery." },
          { type: "sequence", ref: v.routine ?? "" },
        ],
      },
    }],
  },
  {
    id: "script-schedule",
    title: "Run a script on a schedule",
    blanks: [
      { id: "script", label: "Script", kind: "script", example: "scripts/backup.sh" },
      { id: "at", label: "At", kind: "time", example: "02:00" },
    ],
    build: (v) => [{
      automation: {
        id: `run-${slug((v.script ?? "").replace(/^scripts\//, ""))}`,
        name: `Run ${(v.script ?? "").replace(/^scripts\//, "")} at ${v.at ?? ""}`,
        triggers: [{ type: "time", at: v.at ?? "" }],
        actions: [{ type: "script", ref: v.script ?? "" }],
      },
    }],
  },
  { id: "last-leaves", title: "Everything off when the last person leaves", blanks: [], later: true, build: () => [] },
  { id: "door-away", title: "Tell me if a door opens while I'm away", blanks: [], later: true, build: () => [] },
];
