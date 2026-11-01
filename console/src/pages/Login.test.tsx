import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { expectAccessible } from "../test/axe";
import { mockApi, renderWith } from "../test/render";
import { Login } from "./Login";

const app = (
  <Routes>
    <Route path="/login" element={<Login />} />
    <Route path="/" element={<p>Home page</p>} />
    <Route path="/admin" element={<p>Admin page</p>} />
  </Routes>
);

async function signIn(user = "sam", pw = "pw-sam-1234") {
  await userEvent.type(screen.getByLabelText("Username"), user);
  await userEvent.type(screen.getByLabelText("Password"), pw);
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("sign in", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("signs in without a code and goes where you were headed", async () => {
    mockApi({ "POST /auth/login": { mfa_required: false } });
    const { container } = renderWith(app, "/login?next=%2Fadmin");
    await expectAccessible(container);
    await signIn();
    expect(await screen.findByText("Admin page")).toBeInTheDocument();
  });

  it("asks for the authenticator code next", async () => {
    const calls = mockApi({ "POST /auth/login": { mfa_required: true }, "POST /auth/mfa": { ok: true } });
    renderWith(app, "/login");
    await signIn("admin", "pw");
    await userEvent.type(await screen.findByLabelText("Code from your authenticator app"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Home page")).toBeInTheDocument();
    expect(calls.at(-1)).toMatchObject({ path: "/auth/mfa", body: { code: "123456" } });
  });

  it("sets up an authenticator when one is required but missing", async () => {
    mockApi({
      "POST /auth/login": { mfa_required: true, mfa_setup: true },
      "POST /auth/mfa/setup": { provisioning_uri: "otpauth://totp/CAVE:op?secret=JBSWY3DPEHPK3PXP",
                                recovery_codes: ["aaaa-bbbb", "cccc-dddd"] },
      "POST /auth/mfa": { ok: true },
    });
    renderWith(app, "/login");
    await signIn("op", "pw");
    expect(await screen.findByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: /QR code/ })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Code from your authenticator app"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("aaaa-bbbb")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("I've saved these codes somewhere safe"));
    await userEvent.click(screen.getByRole("button", { name: "Go to CAVE" }));
    expect(await screen.findByText("Home page")).toBeInTheDocument();
  });

  it("shows the server's own error words", async () => {
    mockApi({ "POST /auth/login": [401, { detail: "Wrong username or password." }] });
    vi.stubGlobal("location", { ...window.location, pathname: "/login", search: "", assign: vi.fn() });
    renderWith(app, "/login");
    await signIn("sam", "nope");
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Wrong username or password."));
  });
});
