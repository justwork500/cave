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

  describe("integrations", () => {
    const KASA = { "POST /kasa/scan": { signed_in: true, login_ok: true, devices: [] } };
    const HUE = { domain: "hue", title: "Philips Hue", pairing: "key", pairing_hint: "Find it in the Hue app.", devices: [] };
    const SHELLY = { domain: "shelly", title: "Shelly", pairing: "none", pairing_hint: "", devices: [] };
    const BRIDGE = { device_id: "b1", host: "192.168.1.40", model: "Hue Bridge", name: "Hallway bridge", added: false };

    async function setUp(title: string) {
      const panel = await open();
      await userEvent.click(await within(panel).findByRole("button", { name: `Set up ${title}` }));
      return panel;
    }
    async function check(panel: HTMLElement) {
      await userEvent.type(within(panel).getByLabelText("Device address"), "192.168.1.40");
      await userEvent.click(within(panel).getByRole("button", { name: "Check" }));
    }

    it("lists every integration", async () => {
      mockApi({ ...BASE, ...KASA, "GET /integrations": [HUE, SHELLY] });
      const panel = await open();
      expect(await within(panel).findByText("Philips Hue")).toBeInTheDocument();
      expect(within(panel).getByText("Shelly")).toBeInTheDocument();
    });

    it("checks an address then adds with a key", async () => {
      const calls = mockApi({
        ...BASE, ...KASA, "GET /integrations": [HUE],
        "POST /integrations/hue/probe": BRIDGE,
        "POST /integrations/hue/devices": [201, BRIDGE],
      });
      const panel = await setUp("Philips Hue");
      await check(panel);
      expect(await within(panel).findByText("Hue Bridge")).toBeInTheDocument();
      await userEvent.type(within(panel).getByLabelText("Encryption key"), "the-key");
      await userEvent.click(within(panel).getByRole("button", { name: "Add" }));
      await within(panel).findByRole("button", { name: "Set up Philips Hue" });
      expect(calls.find((c) => c.path === "/integrations/hue/devices" && c.method === "POST")?.body)
        .toEqual({ host: "192.168.1.40", secret: "the-key" });
    });

    it("button pairing shows the hint and no input", async () => {
      mockApi({
        ...BASE, ...KASA,
        "GET /integrations": [{ ...HUE, pairing: "button", pairing_hint: "Press the button on top." }],
        "POST /integrations/hue/probe": BRIDGE,
      });
      const panel = await setUp("Philips Hue");
      await check(panel);
      expect(await within(panel).findByText("Press the button on top.")).toBeInTheDocument();
      expect(within(panel).queryByLabelText("Encryption key")).not.toBeInTheDocument();
    });

    it("shows a refused address inline", async () => {
      mockApi({
        ...BASE, ...KASA, "GET /integrations": [HUE],
        "POST /integrations/hue/probe": [422, { detail: "Use the device's address on your home network, like 192.168.1.40." }],
      });
      const panel = await setUp("Philips Hue");
      await check(panel);
      const field = within(panel).getByLabelText("Device address");
      expect(await within(panel).findByText(/home network/)).toBeInTheDocument();
      expect(field).toHaveAccessibleDescription(/home network/);
    });

    it("asks before removing", async () => {
      const calls = mockApi({
        ...BASE, ...KASA,
        "GET /integrations": [{ ...HUE, devices: [{ device_id: "b1", host: "192.168.1.40", model: "Hue Bridge", name: "Hallway bridge" }] }],
        "DELETE /integrations/hue/devices/b1": undefined,
      });
      const panel = await setUp("Philips Hue");
      await userEvent.click(await within(panel).findByRole("button", { name: "Remove Hallway bridge" }));
      const dialog = await screen.findByRole("dialog", { name: /Remove Hallway bridge/ });
      expect(calls.some((c) => c.method === "DELETE")).toBe(false);
      await userEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
      await vi.waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    });

    it("never shows a saved secret", async () => {
      mockApi({
        ...BASE, ...KASA, "GET /integrations": [HUE],
        "POST /integrations/hue/probe": BRIDGE,
        "POST /integrations/hue/devices": [201, BRIDGE],
      });
      const panel = await setUp("Philips Hue");
      await check(panel);
      await userEvent.type(await within(panel).findByLabelText("Encryption key"), "the-key");
      await userEvent.click(within(panel).getByRole("button", { name: "Add" }));
      await userEvent.click(await within(panel).findByRole("button", { name: "Set up Philips Hue" }));
      for (const box of within(panel).getAllByRole("textbox")) expect(box).toHaveValue("");
      expect(panel.querySelector("input[type=password]")).toBeNull();
    });

    it("is accessible", async () => {
      mockApi({ ...BASE, ...KASA, "GET /integrations": [HUE], "POST /integrations/hue/probe": BRIDGE });
      const panel = await setUp("Philips Hue");
      await check(panel);
      await within(panel).findByLabelText("Encryption key");
      await expectAccessible(panel);
    });
  });
});
