import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ADMIN, SAM, mockApi, renderWith, setNarrow } from "../test/render";
import { AppRoutes } from "./routes";

describe("routes", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows No access for an admin page you can't use", async () => {  // Review Focus 3
    setNarrow(false);
    mockApi({ "GET /me": SAM, "GET /items": [], "GET /notifications": [] });
    renderWith(<AppRoutes />, "/admin/users");
    expect(await screen.findByRole("heading", { name: "You don't have access to this" })).toBeInTheDocument();
  });

  it("lets an Admin into the console", async () => {
    setNarrow(false);
    mockApi({ "GET /me": ADMIN, "GET /items": [], "GET /notifications": [], "GET /summary": {} });
    renderWith(<AppRoutes />, "/admin");
    expect(await screen.findByRole("heading", { name: "Home" })).toBeInTheDocument();
  });

  it("sends signed-out people to setup or sign in", async () => {
    setNarrow(false);
    mockApi({ "GET /me": [401, { detail: "Sign in to continue." }], "GET /setup": { needed: true } });
    vi.stubGlobal("location", { ...window.location, pathname: "/login", search: "", assign: vi.fn() });
    renderWith(<AppRoutes />, "/");
    expect(await screen.findByRole("heading", { name: "Set up CAVE" })).toBeInTheDocument();
  });
});
