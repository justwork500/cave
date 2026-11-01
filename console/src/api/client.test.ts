import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./client";

function reply(status: number, body?: unknown) {
  return vi.fn().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: body === undefined ? {} : { "content-type": "application/json" },
    }),
  );
}

describe("api client", () => {
  const assign = vi.fn();
  beforeEach(() => {
    vi.stubGlobal("location", { pathname: "/admin/users", search: "?q=1", assign });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    assign.mockReset();
  });

  it("returns JSON and sends same-origin credentials", async () => {
    const fetch = reply(200, { status: "ok" });
    vi.stubGlobal("fetch", fetch);
    expect(await api.get("/health")).toEqual({ status: "ok" });
    expect(fetch).toHaveBeenCalledWith("/api/v1/health", expect.objectContaining({ credentials: "same-origin" }));
  });

  it("carries the server's detail in ApiError", async () => {
    vi.stubGlobal("fetch", reply(403, { detail: "You don't have access to this." }));
    await expect(api.post("/x", { a: 1 })).rejects.toEqual(new ApiError(403, "You don't have access to this."));
  });

  it("falls back to a plain message when there's no detail", async () => {
    vi.stubGlobal("fetch", reply(500, { oops: true }));
    await expect(api.get("/x")).rejects.toMatchObject({ status: 500, detail: "Something went wrong. Try again." });
  });

  it("sends you to sign in on 401, keeping where you were", async () => {
    vi.stubGlobal("fetch", reply(401, { detail: "Sign in to continue." }));
    await expect(api.get("/me")).rejects.toBeInstanceOf(ApiError);
    expect(assign).toHaveBeenCalledWith("/login?next=%2Fadmin%2Fusers%3Fq%3D1");
  });

  it("sends a kiosk screen back to its key sign-in, not the password page", async () => {
    localStorage.setItem("cave-screen-id", "scr1");
    vi.stubGlobal("fetch", reply(401, { detail: "Sign in to continue." }));
    await expect(api.get("/me")).rejects.toBeInstanceOf(ApiError);
    expect(assign).toHaveBeenCalledWith("/enroll");
    localStorage.removeItem("cave-screen-id");
  });

  it("doesn't redirect from the sign-in page itself", async () => {
    vi.stubGlobal("location", { pathname: "/login", search: "", assign });
    vi.stubGlobal("fetch", reply(401, { detail: "Wrong username or password." }));
    await expect(api.post("/auth/login", {})).rejects.toBeInstanceOf(ApiError);
    expect(assign).not.toHaveBeenCalled();
  });

  it("returns undefined for 204", async () => {
    vi.stubGlobal("fetch", reply(204));
    expect(await api.del("/thing")).toBeUndefined();
  });
});
