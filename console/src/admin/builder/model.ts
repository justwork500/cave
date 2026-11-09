/**
 * The dashboard builder's draft: the YAML file as a plain object, changed by pure functions.
 * Everything is carried through as written, so fields the builder has no control for survive a visual edit.
 */
import { parse, parseDocument, stringify, visit } from "yaml";
import type { Card, EntityView, FullEntity } from "../../api/types";
import { SWITCHABLE } from "../../cards/entity";

export type DraftCard = { type: string; w?: number; h?: number; [k: string]: unknown };
export interface DraftGroup { title: string; cards?: DraftCard[]; [k: string]: unknown }
export interface DraftView { id: string; title: string; sections?: DraftGroup[]; [k: string]: unknown }
export interface Draft { dashboard: { title: string; views?: DraftView[]; [k: string]: unknown } }
export interface Spot { view: number; group: number; card: number }
export type Source =
  | { kind: "device" | "sensor"; entity: FullEntity }
  | { kind: "automation" | "routine" | "script"; id: string; name: string }
  | { kind: "note" | "list" };

const CARD_TYPES = new Set(["tile", "entities", "gauge", "button", "markdown"]);
const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

/** A shape check so the builder can draw it. Full validation happens on Save. */
export function parseDraft(text: string): { draft: Draft } | { reason: string } {
  let doc: unknown;
  try {
    doc = parse(text);
  } catch (e) {
    return { reason: `This YAML has a mistake: ${(e as Error).message.split("\n")[0]}` };
  }
  if (!isObject(doc) || !isObject(doc.dashboard)) return { reason: "There's no dashboard in this YAML." };
  const { views = [] } = doc.dashboard;
  if (!Array.isArray(views)) return { reason: "The views in this YAML need to be a list." };
  for (const view of views as unknown[]) {
    const sections = isObject(view) ? (view.sections ?? []) : null;
    if (!Array.isArray(sections)) return { reason: "Each of the views needs a list of sections." };
    for (const section of sections as unknown[]) {
      const cards = isObject(section) ? (section.cards ?? []) : null;
      if (!Array.isArray(cards)) return { reason: "Each section needs a list of cards." };
      if (typeof (section as { title?: unknown }).title !== "string") return { reason: "Each section's title needs to be text." };
      for (const card of cards as unknown[]) {
        const type = isObject(card) ? String(card.type) : "unnamed";
        if (!CARD_TYPES.has(type)) return { reason: `The builder doesn't know a "${type}" card.` };
        if (type === "entities" && !Array.isArray((card as { entities?: unknown }).entities)) {
          return { reason: "A list tile's entities need to be a list." };
        }
      }
    }
  }
  return { draft: doc as unknown as Draft };
}

export function writeDraft(draft: Draft): string {
  return stringify(draft, { lineWidth: 0, compat: "yaml-1.1" }); // the server reads YAML 1.1, where a bare On is true
}

export function hasComments(text: string): boolean {
  const doc = parseDocument(text);
  let found = Boolean(doc.comment || doc.commentBefore);
  visit(doc, (_key, node) => {
    const n = node as { comment?: string | null; commentBefore?: string | null };
    if (n.comment || n.commentBefore) {
      found = true;
      return visit.BREAK;
    }
    return undefined;
  });
  return found;
}

export function cardFor(source: Source): DraftCard {
  const size = { w: 3, h: 1 };
  switch (source.kind) {
    case "device":
    case "sensor": {
      const { entity_id: entity, capability } = source.entity;
      return { type: "tile", entity, tap_action: SWITCHABLE.has(capability) ? "toggle" : "none", ...size };
    }
    case "automation":
      return { type: "button", name: source.name, action: `automation.${source.id}`, ...size };
    case "routine":
      return { type: "button", name: source.name, action: `sequence.${source.id}`, ...size };
    case "script":
      return { type: "button", name: source.name, action: `script.${source.id}`, confirm: true, ...size };
    case "note":
      return { type: "markdown", content: "", ...size };
    case "list":
      return { type: "entities", entities: [], ...size };
  }
}

function edit(d: Draft, change: (copy: Draft) => void): Draft {
  const copy = structuredClone(d);
  change(copy);
  return copy;
}

const groupsOf = (d: Draft, view: number): DraftGroup[] => {
  const v = d.dashboard.views?.[view];
  if (!v) return [];
  v.sections ??= [];
  return v.sections;
};

const cardsOf = (d: Draft, view: number, group: number): DraftCard[] => {
  const g = groupsOf(d, view)[group];
  if (!g) return [];
  g.cards ??= [];
  return g.cards;
};

export function addCard(d: Draft, view: number, group: number, card: DraftCard): Draft {
  return edit(d, (c) => void cardsOf(c, view, group).push(card));
}

/** to.card is where the tile ends up, counted after it has left its old place. */
export function moveCard(d: Draft, from: Spot, to: Spot): Draft {
  return edit(d, (c) => {
    const [card] = cardsOf(c, from.view, from.group).splice(from.card, 1);
    if (card) cardsOf(c, to.view, to.group).splice(to.card, 0, card);
  });
}

export function removeCard(d: Draft, at: Spot): Draft {
  return edit(d, (c) => void cardsOf(c, at.view, at.group).splice(at.card, 1));
}

/** An empty value removes the setting, so a cleared label isn't written as label: "". */
export function updateCard(d: Draft, at: Spot, change: Record<string, unknown>): Draft {
  return edit(d, (c) => {
    const card = cardsOf(c, at.view, at.group)[at.card];
    if (!card) return;
    for (const [key, value] of Object.entries(change)) {
      if (value === "" || value === null || value === undefined) Reflect.deleteProperty(card, key);
      else card[key] = value;
    }
  });
}

export function addGroup(d: Draft, view: number, title: string): Draft {
  return edit(d, (c) => {
    c.dashboard.views ??= [];
    if (c.dashboard.views.length === 0) c.dashboard.views.push({ id: "main", title: "Main", sections: [] });
    groupsOf(c, view).push({ title, cards: [] });
  });
}

export function renameGroup(d: Draft, view: number, group: number, title: string): Draft {
  return edit(d, (c) => {
    const g = groupsOf(c, view)[group];
    if (g) g.title = title;
  });
}

export function moveGroup(d: Draft, view: number, from: number, to: number): Draft {
  return edit(d, (c) => {
    const groups = groupsOf(c, view);
    const [g] = groups.splice(from, 1);
    if (g) groups.splice(to, 0, g);
  });
}

export function removeGroup(d: Draft, view: number, group: number): Draft {
  return edit(d, (c) => void groupsOf(c, view).splice(group, 1));
}

/** Where the selected tile is once another has gone, or null if it was the one removed. */
export function afterRemove(selected: Spot | null, removed: Spot): Spot | null {
  if (!selected || selected.view !== removed.view || selected.group !== removed.group) return selected;
  if (selected.card === removed.card) return null;
  return selected.card > removed.card ? { ...selected, card: selected.card - 1 } : selected;
}

export const SIZES = { small: { w: 3, h: 1 }, wide: { w: 6, h: 1 }, tall: { w: 3, h: 2 }, large: { w: 6, h: 2 } };

export function sizeOf(card: DraftCard): keyof typeof SIZES | "custom" {
  const { w = 3, h = 1 } = card;
  const found = Object.entries(SIZES).find(([, s]) => s.w === w && s.h === h);
  return found ? (found[0] as keyof typeof SIZES) : "custom";
}

/** What the real cards draw for a card that hasn't been saved. Anything unknown reads as locked, as it does on the page. */
export function viewCard(card: DraftCard, states: EntityView[]): Card {
  const find = (id: unknown): EntityView =>
    states.find((e) => e.entity_id === id) ??
    { entity_id: String(id), name: String(id), area_id: null, restricted: true };
  const base = { w: 3, h: 1, ...card };
  switch (card.type) {
    case "tile": {
      const entity = find(card.entity);
      return { tap_action: "toggle", ...base, entity, locked: Boolean(entity.restricted) } as Card;
    }
    case "gauge": {
      const entity = find(card.entity);
      return { min: 0, max: 100, severity: null, ...base, entity, locked: Boolean(entity.restricted) } as Card;
    }
    case "entities":
      return { ...base, entities: ((card.entities ?? []) as unknown[]).map(find) } as Card;
    case "button":
      return { confirm: null, action: null, entity: null, command: null, ...base, allowed: true } as Card;
    default:
      return { ...base, text: String(card.content ?? "") } as Card;
  }
}

/** The name a person knows a card by. */
export function nameOf(card: DraftCard, states: EntityView[]): string {
  if (typeof card.label === "string" && card.label) return card.label;
  if (typeof card.name === "string") return card.name;
  if (card.type === "markdown") return "Text note";
  if (card.type === "entities") return "List tile";
  return states.find((e) => e.entity_id === card.entity)?.name ?? String(card.entity);
}
