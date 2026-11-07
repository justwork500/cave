import { readFileSync } from "node:fs";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import schema from "../../../schemas/dashboard.json";
import { contrast } from "../app/theme";
import type { ButtonCard, FullEntity, GaugeCard } from "../api/types";
import { mockApi, renderWith } from "../test/render";
import { ActionButton } from "./Button";
import { Gauge } from "./Gauge";
import { COLORS, ICONS } from "./look";
import { Entities, Tile } from "./Tile";

afterEach(() => vi.unstubAllGlobals());

const lamp: FullEntity = { entity_id: "switch.lamp", name: "Office Lamp", area_id: null, capability: "switch",
                           state: "on", attributes: {}, last_changed: null };

function enumOf(field: "icon" | "color"): string[] {
  const options = (schema.$defs.TileCard.properties[field] as { anyOf: { enum?: string[] }[] }).anyOf;
  return options.find((o) => o.enum)?.enum ?? [];
}

function tokens(selector: string): Record<string, string> {
  const css = readFileSync("src/app/app.css", "utf-8"); // vitest empties CSS imports, even ?raw
  const start = css.indexOf(`${selector} {`);
  const block = css.slice(start, css.indexOf("\n}", start));
  return Object.fromEntries([...block.matchAll(/--([a-z-]+):\s*(#[0-9a-f]{6})/g)].map((m) => [m[1], m[2]]));
}

describe("card looks", () => {
  it("offers exactly the icons and colours the core accepts", () => {
    expect(Object.keys(ICONS).sort()).toEqual(enumOf("icon").sort());
    expect([...COLORS].sort()).toEqual(enumOf("color").sort());
  });

  it("shows a tile's label instead of the device name", () => {
    renderWith(<Tile entity={lamp} label="Desk" />);
    expect(screen.getByText("Desk")).toBeInTheDocument();
    expect(screen.queryByText("Office Lamp")).not.toBeInTheDocument();
  });

  it("shows the card's icon", () => {
    const { container } = renderWith(<Tile entity={lamp} icon="wind" />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("names a gauge and a list by their labels", () => {
    const gauge = { entity: lamp, min: 0, max: 100, severity: null, label: "Load" } as unknown as GaugeCard;
    renderWith(<Gauge card={gauge} />);
    expect(screen.getByRole("meter", { name: "Load" })).toBeInTheDocument();
    renderWith(<Entities entities={[lamp]} label="Office" />);
    expect(screen.getByRole("list", { name: "Office" })).toBeInTheDocument();
  });

  it("runs a script button by its whole file name", async () => {
    const calls = mockApi({ "POST /scripts/backup-photos.sh/run": { result: {} } });
    const card = { name: "Back up", action: "script.backup-photos.sh", allowed: true, confirm: null } as ButtonCard;
    renderWith(<ActionButton card={card} />);
    await userEvent.click(screen.getByRole("button", { name: "Back up" }));
    await waitFor(() => expect(calls.at(-1)).toMatchObject({ method: "POST", path: "/scripts/backup-photos.sh/run" }));
  });

  it.each([[".root"], ['.root[data-theme="dark"]']])("%s: every colour keeps its text readable", (selector) => {
    const t = tokens(selector);
    for (const c of COLORS) {
      const [off, on, ink] = [t[c], t[`${c}-on`], t[`${c}-ink`]] as [string, string, string];
      expect(contrast(t.text as string, off)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(t.muted as string, off)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(ink, on)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(t.muted as string, on)).toBeGreaterThanOrEqual(4.5);
    }
  });
});
