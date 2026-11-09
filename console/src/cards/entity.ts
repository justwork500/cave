import { useEffect, useState } from "react";
import type { EntityView, FullEntity } from "../api/types";
import { useLive } from "../app/live";

const WORDS: Record<string, string> = {
  on: "On", off: "Off", open: "Open", closed: "Closed", opening: "Opening", closing: "Closing",
  locked: "Locked", unlocked: "Unlocked", home: "Home", away: "Away",
  unavailable: "Not responding", unknown: "Unknown",
};

export function stateText(state: string | null, attributes: Record<string, unknown>): string {
  if (state === null) return "Unknown";
  const unit = typeof attributes.unit === "string" ? attributes.unit : "";
  if (unit && state.trim() !== "" && !Number.isNaN(Number(state))) return `${state}\u00a0${unit}`;  // no-break space: the unit never wraps away from its number
  return WORDS[state] ?? state.charAt(0).toUpperCase() + state.slice(1).replaceAll("_", " ");
}

// shortcut: rooms show as their slug in words ("front_yard" → "Front yard"); fetch area names if renamed areas matter
export function roomText(areaId: string | null): string {
  return areaId ? stateText(areaId, {}) : "";
}

export const isFull = (e: EntityView): e is FullEntity => !e.restricted && "state" in e;

/** The entity's state, kept current by the live feed. */
export function useLiveState(e: EntityView): { state: string | null; attributes: Record<string, unknown> } {
  const live = useLive();
  const full = isFull(e);
  const [current, setCurrent] = useState(() => ({
    state: full ? e.state : null,
    attributes: full ? e.attributes : {},
  }));
  useEffect(
    () => (full ? live?.onState(e.entity_id, (ev) => setCurrent({ state: ev.new, attributes: ev.attributes })) : undefined),
    [live, full, e.entity_id],
  );
  return current;
}
