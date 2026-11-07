import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LiveContext } from "../app/live";
import { expectAccessible } from "../test/axe";
import { mockApi, renderWith, setNarrow } from "../test/render";
import { ConfigErrors } from "./ConfigErrors";
import { DashboardEditor } from "./Dashboards";
import { Networks } from "./Networks";
import { ScriptEditor } from "./Scripts";

vi.mock("../editor/monaco", () => ({ loadMonaco: () => new Promise(() => undefined) }));
afterEach(() => vi.unstubAllGlobals());

const SCRIPT = {
  file: "backup.sh", name: "Backup", language: "sh", text: "#!/bin/sh\n# cave:\n#   name: Backup\n",
  header: { name: "Backup", target: "sandbox", timeout: "PT1M", sample: null, secrets: ["NAS_PASSWORD"],
            params: { keep: { type: "int", default: 7, min: 1, max: 30, choices: null },
                      mode: { type: "str", default: "full", min: null, max: null, choices: ["full", "quick"] },
                      dry: { type: "bool", default: false, min: null, max: null, choices: null } } },
};

function scriptPage(extra: Record<string, unknown>) {
  const calls = mockApi({ "GET /scripts/backup.sh": SCRIPT, "GET /scripts/backup.sh/runs": [], ...extra });
  const view = renderWith(<Routes><Route path="/admin/scripts/:file" element={<ScriptEditor />} /></Routes>,
                          "/admin/scripts/backup.sh");
  return { ...view, calls };
}

describe("scripts", () => {
  it("builds the test-run form from the header and sends typed values", async () => {
    const { calls, container } = scriptPage({ "POST /scripts/backup.sh/run": { result: { kept: 3 } } });
    const keep = await screen.findByRole("spinbutton", { name: "keep" });
    expect(keep).toHaveValue(7);
    expect(screen.getByRole("combobox", { name: "mode" })).toHaveDisplayValue("full");
    expect(screen.getByText(/Only an Admin can save this/)).toBeInTheDocument();
    await userEvent.clear(keep);
    await userEvent.type(keep, "3");
    await userEvent.click(screen.getByRole("checkbox", { name: "dry" }));
    await userEvent.click(screen.getByRole("button", { name: "Test run" }));
    expect(await screen.findByText(/"kept": 3/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ params: { keep: 3, mode: "full", dry: true } });
    await expectAccessible(container);
  });

  it("shows the log tail when a run fails", async () => {
    scriptPage({ "POST /scripts/backup.sh/run": [409, { detail: "exit code 2\nrsync: connection refused\nbye" }] });
    await userEvent.click(await screen.findByRole("button", { name: "Test run" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("rsync: connection refused");
    expect(alert.querySelector("pre")).not.toBeNull();
  });
});

const VIEW = { slug: "kids", title: "Kids", icon: null, views: [{ id: "main", title: "Main", sections: [
  { title: "Play", cards: [{ type: "markdown", w: 12, h: 1, text: "Hello kids" }] }] }] };

describe("dashboards", () => {
  it("saves, then previews the saved view, and links to its access row", async () => {
    setNarrow(false);
    const calls = mockApi({
      "GET /dashboards/kids": { id: "kids", name: "Kids", yaml: "dashboard:\n  title: Kids\n" },
      "PUT /dashboards/kids": { id: "kids", name: "Kids" },
      "GET /dashboards/kids/view": VIEW,
    });
    const { container } = renderWith(
      <LiveContext.Provider value={null}>
        <Routes><Route path="/admin/dashboards/:slug" element={<DashboardEditor />} /></Routes>
      </LiveContext.Provider>,
      "/admin/dashboards/kids",
    );
    await userEvent.click(await screen.findByRole("tab", { name: "YAML" }));
    const text = await screen.findByRole("textbox", { name: "YAML" });
    await userEvent.type(text, "#");
    await userEvent.click(screen.getByRole("button", { name: "Save and preview" }));
    expect(await screen.findByText("Hello kids")).toBeInTheDocument();
    const put = calls.findIndex((c) => c.method === "PUT");
    const view = calls.findIndex((c) => c.path === "/dashboards/kids/view");
    expect(put).toBeGreaterThan(-1);
    expect(view).toBeGreaterThan(put);
    expect(screen.getByRole("link", { name: "Access" })).toHaveAttribute("href", "/admin/access#dashboard:kids");
    await expectAccessible(container);
  });
});

describe("networks", () => {
  it("shows the API's 422 next to the field", async () => {
    mockApi({
      "GET /system/networks": { local_ranges: ["192.168.1.0/24"], trusted_proxies: [] },
      "PUT /system/networks": [422, { detail: "'192.168.1.300/24' isn't a network range." }],
    });
    const { container } = renderWith(<Networks />);
    const ranges = await screen.findByRole("textbox", { name: "Local network ranges" });
    await waitFor(() => expect(ranges).toHaveValue("192.168.1.0/24"));
    await userEvent.clear(ranges);
    await userEvent.type(ranges, "192.168.1.300/24");
    await userEvent.click(screen.getByRole("button", { name: "Save networks" }));
    expect(await screen.findByText("'192.168.1.300/24' isn't a network range.")).toBeInTheDocument();
    await expectAccessible(container);
  });
});

describe("config errors", () => {
  it("links each broken file to its editor", async () => {
    mockApi({ "GET /config/errors": {
      "automations/ups.yaml": "automations/ups.yaml:7: triggers.0.to: Input should be a valid string",
      "scripts/backup.sh": "scripts/backup.sh: the header needs a name",
      "dashboards/kids.yaml": "dashboards/kids.yaml:3: unknown key",
    } });
    const { container } = renderWith(<ConfigErrors />);
    expect(await screen.findByRole("link", { name: "automations/ups.yaml:7" })).toHaveAttribute(
      "href", "/admin/automations/automations/ups");
    expect(screen.getByRole("link", { name: "scripts/backup.sh" })).toHaveAttribute("href", "/admin/scripts/backup.sh");
    expect(screen.getByRole("link", { name: "dashboards/kids.yaml:3" })).toHaveAttribute("href", "/admin/dashboards/kids");
    expect(screen.getByText(/Input should be a valid string/)).toBeInTheDocument();
    await expectAccessible(container);
  });
});
