import { screen, within } from "@testing-library/react";
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
