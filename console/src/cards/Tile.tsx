import { LockClosedRegular } from "@fluentui/react-icons";
import { useMutation } from "@tanstack/react-query";
import { api, message } from "../api/client";
import type { EntityView } from "../api/types";
import { isFull, roomText, stateText, useLiveState } from "./entity";

/** One device: the state in big type. Locked devices show only that they exist. */
export function Tile({ entity, tapAction = "none", row = false }: {
  entity: EntityView;
  tapAction?: "toggle" | "none";
  row?: boolean;
}) {
  const { state, attributes } = useLiveState(entity);
  const toggle = useMutation({
    mutationFn: () => api.post(`/entities/${encodeURIComponent(entity.entity_id)}/commands/toggle`),
  });
  const cls = `tile${row ? " row" : ""}`;
  const room = roomText(entity.area_id);

  if (!isFull(entity)) {
    return (
      <div className={`${cls} locked`}>
        <span className="tile-name">{entity.name}</span>
        {room && <span className="tile-room">{room}</span>}
        <span className="tile-state">
          <LockClosedRegular aria-hidden /> Restricted
        </span>
      </div>
    );
  }

  const body = (
    <>
      <span className="tile-name">{entity.name}</span>
      {room && <span className="tile-room">{room}</span>}
      <span className="tile-state">{stateText(state, attributes)}</span>
      {toggle.isError && (
        <span className="tile-error" role="alert">
          {message(toggle.error)}
        </span>
      )}
    </>
  );
  if (tapAction !== "toggle") return <div className={cls}>{body}</div>;
  return (
    <button
      type="button"
      className={`${cls}${state === "on" || state === "open" ? " active" : ""}`}
      aria-pressed={state === "on" || state === "open"}
      disabled={toggle.isPending}
      onClick={() => toggle.mutate()}
    >
      {body}
    </button>
  );
}

export function Entities({ entities }: { entities: EntityView[] }) {
  return (
    <ul className="entities">
      {entities.map((e) => (
        <li key={e.entity_id}>
          <Tile entity={e} row />
        </li>
      ))}
    </ul>
  );
}
