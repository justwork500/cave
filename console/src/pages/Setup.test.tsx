import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { expectAccessible } from "../test/axe";
import { mockApi, renderWith } from "../test/render";
import { Setup } from "./Setup";

const app = (
  <Routes>
    <Route path="/setup" element={<Setup />} />
    <Route path="/" element={<p>Home page</p>} />
    <Route path="/login" element={<p>Sign-in page</p>} />
  </Routes>
);

describe("first-run setup", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("goes through code, owner, authenticator and recovery codes", async () => {
    const calls = mockApi({
      "GET /setup": { needed: true },
      "POST /setup": { provisioning_uri: "otpauth://totp/CAVE:owner?secret=ABCDEFGH", recovery_codes: ["r1", "r2"] },
      "POST /auth/mfa": { ok: true },
    });
    const { container } = renderWith(app, "/setup");
    await userEvent.type(await screen.findByLabelText("Setup code"), "7KQ2-M9XD-AAAA-BBBB");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.type(screen.getByLabelText("Your name"), "Owner");
    await userEvent.type(screen.getByLabelText("Username"), "owner");
    await userEvent.type(screen.getByLabelText("Password"), "a-long-owner-password");
    await userEvent.click(screen.getByRole("button", { name: "Create owner account" }));
    expect(await screen.findByText("ABCDEFGH")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Code from your authenticator app"), "654321");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("r1")).toBeInTheDocument();
    const finish = screen.getByRole("button", { name: "Go to CAVE" });
    expect(finish).toBeDisabled();
    await userEvent.click(screen.getByLabelText("I've saved these codes somewhere safe"));
    await expectAccessible(container);
    await userEvent.click(finish);
    expect(await screen.findByText("Home page")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/setup" && c.method === "POST")?.body).toMatchObject({
      code: "7KQ2-M9XD-AAAA-BBBB", username: "owner", display_name: "Owner" });
  });

  it("refuses short passwords before asking the server", async () => {
    mockApi({ "GET /setup": { needed: true } });
    renderWith(app, "/setup");
    await userEvent.type(await screen.findByLabelText("Setup code"), "X");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.type(screen.getByLabelText("Password"), "short");
    expect(screen.getByRole("button", { name: "Create owner account" })).toBeDisabled();
    expect(screen.getByText(/at least 12 characters/)).toBeInTheDocument();
  });

  it("sends you to sign in once CAVE is set up", async () => {
    mockApi({ "GET /setup": { needed: false } });
    renderWith(app, "/setup");
    expect(await screen.findByText("Sign-in page")).toBeInTheDocument();
  });
});
