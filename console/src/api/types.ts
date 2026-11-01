/** The API shapes the console uses. Mirrors core/cave/api. */

export type Role = "admin" | "operator" | "household" | "guest" | "auditor";

export interface Me {
  kind: "user" | "token" | "screen";
  id: string;
  username: string | null;
  display_name: string;
  role: Role | null;
  has_totp: boolean;
  sections: string[];
}

export interface FullEntity {
  entity_id: string;
  name: string;
  area_id: string | null;
  capability: string;
  state: string | null;
  attributes: Record<string, unknown>;
  last_changed: string | null;
  restricted?: undefined;
}

export interface RestrictedEntity {
  entity_id: string;
  name: string;
  area_id: string | null;
  restricted: true;
}

export type EntityView = FullEntity | RestrictedEntity;

interface CardBase {
  w: number;
  h: number;
}
export interface TileCard extends CardBase {
  type: "tile";
  entity: EntityView;
  tap_action: "toggle" | "none";
  locked: boolean;
}
export interface GaugeCard extends CardBase {
  type: "gauge";
  entity: EntityView;
  min: number;
  max: number;
  severity: Record<string, number> | null;
  locked: boolean;
}
export interface EntitiesCard extends CardBase {
  type: "entities";
  entities: EntityView[];
}
export interface ButtonCard extends CardBase {
  type: "button";
  name: string;
  action: string | null;
  entity: string | null;
  command: string | null;
  confirm: boolean | null;
  allowed: boolean;
}
export interface MarkdownCard extends CardBase {
  type: "markdown";
  text: string;
}
export type Card = TileCard | GaugeCard | EntitiesCard | ButtonCard | MarkdownCard;

export interface DashboardView {
  slug: string;
  title: string;
  icon: string | null;
  views: { id: string; title: string; sections: { title: string; cards: Card[] }[] }[];
}

export interface Listed {
  id: string;
  name: string;
  allowed: boolean;
}

export interface Item {
  id: string;
  kind: "dashboard" | "section" | "action" | "feature";
  name: string;
  allowed: boolean;
  status?: "enabled" | "disabled";
  visibility?: "show" | "hide" | "restrict";
  others_see?: "locked" | "none";
  network?: "anywhere" | "local";
  builtin?: boolean;
}

export interface Assignment {
  kind: "user" | "group" | "role" | "screen";
  id: string;
}

export interface Notification {
  id: number;
  title: string | null;
  message: string;
  source: string;
  created_at: string;
  read_at: string | null;
}

export interface Step {
  path: string;
  type: string;
  detail: string;
  started_at: string;
  result: "ok" | "skipped" | "failed" | "stopped" | "what_if";
  data: Record<string, unknown>;
}

export interface Trace {
  steps: Step[];
  outcome: "finished" | "stopped" | "failed" | "cancelled" | "conditions_not_met";
  variables: Record<string, unknown>;
  error: string | null;
}

export interface Summary {
  mqtt?: { status: string; entities: number };
  unavailable?: number;
  failures_24h?: number;
  screens_pending?: number;
}
