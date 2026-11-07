import { LockClosedRegular } from "@fluentui/react-icons";
import type { GaugeCard } from "../api/types";
import { isFull, stateText, useLiveState } from "./entity";
import { CardIcon } from "./look";

const LEVELS: Record<string, { label: string; colour: string }> = {
  green: { label: "Normal", colour: "#2e7d32" },
  yellow: { label: "Warning", colour: "#b26a00" },
  red: { label: "Critical", colour: "#c62828" },
};

/** The highest severity whose threshold the value has reached. */
export function level(value: number, severity: Record<string, number> | null) {
  const hit = Object.entries(severity ?? {}).filter(([, from]) => value >= from).sort((a, b) => b[1] - a[1])[0];
  return hit ? (LEVELS[hit[0]] ?? { label: hit[0], colour: "var(--colorBrandForeground1)" }) : null;
}

export function Gauge({ card }: { card: GaugeCard }) {
  const { state, attributes } = useLiveState(card.entity);
  const name = card.label || card.entity.name;
  const title = <span className="tile-name"><CardIcon name={card.icon} />{name}</span>;
  if (!isFull(card.entity)) {
    return (
      <div className="tile locked">
        {title}
        <span className="tile-state">
          <LockClosedRegular aria-hidden /> Restricted
        </span>
      </div>
    );
  }
  const value = Number(state);
  const known = state !== null && !Number.isNaN(value);
  const fraction = known ? Math.min(1, Math.max(0, (value - card.min) / (card.max - card.min || 1))) : 0;
  const sev = known ? level(value, card.severity) : null;
  // a half circle from the left (180°) to the right (0°), radius 40, centre (50, 50)
  const angle = Math.PI * (1 - fraction);
  const x = 50 + 40 * Math.cos(angle);
  const y = 50 - 40 * Math.sin(angle);
  const text = stateText(state, attributes);

  return (
    <div
      className="gauge"
      role="meter"
      aria-label={name}
      aria-valuemin={card.min}
      aria-valuemax={card.max}
      aria-valuenow={known ? value : undefined}
      aria-valuetext={sev ? `${text}, ${sev.label}` : text}
    >
      {title}
      <svg viewBox="0 0 100 56" aria-hidden="true">
        <path d="M10 50 A40 40 0 0 1 90 50" className="gauge-track" />
        {fraction > 0 && (
          <path
            d={`M10 50 A40 40 0 0 1 ${x.toFixed(2)} ${y.toFixed(2)}`}
            className="gauge-fill"
            style={sev ? { stroke: sev.colour } : undefined}
          />
        )}
      </svg>
      <span className="gauge-value">{text}</span>
      {sev && (
        <span className="gauge-level" style={{ borderColor: sev.colour }}>
          {sev.label}
        </span>
      )}
    </div>
  );
}
