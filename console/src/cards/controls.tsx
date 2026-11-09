import { Button, Dropdown, Option, Slider } from "@fluentui/react-components";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, message } from "../api/client";
import type { EntityView } from "../api/types";
import { isFull, useLiveState } from "./entity";

const num = (v: unknown, fallback: number) => (typeof v === "number" && Number.isFinite(v) ? v : fallback);
const list = (v: unknown) => (Array.isArray(v) ? v.map(String) : []);

/** A slider that sends its value once, when the person lets go. */
function Level({ label, min, max, step, start, unit, send }: {
  label: string; min: number; max: number; step: number; start: number; unit?: string;
  send: (value: number) => void;
}) {
  const [value, setValue] = useState(start);
  const [sent, setSent] = useState(start);
  const release = () => {
    if (value === sent) return;
    setSent(value);
    send(value);
  };
  return (
    <div className="tile-control">
      <Slider
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(_e, d) => setValue(d.value)}
        onPointerUp={release}
        onKeyUp={release}
      />
      <span aria-hidden="true">{value}{unit ? ` ${unit}` : ""}</span>
    </div>
  );
}

function Choice({ label, options, selected, send }: {
  label: string; options: string[]; selected: string; send: (option: string) => void;
}) {
  return (
    <Dropdown
      aria-label={label}
      value={selected}
      selectedOptions={[selected]}
      onOptionSelect={(_e, d) => d.optionValue && send(d.optionValue)}
    >
      {options.map((o) => <Option key={o}>{o}</Option>)}
    </Dropdown>
  );
}

/** Media, number and choice controls for a tile. Restricted devices get none. */
export function Controls({ entity }: { entity: EntityView }) {
  const { state, attributes } = useLiveState(entity);
  const send = useMutation({
    mutationFn: (c: { command: string; args?: Record<string, unknown> }) =>
      api.post(`/entities/${encodeURIComponent(entity.entity_id)}/commands/${c.command}`, c.args),
  });
  if (!isFull(entity)) return null;
  const run = (command: string, args?: Record<string, unknown>) => send.mutate({ command, args });

  let controls = null;
  if (entity.capability === "media_player") {
    const sources = list(attributes.sources);
    controls = (
      <>
        <Button onClick={() => run(state === "off" ? "turn_on" : "turn_off")}>Power</Button>
        {(state === "playing" || state === "paused") && (
          <Button onClick={() => run(state === "playing" ? "pause" : "play")}>
            {state === "playing" ? "Pause" : "Play"}
          </Button>
        )}
        {typeof attributes.volume === "number" && (
          <Level label="Volume" min={0} max={100} step={1} start={attributes.volume}
                 send={(level) => run("volume_set", { level })} />
        )}
        {sources.length > 0 && (
          <Choice label="Source" options={sources} selected={String(attributes.source ?? "")}
                  send={(source) => run("select_source", { source })} />
        )}
      </>
    );
  } else if (entity.capability === "number") {
    controls = (
      <Level label={entity.name} min={num(attributes.min, 0)} max={num(attributes.max, 100)}
             step={num(attributes.step, 1) || 1} start={num(Number(state), 0)}
             unit={typeof attributes.unit === "string" ? attributes.unit : undefined}
             send={(value) => run("set_value", { value })} />
    );
  } else if (entity.capability === "select") {
    controls = (
      <Choice label={entity.name} options={list(attributes.options)} selected={state ?? ""}
              send={(option) => run("select_option", { option })} />
    );
  }
  if (!controls) return null;
  return (
    <div className="tile-controls">
      {controls}
      {send.isError && <span className="tile-error" role="alert">{message(send.error)}</span>}
    </div>
  );
}
