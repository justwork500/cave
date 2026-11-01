/**
 * The Simple view's shape: one trigger, at most one condition, and notify/call/routine/script actions.
 * A sentence is the parsed file itself, so converting back can't lose anything the shape allows.
 */
import { isNode, isScalar, parseDocument, stringify, visit } from "yaml";

export type Trigger =
  | { type: "state"; entity: string; from?: string; to?: string; for?: string | number }
  | { type: "numeric_state"; entity: string; above?: number; below?: number; for?: string | number }
  | { type: "time"; at: string };
export type Condition =
  | { type: "state"; entity: string; state: string }
  | { type: "numeric_state"; entity: string; above?: number; below?: number }
  | { type: "time"; after?: string; before?: string; weekdays?: string[] };
export type Action =
  | { type: "notify"; message: string; title?: string; targets?: string[] }
  | { type: "call"; target: string; command: string; args?: Record<string, unknown> }
  | { type: "sequence"; ref: string; with?: Record<string, unknown> }
  | { type: "script"; ref: string; target?: string; args?: Record<string, unknown>; result_var?: string };

export interface Sentence {
  automation: {
    id: string;
    name: string;
    mode?: string;
    max?: number;
    enabled?: boolean;
    triggers: [Trigger];
    conditions?: [] | [Condition];
    actions: Action[];
  };
}

const KEYS: Record<string, Record<string, string[]>> = {
  trigger: { state: ["entity", "from", "to", "for"], numeric_state: ["entity", "above", "below", "for"], time: ["at"] },
  condition: { state: ["entity", "state"], numeric_state: ["entity", "above", "below"],
               time: ["after", "before", "weekdays"] },
  action: { notify: ["message", "title", "targets"], call: ["target", "command", "args"], sequence: ["ref", "with"],
            script: ["ref", "target", "args", "result_var"] },
};
const TOP = ["id", "name", "mode", "max", "enabled", "triggers", "conditions", "actions"];

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

/** Values the Simple view shows and edits as text; anything else there is outside its shape. */
const TEXT = ["entity", "target", "command", "ref", "from", "to", "state", "at", "after", "before", "message", "title"];

function fits(v: unknown, part: keyof typeof KEYS): boolean {
  if (!isObj(v) || typeof v.type !== "string") return false;
  const allowed = KEYS[part]?.[v.type];
  return Boolean(allowed) && Object.entries(v).every(([k, x]) =>
    k === "type" || (allowed?.includes(k) && (!TEXT.includes(k) || typeof x === "string")));
}

/** The server reads YAML 1.1, so this does too: unquoted on/off are booleans there. */
const PARSE = { version: "1.1" } as const;

export function fromYaml(text: string): Sentence | null {
  const doc = parseDocument(text, PARSE);
  if (doc.errors.length) return null;
  let unsafe = Boolean(doc.commentBefore || doc.comment);
  visit(doc, (_, node) => {
    // rebuilding the text would drop the comments the user wrote
    if (isNode(node) && (node.commentBefore || node.comment)) unsafe = true;
    // a plain 07:00, on or 0700 turns into something else here, and not always the same thing on the server
    if (isScalar(node) && node.type === "PLAIN" && typeof node.value !== "string" && String(node.value) !== node.source) {
      unsafe = true;
    }
  });
  if (unsafe) return null;
  const root: unknown = doc.toJS();
  if (!isObj(root) || Object.keys(root).join() !== "automation") return null;
  const a = root.automation;
  if (!isObj(a) || !Object.keys(a).every((k) => TOP.includes(k))) return null;
  if (typeof a.id !== "string" || typeof a.name !== "string") return null;
  const { triggers, conditions = [], actions } = a;
  if (!Array.isArray(triggers) || triggers.length !== 1 || !fits(triggers[0], "trigger")) return null;
  if (!Array.isArray(conditions) || conditions.length > 1 || !conditions.every((c) => fits(c, "condition"))) return null;
  if (!Array.isArray(actions) || actions.length === 0 || !actions.every((x) => fits(x, "action"))) return null;
  return root as unknown as Sentence;
}

export function toYaml(s: Sentence): string {
  // every string quoted: "on" left plain would be read back as true by the server
  return stringify(s, { defaultStringType: "QUOTE_DOUBLE", defaultKeyType: "PLAIN", lineWidth: 0 });
}
