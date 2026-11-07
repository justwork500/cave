import { Button, Field, Input, Select, Switch, Textarea } from "@fluentui/react-components";
import { ArrowUpRegular, DismissRegular } from "@fluentui/react-icons";
import { useState } from "react";
import type { EntityView } from "../../api/types";
import { SWITCHABLE, isFull } from "../../cards/entity";
import { COLORS, ICONS } from "../../cards/look";
import { type DraftCard, type DraftGroup, SIZES, nameOf, sizeOf } from "./model";

const SIZE_NAMES = { small: "Small", wide: "Wide", tall: "Tall", large: "Large" };
const title = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function MoveButtons({ canEarlier, canLater, onMove }: {
  canEarlier: boolean;
  canLater: boolean;
  onMove: (by: -1 | 1) => void;
}) {
  return (
    <div className="row start">
      <Button size="small" disabled={!canEarlier} onClick={() => onMove(-1)}>Move earlier</Button>
      <Button size="small" disabled={!canLater} onClick={() => onMove(1)}>Move later</Button>
    </div>
  );
}

/** A run button must keep a name, so clearing the box leaves the last one in place until there's a new one. */
function ButtonName({ card, onChange }: { card: DraftCard; onChange: (name: string) => void }) {
  const [text, setText] = useState(String(card.name ?? ""));
  return (
    <Field label="Label">
      <Input value={text} onChange={(_, d) => {
        setText(d.value);
        if (d.value.trim()) onChange(d.value);
      }} />
    </Field>
  );
}

function ShowsAs({ card, entity, onChange }: {
  card: DraftCard;
  entity: EntityView | undefined;
  onChange: (change: Record<string, unknown>) => void;
}) {
  const current = card.type === "gauge" ? "gauge" : card.tap_action === "none" ? "status" : "toggle";
  const full = entity && isFull(entity) ? entity : undefined;
  const numeric = full?.state != null && full.state.trim() !== "" && !Number.isNaN(Number(full.state));
  const toggle = current === "toggle" || (full !== undefined && SWITCHABLE.has(full.capability));
  const gauge = current === "gauge" || numeric;
  const tile = { type: "tile", min: null, max: null, severity: null };
  return (
    <Field label="Shows as">
      <Select value={current} onChange={(_, d) => onChange(
        d.value === "gauge" ? { type: "gauge", tap_action: null }
          : { ...tile, tap_action: d.value === "toggle" ? "toggle" : "none" })}>
        {toggle && <option value="toggle">Toggle</option>}
        <option value="status">Status only</option>
        {gauge && <option value="gauge">Gauge</option>}
      </Select>
    </Field>
  );
}

function Items({ card, states, onChange }: {
  card: DraftCard;
  states: EntityView[];
  onChange: (entities: string[]) => void;
}) {
  const items = (card.entities ?? []) as string[];
  const nameFor = (id: string) => states.find((e) => e.entity_id === id)?.name ?? id;
  const left = states.filter(isFull).filter((e) => !items.includes(e.entity_id));
  return (
    <>
      <ul className="palette-list">
        {items.map((id, i) => (
          <li key={id}>
            <span>{nameFor(id)}</span>
            <span>
              {i > 0 && (
                <Button size="small" appearance="subtle" icon={<ArrowUpRegular />} aria-label={`Move ${nameFor(id)} up`}
                        onClick={() => onChange(items.with(i - 1, id).with(i, items[i - 1] as string))} />
              )}
              <Button size="small" appearance="subtle" icon={<DismissRegular />} aria-label={`Take out ${nameFor(id)}`}
                      onClick={() => onChange(items.filter((x) => x !== id))} />
            </span>
          </li>
        ))}
      </ul>
      <Field label="Add an item">
        <Select value="" onChange={(_, d) => onChange([...items, d.value])}>
          <option value="" disabled>Choose</option>
          {left.map((e) => <option key={e.entity_id} value={e.entity_id}>{e.name}</option>)}
        </Select>
      </Field>
    </>
  );
}

export function TileSettings({ card, states, groups, group, index, onChange, onMove, onMoveToGroup }: {
  card: DraftCard;
  states: EntityView[];
  groups: DraftGroup[];
  group: number;
  index: number;
  onChange: (change: Record<string, unknown>) => void;
  onMove: (by: -1 | 1) => void;
  onMoveToGroup: (group: number) => void;
}) {
  const entity = states.find((e) => e.entity_id === card.entity);
  const size = sizeOf(card);
  const note = card.type === "markdown";
  const number = (key: string) => (
    <Field label={title(key)}>
      <Input type="number" value={String(card[key] ?? "")}
             onChange={(_, d) => onChange({ [key]: d.value === "" ? null : Number(d.value) })} />
    </Field>
  );
  return (
    <>
      <h2>{nameOf(card, states)}</h2>
      {card.type === "button" && <ButtonName card={card} onChange={(name) => onChange({ name })} />}
      {(card.type === "tile" || card.type === "gauge" || card.type === "entities") && (
        <Field label="Label">
          <Input value={String(card.label ?? "")} placeholder={entity?.name} onChange={(_, d) => onChange({ label: d.value })} />
        </Field>
      )}
      {note && (
        <Field label="Text">
          <Textarea rows={5} value={String(card.content ?? "")} onChange={(_, d) => {
            // a note must keep its content key, even empty
            onChange({ content: d.value || " " });
          }} />
        </Field>
      )}
      {(card.type === "tile" || card.type === "gauge") && <ShowsAs card={card} entity={entity} onChange={onChange} />}
      {card.type === "gauge" && <div className="row start">{number("min")}{number("max")}</div>}
      {card.type === "entities" && <Items card={card} states={states} onChange={(entities) => onChange({ entities })} />}
      {card.type === "button" && (
        <Switch label="Ask before running" checked={Boolean(card.confirm)}
                onChange={(_, d) => onChange({ confirm: d.checked || null })} />
      )}
      {!note && (
        <>
          <Field label="Icon">
            <Select value={String(card.icon ?? "")} onChange={(_, d) => onChange({ icon: d.value })}>
              <option value="">None</option>
              {Object.keys(ICONS).map((i) => <option key={i} value={i}>{title(i)}</option>)}
            </Select>
          </Field>
          <Field label="Colour">
            <Select value={String(card.color ?? "")} onChange={(_, d) => onChange({ color: d.value })}>
              <option value="">Default</option>
              {COLORS.map((c) => <option key={c} value={c}>{title(c)}</option>)}
            </Select>
          </Field>
        </>
      )}
      <Field label="Size">
        <Select value={size} onChange={(_, d) => onChange(SIZES[d.value as keyof typeof SIZES])}>
          {Object.entries(SIZE_NAMES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          {size === "custom" && <option value="custom" disabled>Custom</option>}
        </Select>
      </Field>
      <MoveButtons canEarlier={index > 0} canLater={index < (groups[group]?.cards?.length ?? 0) - 1} onMove={onMove} />
      {groups.length > 1 && (
        <Field label="Move to group">
          <Select value={String(group)} onChange={(_, d) => onMoveToGroup(Number(d.value))}>
            {groups.map((g, i) => <option key={i} value={i}>{g.title || "Untitled group"}</option>)}
          </Select>
        </Field>
      )}
    </>
  );
}

export function GroupSettings({ group, index, count, onRename, onMove, onRemove }: {
  group: DraftGroup;
  index: number;
  count: number;
  onRename: (title: string) => void;
  onMove: (by: -1 | 1) => void;
  onRemove: () => void;
}) {
  return (
    <>
      <h2>{group.title || "Untitled group"}</h2>
      <Field label="Group name">
        <Input value={group.title} onChange={(_, d) => onRename(d.value)} />
      </Field>
      <MoveButtons canEarlier={index > 0} canLater={index < count - 1} onMove={onMove} />
      <div><Button onClick={onRemove}>Remove group</Button></div>
    </>
  );
}
