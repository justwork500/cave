import { Button, Tab, TabList } from "@fluentui/react-components";
import { AddRegular, DismissRegular, ReOrderDotsVerticalRegular } from "@fluentui/react-icons";
import type { DragEvent } from "react";
import type { EntityView } from "../../api/types";
import { CardBody } from "../../pages/Dashboard";
import { type Draft, type Spot, nameOf, viewCard } from "./model";
import { DRAG_TYPE } from "./Palette";

export type Selected = { group: number; card?: number } | null;
export type Target = { group: number; card?: number };

export function Canvas({ draft, view, states, selected, onView, onSelect, onDrop, onRemove, onAddGroup }: {
  draft: Draft;
  view: number;
  states: EntityView[];
  selected: Selected;
  onView: (view: number) => void;
  onSelect: (s: Selected) => void;
  /** What was dragged, as JSON, and where it landed. */
  onDrop: (data: string, target: Target) => void;
  onRemove: (at: Spot) => void;
  onAddGroup: () => void;
}) {
  const views = draft.dashboard.views ?? [];
  const groups = views[view]?.sections ?? [];

  const start = (e: DragEvent, data: unknown) => {
    e.stopPropagation();
    e.dataTransfer.setData(DRAG_TYPE, JSON.stringify(data));
    e.dataTransfer.effectAllowed = "copyMove";
  };
  const target = (where: Target) => ({
    onDragOver: (e: DragEvent) => e.preventDefault(),
    onDrop: (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      onDrop(e.dataTransfer.getData(DRAG_TYPE), where);
    },
  });

  return (
    <div className="builder-canvas">
      {views.length > 1 && (
        <TabList selectedValue={view} onTabSelect={(_, t) => onView(Number(t.value))}>
          {views.map((v, i) => <Tab key={v.id} value={i}>{v.title}</Tab>)}
        </TabList>
      )}
      {groups.map((g, group) => (
        <section
          key={group}
          className={`builder-group${selected?.group === group && selected.card === undefined ? " selected" : ""}`}
          aria-label={g.title || "Untitled group"}
          {...target({ group })}
        >
          <header draggable onDragStart={(e) => start(e, { group })} {...target({ group })}>
            <ReOrderDotsVerticalRegular aria-hidden />
            <button type="button" aria-label={`Select group ${g.title}`} onClick={() => onSelect({ group })}>
              {g.title || "Untitled group"}
            </button>
          </header>
          {(g.cards ?? []).length === 0 && <p className="muted">Drag something here, or use its Add button.</p>}
          <div className="grid">
            {(g.cards ?? []).map((card, i) => {
              const name = nameOf(card, states);
              const shown = viewCard(card, states);
              const at = { view, group, card: i };
              const isSelected = selected?.group === group && selected.card === i;
              return (
                <div
                  key={`${i}:${String(card.entity ?? card.action ?? card.type)}`} // a tile keeps its own live state
                  draggable
                  className={`card card-${card.type} builder-tile${isSelected ? " selected" : ""}${
                    shown.color ? ` tint-${shown.color}` : ""}`}
                  style={{ gridColumn: `span ${shown.w}`, gridRow: `span ${shown.h}` }}
                  onDragStart={(e) => start(e, { spot: at })}
                  {...target({ group, card: i })}
                >
                  {/* inert: nothing on the canvas switches a device or starts a run */}
                  <div inert><CardBody card={shown} section={g.title} /></div>
                  <button type="button" className="builder-select" aria-label={`Select ${name}`} aria-pressed={isSelected}
                          onClick={() => onSelect({ group, card: i })} />
                  <Button className="builder-remove" size="small" icon={<DismissRegular />} aria-label={`Remove ${name}`}
                          onClick={() => onRemove(at)} />
                </div>
              );
            })}
          </div>
        </section>
      ))}
      <div><Button icon={<AddRegular />} onClick={onAddGroup}>Add group</Button></div>
    </div>
  );
}
