import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { expectAccessible } from "../../test/axe";
import { mockApi, renderWith, setNarrow } from "../../test/render";
import { Builder } from "./Builder";
import { type Draft, parseDraft } from "./model";

afterEach(() => vi.unstubAllGlobals());
beforeEach(() => setNarrow(false));

const entity = (entity_id: string, name: string, capability: string, state: string, attributes = {}) => ({
  entity_id, name, area_id: null, capability, state, attributes, last_changed: null });

const STATES = [
  entity("switch.left", "Left fan", "switch", "on"),
  entity("switch.lamp", "Office Lamp", "switch", "off"),
  entity("lock.door", "Front door", "lock", "locked"),
  entity("sensor.load", "UPS load", "sensor", "38", { unit: "%" }),
  entity("sensor.mode", "Mode", "sensor", "eco"),
  { entity_id: "switch.hidden", name: "Hidden", area_id: null, restricted: true },
];

const ROUTES = {
  "GET /states": STATES,
  "GET /automations": [{ id: "dusk", name: "Porch at dusk", allowed: true },
                       { id: "nope", name: "Not yours", allowed: false }],
  "GET /sequences": [{ id: "night", name: "Goodnight", allowed: true }],
  "GET /scripts": [{ file: "backup.sh", name: "Backup", allowed: true, runnable: true },
                   { file: "ask.sh", name: "Needs input", allowed: true, runnable: false }],
};

const YAML = `dashboard:
  title: Home
  views:
    - id: main
      title: Main
      sections:
        - title: Bedroom
          cards:
            - { type: tile, entity: switch.left, w: 5, h: 3 }
            - { type: tile, entity: sensor.load, tap_action: none }
        - title: Office
          cards:
            - { type: tile, entity: switch.hidden }
            - { type: button, name: Go, action: automation.dusk }
`;

const current: { draft?: Draft } = {};

function Harness({ start }: { start: Draft }) {
  const [draft, setDraft] = useState(start);
  return <Builder draft={draft} onChange={(d) => {
    current.draft = d;
    setDraft(d);
  }} />;
}

function show(routes: Record<string, unknown> = {}, text = YAML) {
  const calls = mockApi({ ...ROUTES, ...routes });
  const parsed = parseDraft(text);
  if (!("draft" in parsed)) throw new Error(parsed.reason);
  current.draft = parsed.draft;
  const view = renderWith(<Harness start={parsed.draft} />);
  return { calls, view };
}

const group = (i: number) => current.draft?.dashboard.views?.[0]?.sections?.[i];
const announced = (text: string) => expect(screen.getByText(text)).toHaveClass("sr-only");
const names = (i: number) => (group(i)?.cards ?? []).map((c) => c.entity ?? c.name ?? c.type);
const select = async (name: string) => userEvent.click(await screen.findByRole("button", { name: `Select ${name}` }));

describe("the builder", () => {
  it("adds a device to the selected group with its Add button", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Select group Bedroom" }));
    await userEvent.click(await screen.findByRole("button", { name: "Add Office Lamp" }));
    expect(names(0)).toEqual(["switch.left", "sensor.load", "switch.lamp"]);
    expect(group(0)?.cards?.at(-1)).toMatchObject({ tap_action: "toggle" });
    announced("Office Lamp added to Bedroom.");
  });

  it("adds to the last group when none is selected", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Add Goodnight" }));
    expect(names(1).at(-1)).toBe("Goodnight");
  });

  it("makes a group when there are none", async () => {
    show({}, "dashboard:\n  title: Gate\n");
    await userEvent.click(await screen.findByRole("button", { name: "Add Left fan" }));
    expect(group(0)).toMatchObject({ title: "Main" });
    expect(names(0)).toEqual(["switch.left"]);
  });

  it("hides what you can't use", async () => {
    show();
    await screen.findByRole("button", { name: "Add Left fan" });
    await screen.findByRole("button", { name: "Add Backup" });
    expect(screen.queryByRole("button", { name: "Add Hidden" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Not yours" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Needs input" })).not.toBeInTheDocument();
  });

  it("still works when a list is refused", async () => {
    show({ "GET /scripts": [403, { detail: "No." }] });
    await screen.findByRole("button", { name: "Add Left fan" });
    expect(screen.queryByRole("heading", { name: "Scripts" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Devices" })).toBeInTheDocument();
  });

  it("searches across every list", async () => {
    show();
    await screen.findByRole("button", { name: "Add Left fan" });
    await userEvent.type(screen.getByRole("textbox", { name: "Search what you can add" }), "good");
    expect(await screen.findByRole("button", { name: "Add Goodnight" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Left fan" })).not.toBeInTheDocument();
  });

  it("selects a tile by keyboard", async () => {
    show();
    (await screen.findByRole("button", { name: "Select UPS load" })).focus();
    await userEvent.keyboard("{Enter}");
    expect(screen.getByLabelText("Label")).toHaveAttribute("placeholder", "UPS load");
  });

  it("never switches or runs anything from the canvas", async () => {
    const { calls } = show();
    await select("Left fan");
    await select("Go");
    expect(screen.getByRole("button", { name: "Go" }).closest("[inert]")).not.toBeNull();
    expect(screen.getByRole("button", { name: /Left fan/, pressed: true }).closest("[inert]")).not.toBeNull();
    expect(calls.filter((c) => c.method !== "GET")).toEqual([]);
  });

  it("moves a tile with the Move controls and announces it", async () => {
    show();
    await select("UPS load");
    await userEvent.click(screen.getByRole("button", { name: "Move earlier" }));
    expect(names(0)).toEqual(["sensor.load", "switch.left"]);
    announced("UPS load moved.");
    expect(screen.getByRole("button", { name: "Move earlier" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Move later" }));
    expect(names(0)).toEqual(["switch.left", "sensor.load"]);
  });

  it("moves a tile to another group", async () => {
    show();
    await select("UPS load");
    await userEvent.selectOptions(screen.getByLabelText("Move to group"), "Office");
    expect(names(0)).toEqual(["switch.left"]);
    expect(names(1)).toEqual(["switch.hidden", "Go", "sensor.load"]);
    announced("UPS load moved to Office.");
  });

  function drag(from: Element, to: Element) {
    const store = new Map<string, string>();
    const dataTransfer = {
      setData: (k: string, v: string) => store.set(k, v), getData: (k: string) => store.get(k) ?? "",
      get types() { return [...store.keys()]; }, effectAllowed: "", dropEffect: "",
    };
    fireEvent.dragStart(from, { dataTransfer });
    fireEvent.dragOver(to, { dataTransfer });
    fireEvent.drop(to, { dataTransfer });
  }

  it("moves a tile by dragging", async () => {
    show();
    const tile = (await screen.findByRole("button", { name: "Select UPS load" })).closest("[draggable]")!;
    const onto = screen.getByRole("button", { name: "Select Go" }).closest("[draggable]")!;
    drag(tile, onto);
    expect(names(1)).toEqual(["switch.hidden", "sensor.load", "Go"]);
  });

  it("a moved tile keeps showing its own state", async () => {
    show({}, `dashboard:
  title: A
  views:
    - id: m
      title: M
      sections:
        - title: S
          cards:
            - { type: tile, entity: switch.left }
            - { type: tile, entity: switch.lamp }
`);
    await select("Office Lamp");
    await userEvent.click(screen.getByRole("button", { name: "Move earlier" }));
    const tiles = [...document.querySelectorAll(".builder-tile")].map((t) => t.textContent);
    expect(tiles[0]).toContain("Office LampOff");
    expect(tiles[1]).toContain("Left fanOn");
  });

  it("drags a tile later within its group", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Add Goodnight" }));
    const first = screen.getByRole("button", { name: "Select Hidden" }).closest("[draggable]")!;
    const onto = screen.getByRole("button", { name: "Select Goodnight" }).closest("[draggable]")!;
    drag(first, onto);
    expect(names(1)).toEqual(["Go", "Goodnight", "switch.hidden"]);
  });

  it("swaps a tile with its right-hand neighbour by dragging", async () => {
    show();
    const first = (await screen.findByRole("button", { name: "Select Left fan" })).closest("[draggable]")!;
    drag(first, screen.getByRole("button", { name: "Select UPS load" }).closest("[draggable]")!);
    expect(names(0)).toEqual(["sensor.load", "switch.left"]);
  });

  it("adds by dragging from the list", async () => {
    show();
    const row = (await screen.findByRole("button", { name: "Add Office Lamp" })).closest("[draggable]")!;
    drag(row, screen.getByRole("region", { name: "Bedroom" }));
    expect(names(0)).toEqual(["switch.left", "sensor.load", "switch.lamp"]);
  });

  it("reorders groups by dragging", async () => {
    show();
    const head = (await screen.findByRole("button", { name: "Select group Office" })).closest("[draggable]")!;
    drag(head, screen.getByRole("button", { name: "Select group Bedroom" }).closest("[draggable]")!);
    expect(group(0)?.title).toBe("Office");
  });

  it("ignores a drop of something else", async () => {
    show();
    const region = await screen.findByRole("region", { name: "Bedroom" });
    fireEvent.drop(region, { dataTransfer: { getData: () => "", types: [] } });
    expect(names(0)).toEqual(["switch.left", "sensor.load"]);
  });

  it("removes a tile and clears its settings", async () => {
    show();
    await select("UPS load");
    await userEvent.click(screen.getByRole("button", { name: "Remove UPS load" }));
    expect(names(0)).toEqual(["switch.left"]);
    expect(screen.queryByLabelText("Label")).not.toBeInTheDocument();
  });

  it("keeps the selection on the same tile when an earlier one goes", async () => {
    show();
    await select("UPS load");
    await userEvent.click(screen.getByRole("button", { name: "Remove Left fan" }));
    expect(screen.getByLabelText("Label")).toHaveAttribute("placeholder", "UPS load");
  });

  it("renames, moves and removes a group", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Select group Office" }));
    const name = screen.getByLabelText("Group name");
    await userEvent.clear(name);
    await userEvent.type(name, "Study");
    expect(group(1)?.title).toBe("Study");
    await userEvent.click(screen.getByRole("button", { name: "Move earlier" }));
    expect(group(0)?.title).toBe("Study");
    await userEvent.click(screen.getByRole("button", { name: "Remove group" }));
    expect(current.draft?.dashboard.views?.[0]?.sections?.map((s) => s.title)).toEqual(["Bedroom"]);
  });

  it("adds a group and selects it", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Add group" }));
    expect(group(2)).toMatchObject({ title: "New group" });
    expect(screen.getByLabelText("Group name")).toHaveValue("New group");
  });

  it("changes label, icon, colour and size", async () => {
    show();
    await select("UPS load");
    await userEvent.type(screen.getByLabelText("Label"), "Load");
    await userEvent.selectOptions(screen.getByLabelText("Icon"), "battery");
    await userEvent.selectOptions(screen.getByLabelText("Colour"), "Green");
    await userEvent.selectOptions(screen.getByLabelText("Size"), "Wide");
    expect(group(0)?.cards?.[1]).toMatchObject({ label: "Load", icon: "battery", color: "green", w: 6, h: 1 });
    await userEvent.selectOptions(screen.getByLabelText("Colour"), "Default");
    expect(group(0)?.cards?.[1]).not.toHaveProperty("color");
  });

  it("keeps a run button's name when it's cleared", async () => {
    show();
    await select("Go");
    await userEvent.clear(screen.getByLabelText("Label"));
    expect(group(1)?.cards?.[1]).toMatchObject({ name: "Go" });
    await userEvent.type(screen.getByLabelText("Label"), "Run");
    expect(group(1)?.cards?.[1]).toMatchObject({ name: "Run" });
  });

  it("shows a size from YAML as Custom and keeps it", async () => {
    show();
    await select("Left fan");
    expect(screen.getByLabelText("Size")).toHaveValue("custom");
    await userEvent.type(screen.getByLabelText("Label"), "Fan");
    expect(group(0)?.cards?.[0]).toMatchObject({ w: 5, h: 3 });
  });

  it("offers Toggle only for what switches, and Gauge only for numbers", async () => {
    show({}, `dashboard:
  title: A
  views:
    - id: m
      title: M
      sections:
        - title: S
          cards:
            - { type: tile, entity: switch.left }
            - { type: tile, entity: sensor.load, tap_action: none }
            - { type: tile, entity: sensor.mode, tap_action: none }
`);
    const options = () => within(screen.getByLabelText("Shows as")).getAllByRole("option").map((o) => o.textContent);
    await select("Left fan");
    expect(options()).toEqual(["Toggle", "Status only"]);
    await select("UPS load");
    expect(options()).toEqual(["Status only", "Gauge"]);
    await select("Mode");
    expect(options()).toEqual(["Status only"]);
  });

  it("turns a sensor into a gauge and back", async () => {
    show();
    await select("UPS load");
    await userEvent.selectOptions(screen.getByLabelText("Shows as"), "Gauge");
    expect(group(0)?.cards?.[1]).toMatchObject({ type: "gauge" });
    expect(group(0)?.cards?.[1]).not.toHaveProperty("tap_action");
    await userEvent.type(screen.getByLabelText("Max"), "50");
    expect(group(0)?.cards?.[1]).toMatchObject({ max: 50 });
    await userEvent.selectOptions(screen.getByLabelText("Shows as"), "Status only");
    expect(group(0)?.cards?.[1]).toMatchObject({ type: "tile", tap_action: "none" });
    expect(group(0)?.cards?.[1]).not.toHaveProperty("max");
  });

  it("builds a list tile", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Add List tile" }));
    await select("List tile");
    await userEvent.selectOptions(screen.getByLabelText("Add an item"), "UPS load");
    await userEvent.selectOptions(screen.getByLabelText("Add an item"), "Left fan");
    expect(group(1)?.cards?.at(-1)).toMatchObject({ entities: ["sensor.load", "switch.left"] });
    await userEvent.click(screen.getByRole("button", { name: "Move Left fan up" }));
    expect(group(1)?.cards?.at(-1)).toMatchObject({ entities: ["switch.left", "sensor.load"] });
    await userEvent.click(screen.getByRole("button", { name: "Take out Left fan" }));
    expect(group(1)?.cards?.at(-1)).toMatchObject({ entities: ["sensor.load"] });
  });

  it("writes a text note and sets Ask before running", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Add Text note" }));
    await select("Text note");
    await userEvent.type(screen.getByLabelText("Text"), "Hello");
    expect(group(1)?.cards?.at(-1)).toMatchObject({ content: "Hello" });
    expect(screen.queryByLabelText("Icon")).not.toBeInTheDocument();
    await select("Go");
    await userEvent.click(screen.getByRole("switch", { name: "Ask before running" }));
    expect(group(1)?.cards?.[1]).toMatchObject({ confirm: true });
  });

  it("keeps a restricted tile locked but movable", async () => {
    show();
    await screen.findByRole("button", { name: "Add Left fan" });
    await select("Hidden");
    await waitFor(() => expect(screen.getByText("Restricted")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Move later" }));
    expect(names(1)).toEqual(["Go", "switch.hidden"]);
  });

  it("folds the side panels into drawers on a narrow screen", async () => {
    setNarrow(true);
    show();
    await screen.findByRole("button", { name: "Select Left fan" });
    expect(screen.queryByRole("button", { name: "Add Left fan" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Settings" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    await userEvent.click(await screen.findByRole("button", { name: "Add Office Lamp" }));
    expect(names(1).at(-1)).toBe("switch.lamp");
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    await select("UPS load");
    await userEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(await screen.findByLabelText("Label")).toBeInTheDocument();
  });

  it("passes an accessibility check", async () => {
    const { view } = show();
    await select("UPS load");
    await expectAccessible(view.container);
  });
});
