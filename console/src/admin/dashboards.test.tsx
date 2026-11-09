import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderWith } from "../test/render";
import { AutomationEditor } from "./Automations";
import { DashboardEditor, Dashboards } from "./Dashboards";

vi.mock("../editor/monaco", () => ({ loadMonaco: () => new Promise(() => undefined) }));
afterEach(() => vi.unstubAllGlobals());

const GATE = { name: "Gate", yaml: "dashboard:\n  title: Gate\n" };

function at(path: string) {
  return renderWith(
    <Routes>
      <Route path="/admin/dashboards" element={<Dashboards />} />
      <Route path="/admin/dashboards/:slug" element={<DashboardEditor />} />
      <Route path="/admin/automations" element={<p>Automation list</p>} />
      <Route path="/admin/automations/:kinds/:id" element={<AutomationEditor />} />
    </Routes>,
    path,
  );
}

const BOARD = `dashboard:
  title: Gate
  views:
    - id: main
      title: Main
      sections:
        - title: Doors
          cards: []
`;

const LISTS = {
  "GET /states": [{ entity_id: "switch.gate", name: "Gate light", area_id: null, capability: "switch", state: "off",
                    attributes: {}, last_changed: null }],
  "GET /automations": [], "GET /sequences": [], "GET /scripts": [],
};

function open(yaml: string, routes: Record<string, unknown> = {}) {
  const calls = mockApi({ ...LISTS, "GET /dashboards/gate": { name: "Gate", yaml }, ...routes });
  at("/admin/dashboards/gate");
  return calls;
}

const addLight = async () => userEvent.click(await screen.findByRole("button", { name: "Add Gate light" }));
const yamlBox = () => screen.findByRole("textbox", { name: "YAML" });

describe("visual and YAML", () => {
  it("opens in Visual", async () => {
    open(BOARD);
    expect(await screen.findByRole("tab", { name: "Visual", selected: true })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Add Gate light" })).toBeInTheDocument();
  });

  it("carries unsaved changes from Visual to YAML and back", async () => {
    open(BOARD);
    await addLight();
    await userEvent.click(screen.getByRole("tab", { name: "YAML" }));
    expect(((await yamlBox()) as HTMLTextAreaElement).value).toContain("switch.gate");
    await userEvent.click(screen.getByRole("tab", { name: "Visual" }));
    expect(await screen.findByRole("button", { name: "Select Gate light" })).toBeInTheDocument();
  });

  it("disables Visual with the reason when the YAML can't be used", async () => {
    open(BOARD);
    await screen.findByRole("button", { name: "Add Gate light" });
    await userEvent.click(screen.getByRole("tab", { name: "YAML" }));
    fireEvent.change(await yamlBox(), { target: { value: "title: nope\n" } });
    expect(screen.getByRole("tab", { name: "Visual" })).toBeDisabled();
    expect(screen.getByText("There's no dashboard in this YAML.")).toBeInTheDocument();
  });

  it("opens YAML it can't draw straight in YAML", async () => {
    open("dashboard: [");
    expect(await screen.findByRole("tab", { name: "YAML", selected: true })).toBeInTheDocument();
    expect(await yamlBox()).toHaveValue("dashboard: [");
  });

  it("warns before a visual change removes comments, and can stay in YAML", async () => {
    open(`# mine
${BOARD}`);
    await addLight();
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Remove the comments in this YAML?")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep editing in YAML" }));
    const text = ((await yamlBox()) as HTMLTextAreaElement).value;
    expect(text).toContain("# mine");
    expect(text).not.toContain("switch.gate");
  });

  it("goes ahead once you agree to remove comments", async () => {
    open(`# mine
${BOARD}`);
    await addLight();
    await userEvent.click(await screen.findByRole("button", { name: "Remove comments" }));
    expect(await screen.findByRole("button", { name: "Select Gate light" })).toBeInTheDocument();
  });

  it("saves the draft through the normal route", async () => {
    const calls = open(BOARD, { "PUT /dashboards/gate": { ok: true } });
    await addLight();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")).toBeDefined());
    expect((calls.find((c) => c.method === "PUT")?.body as { yaml: string }).yaml).toContain("switch.gate");
  });

  it("shows a save refusal and keeps the draft", async () => {
    open(BOARD, { "PUT /dashboards/gate": [403, { detail: "You can't save this." }] });
    await addLight();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("You can't save this.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select Gate light" })).toBeInTheDocument();
  });

  it("Discard goes back to the saved version", async () => {
    open(BOARD);
    await screen.findByRole("button", { name: "Add Gate light" });
    expect(screen.getByRole("button", { name: "Discard" })).toBeDisabled();
    await addLight();
    await userEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(await screen.findByRole("button", { name: "Add Gate light" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Select Gate light" })).not.toBeInTheDocument();
  });

  it("asks before closing with unsaved changes", async () => {
    open(BOARD);
    const closing = () => {
      const e = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(e);
      return e.defaultPrevented;
    };
    await screen.findByRole("button", { name: "Add Gate light" });
    expect(closing()).toBe(false);
    await addLight();
    expect(closing()).toBe(true);
  });
});

describe("dashboards", () => {
  it("creates a new dashboard from its name and opens it for editing", async () => {
    const calls = mockApi({
      "GET /dashboards": [],
      "PUT /dashboards/garage_tablet": { ok: true },
      "GET /dashboards/garage_tablet": { name: "Garage tablet", yaml: "dashboard:\n  title: Garage tablet\n" },
    });
    at("/admin/dashboards");
    await userEvent.type(await screen.findByRole("textbox", { name: "New dashboard name" }), "Garage tablet");
    await userEvent.click(screen.getByRole("button", { name: "Create dashboard" }));
    expect(await screen.findByRole("heading", { name: "Garage tablet" })).toBeInTheDocument();
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.query).toBe("?create=true");
    expect((put.body as { yaml: string }).yaml).toContain('title: "Garage tablet"');
    expect((put.body as { yaml: string }).yaml).toContain("cards: []");
  });

  it("deletes a dashboard only after you confirm", async () => {
    const calls = mockApi({ "GET /dashboards/gate": GATE, "DELETE /dashboards/gate": undefined, "GET /dashboards": [] });
    at("/admin/dashboards/gate");
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete dashboard" }));
    expect(await screen.findByRole("heading", { name: "Dashboards" })).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "DELETE").map((c) => c.path)).toEqual(["/dashboards/gate"]);
  });
});

describe("automations", () => {
  it("deletes an automation after you confirm", async () => {
    const calls = mockApi({
      "GET /automations/smoke": { name: "Smoke", yaml: "automation:\n  id: smoke\n" },
      "DELETE /automations/smoke": undefined,
    });
    at("/admin/automations/automations/smoke");
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete automation" }));
    expect(await screen.findByText("Automation list")).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "DELETE").map((c) => c.path)).toEqual(["/automations/smoke"]);
  });
});
