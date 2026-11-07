import {
  Button, DrawerBody, DrawerFooter, DrawerHeader, DrawerHeaderTitle, OverlayDrawer, Spinner,
} from "@fluentui/react-components";
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { api } from "../../api/client";
import type { EntityView } from "../../api/types";
import { useFolded } from "../../app/live";
import { Canvas, type Selected, type Target } from "./Canvas";
import {
  type Draft, type DraftCard, type Source, type Spot, addCard, addGroup, afterRemove, cardFor, moveCard, moveGroup,
  nameOf, removeCard, removeGroup, renameGroup, updateCard,
} from "./model";
import { Palette } from "./Palette";
import { GroupSettings, TileSettings } from "./Settings";

interface Dragged {
  source?: Source;
  spot?: Spot;
  group?: number;
}

function read(data: string): Dragged | null {
  try {
    return data ? (JSON.parse(data) as Dragged) : null;
  } catch {
    return null;
  }
}

/** The three panels. Holds only what's selected: the draft belongs to the page, so YAML and Visual stay one document. */
export function Builder({ draft, onChange }: { draft: Draft; onChange: (d: Draft) => void }) {
  const states = useQuery({ queryKey: ["states"], queryFn: () => api.get<EntityView[]>("/states") });
  const all = states.data ?? [];
  const [view, setView] = useState(0);
  const [selected, setSelected] = useState<Selected>(null);
  const [status, setStatus] = useState("");
  const folded = useFolded();
  const [drawer, setDrawer] = useState<"add" | "settings" | null>(null);

  const groups = draft.dashboard.views?.[view]?.sections ?? [];
  const cardsIn = (g: number) => groups[g]?.cards ?? [];
  const label = (card: DraftCard | undefined) => (card ? nameOf(card, all) : "");
  const groupName = (g: number, d: Draft = draft) => d.dashboard.views?.[view]?.sections?.[g]?.title || "the new group";

  const add = (source: Source, to?: Target) => {
    let next = draft;
    let group = to?.group ?? selected?.group ?? groups.length - 1;
    if (groups.length === 0) {
      next = addGroup(next, view, "Main");
      group = 0;
    }
    const card = cardFor(source);
    next = addCard(next, view, group, card);
    if (to?.card !== undefined) {
      next = moveCard(next, { view, group, card: cardsIn(group).length }, { view, group, card: to.card });
    }
    onChange(next);
    setStatus(`${label(card)} added to ${groupName(group, next)}.`);
  };

  const move = (from: Spot, to: Spot, words: string) => {
    onChange(moveCard(draft, from, to));
    setSelected({ group: to.group, card: to.card });
    setStatus(`${label(cardsIn(from.group)[from.card])} moved${words}.`);
  };

  const shiftGroup = (from: number, to: number) => {
    onChange(moveGroup(draft, view, from, to));
    setSelected({ group: to });
    setStatus(`${groups[from]?.title ?? "Group"} moved.`);
  };

  const drop = (data: string, target: Target) => {
    const what = read(data);
    if (what?.source) add(what.source, target);
    else if (what?.group !== undefined) {
      if (what.group !== target.group) shiftGroup(what.group, target.group);
    } else if (what?.spot) {
      const from = what.spot;
      const same = from.group === target.group;
      const end = cardsIn(target.group).length - (same ? 1 : 0);
      const card = target.card ?? end; // it takes the place of the tile it's dropped on
      if (same && card === from.card) return;
      move(from, { view, group: target.group, card }, same ? "" : ` to ${groupName(target.group)}`);
    }
  };

  const remove = (at: Spot) => {
    const name = label(cardsIn(at.group)[at.card]);
    onChange(removeCard(draft, at));
    const spot = selected?.card === undefined ? null : { view, group: selected.group, card: selected.card };
    const kept = afterRemove(spot, at);
    setSelected(kept ? { group: kept.group, card: kept.card } : selected?.card === undefined ? selected : null);
    setStatus(`${name} removed.`);
  };

  const newGroup = () => {
    onChange(addGroup(draft, view, "New group"));
    setSelected({ group: groups.length });
    setStatus("Group added.");
  };

  if (states.isPending) return <Spinner label="Loading" />; // tiles read their state once, when first drawn

  const group = selected ? groups[selected.group] : undefined;
  const card = selected?.card !== undefined ? group?.cards?.[selected.card] : undefined;

  const panel = (which: "add" | "settings", title: string, body: ReactNode) => (folded ? (
    <OverlayDrawer position="end" open={drawer === which} onOpenChange={(_, d) => !d.open && setDrawer(null)}>
      <DrawerHeader><DrawerHeaderTitle>{title}</DrawerHeaderTitle></DrawerHeader>
      <DrawerBody>{body}</DrawerBody>
      <DrawerFooter><Button onClick={() => setDrawer(null)}>Done</Button></DrawerFooter>
    </OverlayDrawer>
  ) : body);

  return (
    <div className={`builder${folded ? " folded" : ""}`}>
      {folded && (
        <div className="row start">
          <Button appearance="primary" onClick={() => setDrawer("add")}>Add</Button>
          <Button disabled={!selected} onClick={() => setDrawer("settings")}>Settings</Button>
        </div>
      )}
      {panel("add", "Add to dashboard", <Palette states={all} onAdd={(s) => add(s)} />)}
      <Canvas
        draft={draft}
        view={view}
        states={all}
        selected={selected}
        onView={(v) => {
          setView(v);
          setSelected(null);
        }}
        onSelect={setSelected}
        onDrop={drop}
        onRemove={remove}
        onAddGroup={newGroup}
      />
      {panel("settings", "Settings", <aside className="builder-panel" aria-label="Settings">
        {selected && card && selected.card !== undefined ? (
          <TileSettings
            key={`${view}-${selected.group}-${selected.card}`}
            card={card}
            states={all}
            groups={groups}
            group={selected.group}
            index={selected.card}
            onChange={(change) => onChange(updateCard(draft, { view, group: selected.group, card: selected.card as number }, change))}
            onMove={(by) => {
              const from = { view, group: selected.group, card: selected.card as number };
              move(from, { ...from, card: from.card + by }, "");
            }}
            onMoveToGroup={(to) => move(
              { view, group: selected.group, card: selected.card as number },
              { view, group: to, card: cardsIn(to).length },
              ` to ${groupName(to)}`,
            )}
          />
        ) : selected && group ? (
          <GroupSettings
            group={group}
            index={selected.group}
            count={groups.length}
            onRename={(title) => onChange(renameGroup(draft, view, selected.group, title))}
            onMove={(by) => shiftGroup(selected.group, selected.group + by)}
            onRemove={() => {
              onChange(removeGroup(draft, view, selected.group));
              setSelected(null);
              setStatus(`${group.title} removed.`);
            }}
          />
        ) : (
          <p className="muted">Select a tile or group to change it.</p>
        )}
      </aside>)}
      <p className="sr-only" role="status">{status}</p>
    </div>
  );
}
