import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { expectAccessible } from "../test/axe";
import { mockApi, renderWith } from "../test/render";
import { Devices } from "./Devices";

afterEach(() => vi.unstubAllGlobals());

const PLUG = { mac: "aabbccddee01", host: "10.0.0.5", model: "HS103(US)", added: false, name: null };
const BASE = { "GET /states": [], "GET /areas": [] };

async function open() {
  renderWith(<Devices />);
  await userEvent.click(await screen.findByRole("button", { name: "Add device" }));
  return screen.findByRole("dialog");
}

describe("add device", () => {
  it("scans on opening, asks for the TP-Link sign-in, then adds what it found", async () => {
    let signedIn = false;
    const calls = mockApi({
      ...BASE,
      "POST /kasa/scan": () => signedIn
        ? { signed_in: true, login_ok: true, devices: [{ ...PLUG, name: "Lamp" }] }
        : { signed_in: false, login_ok: null, devices: [PLUG] },
      "PUT /kasa/login": () => { signedIn = true; return [204, undefined]; },
      "POST /kasa/devices": [201, { mac: PLUG.mac }],
    });
    const panel = await open();
    expect(await within(panel).findByText("HS103(US)")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Add HS103(US)" })).toBeDisabled();
    await userEvent.type(within(panel).getByLabelText("TP-Link email"), "sam@example.com");
    await userEvent.type(within(panel).getByLabelText("TP-Link password"), "pw");
    await expectAccessible(panel);
    await userEvent.click(within(panel).getByRole("button", { name: "Sign in" }));
    await userEvent.click(await within(panel).findByRole("button", { name: "Add Lamp" }));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ username: "sam@example.com", password: "pw" });
    expect(calls.find((c) => c.path === "/kasa/devices")?.body).toEqual({ mac: PLUG.mac });
  });

  it("says so when TP-Link's sign-in is refused", async () => {
    mockApi({ ...BASE, "POST /kasa/scan": { signed_in: true, login_ok: false, devices: [PLUG] } });
    const panel = await open();
    expect(await within(panel).findByText(/didn't accept that sign-in/)).toBeInTheDocument();
    expect(within(panel).getByLabelText("TP-Link email")).toBeInTheDocument();
  });

  it("removes a device that's already added", async () => {
    const calls = mockApi({
      ...BASE,
      "POST /kasa/scan": { signed_in: true, login_ok: true, devices: [{ ...PLUG, name: "Lamp", added: true }] },
      "DELETE /kasa/devices/aabbccddee01": undefined,
    });
    const panel = await open();
    await userEvent.click(await within(panel).findByRole("button", { name: "Remove Lamp" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(true);
  });

  it("explains what to check when nothing is found", async () => {
    mockApi({ ...BASE, "POST /kasa/scan": { signed_in: false, login_ok: null, devices: [] } });
    const panel = await open();
    expect(await within(panel).findByText(/No Kasa devices found/)).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: "How MQTT devices connect" })).toBeInTheDocument();
  });
});
