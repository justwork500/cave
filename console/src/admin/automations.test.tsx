import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { expectAccessible } from "../test/axe";
import { mockApi, renderWith } from "../test/render";
import { AutomationEditor } from "./Automations";
import { SentenceBuilder } from "./SentenceBuilder";
import { fromYaml } from "./sentence";
import { TestCenter } from "./TestCenter";
import { YamlEditor } from "../editor/YamlEditor";

vi.mock("../editor/monaco", () => ({ loadMonaco: () => new Promise(() => undefined) }));
afterEach(() => vi.unstubAllGlobals());

const DEVICES = [
  { entity_id: "binary_sensor.ups_on_battery", name: "UPS on battery", area_id: null, capability: "binary_sensor",
    state: "off", attributes: {}, last_changed: null },
  { entity_id: "sensor.ups_runtime", name: "UPS runtime", area_id: null, capability: "sensor", state: "40",
    attributes: { unit: "min" }, last_changed: null },
  { entity_id: "cover.garage", name: "Garage door", area_id: null, restricted: true },
];
const YAML = `automation:
  id: ups
  name: UPS alert
  triggers:
    - type: state
      entity: binary_sensor.ups_on_battery
      to: "on"
      for: 2m
  conditions:
    - type: numeric_state
      entity: sensor.ups_runtime
      below: 15
  actions:
    - type: notify
      message: UPS on battery
    - type: sequence
      ref: sequence.lab_safe_shutdown
`;
const LISTS = {
  "GET /states": DEVICES,
  "GET /sequences": [{ id: "lab_safe_shutdown", name: "Lab safe shutdown", allowed: true }],
  "GET /scripts": [],
  "GET /me": { kind: "user", id: "a", username: "alex", display_name: "Alex", role: "admin", has_totp: true,
               sections: ["section:automations"] },
};

describe("sentence builder", () => {
  it("shows names, never ids, and lists only devices you control", async () => {
    mockApi(LISTS);
    const onChange = vi.fn();
    function Harness() {
      const [s, setS] = useState(fromYaml(YAML)!);
      return <SentenceBuilder sentence={s} onChange={(n) => { setS(n); onChange(n); }} />;
    }
    const { container } = renderWith(<Harness />);
    const device = await screen.findByRole("combobox", { name: "Trigger device" });
    await waitFor(() => expect(device).toHaveDisplayValue("UPS on battery"));
    expect(within(device).queryByText("Garage door")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Routine to run" })).toHaveDisplayValue("Lab safe shutdown");
    expect(container.textContent).not.toMatch(/binary_sensor\.|sequence\./);
    await userEvent.clear(screen.getByRole("textbox", { name: "Below" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Below" }), "20");
    expect(onChange.mock.lastCall?.[0].automation.conditions[0].below).toBe(20);
    await expectAccessible(container);
  });
});

function editor(yaml: string, extra: Record<string, unknown> = {}) {
  const calls = mockApi({ ...LISTS, "GET /automations/ups": { id: "ups", name: "UPS alert", yaml }, ...extra });
  const view = renderWith(
    <Routes>
      <Route path="/admin/automations/:kinds/:id" element={<AutomationEditor />} />
    </Routes>,
    "/admin/automations/automations/ups",
  );
  return { ...view, calls };
}

describe("automation editor", () => {
  it("disables saving from Simple when the YAML is outside its shape", async () => {
    editor(YAML.replace("    - type: sequence\n", "    - type: choose\n      options: []\n    - type: sequence\n"));
    expect(await screen.findByText(/uses features the Simple view can't show/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("saves after showing the change, and shows the save guard's words", async () => {
    const { calls } = editor(YAML, {
      "PUT /automations/ups": [403, { detail: "You can't save this because you don't have access to: cover.garage" }],
    });
    await userEvent.click(await screen.findByRole("tab", { name: "Advanced" }));
    const text = await screen.findByRole("textbox", { name: "YAML" });
    await userEvent.type(text, "#");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    // a text lookup: role queries compute styles for the whole page and ran out of time on CI
    const title = await screen.findByText("Save these changes?", {}, { timeout: 5000 });
    const dialog = title.closest<HTMLElement>('[role="dialog"]')!;
    expect(await within(dialog).findByText("Before")).toBeInTheDocument();
    // a text lookup: role queries compute styles for every diff line and time out under load
    await userEvent.click(await within(dialog).findByText("Save changes"));
    expect(await screen.findByRole("alert")).toHaveTextContent("don't have access to: cover.garage");
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ yaml: `${YAML}#` });
  });
});

describe("YAML editor", () => {
  it("keeps </script> as text", () => {  // Review Focus 4
    const { container } = renderWith(<YamlEditor label="YAML" value={"message: </script><script>alert(1)</script>"}
                                                 onChange={() => undefined} />);
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByRole("textbox", { name: "YAML" })).toHaveValue("message: </script><script>alert(1)</script>");
  });
});

describe("test center", () => {
  it("runs with simulated values and shows each What if line and the summary", async () => {
    const calls = mockApi({
      ...LISTS,
      "GET /automations": [{ id: "ups", name: "UPS alert", allowed: true }],
      "GET /automations/ups": { id: "ups", name: "UPS alert", yaml: YAML },
      "POST /test-center/run": {
        trace: { outcome: "finished", variables: {}, error: null, steps: [
          { path: "triggers/0", type: "trigger", detail: "UPS on battery changed to on", started_at: "", result: "ok",
            data: {} },
          { path: "actions/0", type: "notify", detail: "What if: notify 'UPS on battery'", started_at: "",
            result: "what_if", data: {} },
          { path: "summary", type: "summary", detail: "Done. 0 devices changed, 0 messages sent, 0 scripts run.",
            started_at: "", result: "ok", data: {} },
        ] },
        summary: { devices_changed: 0, messages_sent: 0, scripts_run: 0 },
      },
    });
    const { container } = renderWith(<TestCenter />);
    await screen.findByRole("option", { name: "UPS alert" });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Automation or routine" }), "automation:ups");
    const runtime = await screen.findByRole("textbox", { name: "UPS runtime" });
    await userEvent.type(runtime, "12");
    await userEvent.click(screen.getByRole("button", { name: "Run test" }));
    expect(await screen.findByText("What if: notify 'UPS on battery'")).toBeInTheDocument();
    expect(screen.getByText("What if", { selector: ".chip" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Done. 0 devices changed, 0 messages sent, 0 scripts run.");
    expect(calls.find((c) => c.path === "/test-center/run")?.body).toMatchObject({
      kind: "automation", id: "ups", states: { "sensor.ups_runtime": "12" } });
    await expectAccessible(container);
  });
});

describe("new automations", () => {
  it("never replaces an existing file: saves with create, and shows the refusal", async () => {
    const calls = mockApi({
      ...LISTS,
      "PUT /automations/new-automation": [409, { detail: "new-automation is already taken. Choose another id." }],
    });
    renderWith(
      <Routes><Route path="/admin/automations/new" element={<AutomationEditor />} /></Routes>,
      "/admin/automations/new",
    );
    await userEvent.click(await screen.findByRole("button", { name: "Start blank" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    // a text lookup: role queries compute styles for the whole page and ran out of time on CI
    const title = await screen.findByText("Save these changes?", {}, { timeout: 5000 });
    const dialog = title.closest<HTMLElement>('[role="dialog"]')!;
    await userEvent.click(await within(dialog).findByText("Save changes"));
    expect(await screen.findByRole("alert")).toHaveTextContent("new-automation is already taken");
    expect(calls.find((c) => c.method === "PUT")?.query).toBe("?create=true");
  });

  it("creates recipes without replacing anything", async () => {
    const calls = mockApi({ ...LISTS, "PUT /automations/washer-finished": { id: "washer-finished", name: "Washer finished" },
                            "GET /automations": [] });
    renderWith(
      <Routes>
        <Route path="/admin/automations/new" element={<AutomationEditor />} />
        <Route path="/admin/automations" element={<p>List</p>} />
      </Routes>,
      "/admin/automations/new",
    );
    await userEvent.click(await screen.findByRole("button", { name: "Tell me when the washer finishes" }));
    await screen.findByRole("option", { name: "UPS runtime" });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Washer power sensor" }), "sensor.ups_runtime");
    await userEvent.type(screen.getByRole("textbox", { name: "Finished below (watts)" }), "5");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("List")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.query).toBe("?create=true");
  });
});

