import { LockClosedRegular } from "@fluentui/react-icons";
import { useMutation } from "@tanstack/react-query";
import { api, message } from "../api/client";
import type { EntityView } from "../api/types";
import { isFull, roomText, stateText, useLiveState } from "./entity";
import { CardIcon } from "./look";

/** One device: the state in big type. Locked devices show only that they exist. */
const ACTIVE = new Set(["on", "open", "opening", "unlocked"]);

export function Tile({ entity, label, icon, tapAction = "none", row = false, section }: {
  entity: EntityView;
  /** Shown instead of the device's name, on this tile only. */
  label?: string | null;
  icon?: string | null;
  tapAction?: "toggle" | "none";
  row?: boolean;
  /** The section it sits in: its room isn't repeated when the section is that room. */
  section?: string;
}) {
  const { state, attributes } = useLiveState(entity);
  const toggle = useMutation({
    mutationFn: () => api.post(`/entities/${encodeURIComponent(entity.entity_id)}/commands/toggle`),
  });
  const cls = `tile${row ? " row" : ""}`;
  const roomName = roomText(entity.area_id);
  const room = section && roomName.toLowerCase() === section.toLowerCase() ? "" : roomName;
  const name = <span className="tile-name"><CardIcon name={icon} />{label || entity.name}</span>;

  if (!isFull(entity)) {
    return (
      <div className={`${cls} locked`}>
        {name}
        {room && <span className="tile-room">{room}</span>}
        <span className="tile-state">
          <LockClosedRegular aria-hidden /> Restricted
        </span>
      </div>
    );
  }

  const body = (
    <>
      {name}
      {room && <span className="tile-room">{room}</span>}
      <span className="tile-state">{stateText(state, attributes)}</span>
      {toggle.isError && (
        <span className="tile-error" role="alert">
          {message(toggle.error)}
        </span>
      )}
    </>
  );
  const on = ACTIVE.has(state ?? "");
  const look = `${cls}${on ? " on" : ""}${state === "unavailable" ? " unavailable" : ""}`;
  if (tapAction !== "toggle") return <div className={look}>{body}</div>;
  return (
    <button
      type="button"
      className={look}
      aria-pressed={on}
      disabled={toggle.isPending}
      onClick={() => toggle.mutate()}
    >
      {body}
      <span className="switch" aria-hidden="true" />
    </button>
  );
}

export function Entities({ entities, label, icon }: {
  entities: EntityView[];
  label?: string | null;
  icon?: string | null;
}) {
  return (
    <ul className="entities" aria-label={label || undefined}>
      {(label || icon) && <li className="entities-title" aria-hidden="true"><CardIcon name={icon} />{label}</li>}
      {entities.map((e) => (
        <li key={e.entity_id}>
          <Tile entity={e} row />
        </li>
      ))}
    </ul>
  );
}
