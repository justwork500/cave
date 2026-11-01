import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../app/routes";
import { expectAccessible } from "../test/axe";
import { mockApi, renderWith, setNarrow } from "../test/render";
import { Access } from "./Access";
import { Devices } from "./Devices";
import { Screens } from "./Screens";
import { Users } from "./Users";

vi.mock("qrcode", () => ({
  default: { toDataURL: vi.fn(async (text: string) => `data:image/png;base64,${btoa(text)}`) },
}));

afterEach(() => vi.unstubAllGlobals());

describe("admin layout", () => {
  it("lists only the sections you have", async () => {
    setNarrow(false);
    const operator = { kind: "user", id: "o", username: "op", display_name: "Op", role: "operator", has_totp: true,
                       sections: ["section:devices", "section:automations"] };
    mockApi({ "GET /me": operator, "GET /items": [], "GET /notifications": [], "GET /summary": { unavailable: 2 } });
    const { container } = renderWith(<AppRoutes />, "/admin");
    const nav = await screen.findByRole("navigation", { name: "Admin console" });
    expect(within(nav).getByRole("link", { name: "Devices" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Automations" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Users" })).not.toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /2 devices not responding/ })).toHaveAttribute(
      "href", "/admin/devices?filter=unavailable");
    await expectAccessible(container);
  });
});

const ITEM = { id: "dashboard:garage", kind: "dashboard", name: "Garage", allowed: true, status: "enabled",
               visibility: "show", others_see: "locked", network: "anywhere", builtin: false };

function access(extra: Record<string, unknown> = {}) {
  return mockApi({
    "GET /items": [ITEM],
    "GET /items/dashboard:garage/assignments": [{ kind: "role", id: "admin" }],
    "GET /users": [{ id: "u1", username: "sam", display_name: "Sam", role: "household", enabled: true,
                     expires_at: null }],
    "GET /groups": [{ id: "g1", name: "Kids", members: [] }],
    "GET /screens": [{ id: "s1", name: "Garage tablet", status: "approved", fingerprint: "AB:CD", created_at: "" }],
    "PATCH /items/dashboard:garage": (b: unknown) => ({ ...ITEM, ...(b as object) }),
    "PUT /items/dashboard:garage/assignments": (b: unknown) => b,
    ...extra,
  });
}

describe("access", () => {
  it("shows Others see it only for Restrict, and saves the row", async () => {
    const calls = access();
    const { container } = renderWith(<Access />);
    const visibility = await screen.findByRole("combobox", { name: "Visibility for Garage" });
    expect(screen.queryByRole("combobox", { name: "Others see Garage" })).not.toBeInTheDocument();
    await userEvent.selectOptions(visibility, "restrict");
    expect(await screen.findByRole("combobox", { name: "Others see Garage" })).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ visibility: "restrict" });
    expect(await screen.findByRole("button", { name: "Undo" })).toBeInTheDocument();
    await expectAccessible(container);
  });

  it("assigns a group with the keyboard alone", async () => {  // Review Focus 5
    const calls = access();
    renderWith(<Access />);
    const assign = await screen.findByRole("button", { name: "Assign Garage" });
    assign.focus();
    await userEvent.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog");
    within(dialog).getByRole("tab", { name: "Groups" }).focus();
    await userEvent.keyboard("{Enter}");
    within(dialog).getByRole("button", { name: "Add Kids" }).focus();
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual([
      { kind: "role", id: "admin" }, { kind: "group", id: "g1" }]));
    expect(await screen.findByText("Kids")).toBeInTheDocument();
  });
});

describe("screens", () => {
  it("shows the enrollment link as a QR code with a countdown", async () => {
    const url = "https://cave.local/enroll#abc123";
    mockApi({
      "GET /screens": [],
      "POST /screens": { screen: { id: "s9", name: "Hall", status: "pending", fingerprint: null, created_at: "" },
                         enroll_url: url, expires_at: new Date(Date.now() + 600_000).toISOString() },
    });
    const { container } = renderWith(<Screens />);
    await userEvent.click(await screen.findByRole("button", { name: "Add screen" }));
    await userEvent.type(screen.getByLabelText("Screen name"), "Hall");
    await userEvent.click(screen.getByRole("button", { name: "Create enrollment link" }));
    const qr = await screen.findByRole("img", { name: /QR code/ });
    expect(qr.getAttribute("src")).toContain(btoa(url));
    expect(screen.getByText(url)).toBeInTheDocument();
    expect(screen.getByText(/Expires in (10:00|9:5\d)/)).toBeInTheDocument();
    await expectAccessible(container);
  });

  it("approves only once you've checked the fingerprints match", async () => {
    const calls = mockApi({
      "GET /screens": [{ id: "s1", name: "Garage tablet", status: "pending", fingerprint: "AB:CD:EF", created_at: "" }],
      "POST /screens/s1/approve": { id: "s1", name: "Garage tablet", status: "approved", fingerprint: "AB:CD:EF",
                                    created_at: "" },
    });
    renderWith(<Screens />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve Garage tablet" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("AB:CD:EF")).toBeInTheDocument();
    const approve = within(dialog).getByRole("button", { name: "Approve" });
    expect(approve).toBeDisabled();
    await userEvent.click(within(dialog).getByLabelText("They match"));
    await userEvent.click(approve);
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/screens/s1/approve")).toBe(true));
  });
});

describe("users", () => {
  it("shows the last-Admin refusal in the API's words", async () => {
    mockApi({
      "GET /users": [{ id: "a", username: "admin", display_name: "Alex", role: "admin", enabled: true,
                       expires_at: null }],
      "PATCH /users/a": [409, { detail: "CAVE needs at least one active Admin." }],
    });
    const { container } = renderWith(<Users />);
    await userEvent.click(await screen.findByRole("switch", { name: "Alex enabled" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("CAVE needs at least one active Admin.");
    await expectAccessible(container);
  });
});

describe("devices", () => {
  it("edits devices you control and locks the rest", async () => {
    const calls = mockApi({
      "GET /states": [
        { entity_id: "light.porch", name: "Porch light", area_id: null, capability: "switch", state: "on",
          attributes: {}, last_changed: null },
        { entity_id: "cover.garage", name: "Garage door", area_id: null, restricted: true },
      ],
      "GET /areas": [{ id: "garage", name: "Garage", floor: null }],
      "PATCH /entities/light.porch": { ok: true },
    });
    const { container } = renderWith(<Devices />);
    const locked = (await screen.findByText("Garage door")).closest("tr") as HTMLElement;
    expect(within(locked).getByText("Restricted")).toBeInTheDocument();
    expect(within(locked).queryByRole("button")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Edit Porch light" }));
    const name = await screen.findByLabelText("Name");
    await userEvent.clear(name);
    await userEvent.type(name, "Front porch");
    await userEvent.selectOptions(screen.getByLabelText("Room"), "garage");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
      name: "Front porch", area_id: "garage" }));
    await expectAccessible(container);
  });
});
