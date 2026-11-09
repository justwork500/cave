import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { expectAccessible } from "../../test/axe";
import { ADMIN, SAM, mockApi, renderWith, setNarrow } from "../../test/render";
import { MenuBar } from "./MenuBar";
import { LiveContext } from "../live";
import type { NotificationEvent } from "../../api/ws";

function fakeLive() {
  let push: ((e: NotificationEvent) => void) | undefined;
  return {
    feed: { onState: () => () => undefined, stop: vi.fn(), onNotification: (cb: (e: NotificationEvent) => void) => {
      push = cb;
      return () => undefined;
    } },
    push: (e: NotificationEvent) => push?.(e),
  };
}

function bar(me: object) {
  const live = fakeLive();
  const calls = mockApi({
    "GET /items": [{ id: "dashboard:home", kind: "dashboard", name: "Home", allowed: true },
                 { id: "dashboard:lab", kind: "dashboard", name: "Lab", allowed: false },
                 { id: "dashboard:gate", kind: "dashboard", name: "Gate", allowed: true, missing: true }],
    "GET /notifications": [],
    "POST /auth/logout": [204, undefined],
  });
  const view = renderWith(
    <LiveContext.Provider value={live.feed as never}>
      <MenuBar me={me as never} />
    </LiveContext.Provider>,
  );
  return { ...view, live, calls };
}

describe("menu bar", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("has no admin link for a household member", async () => {  // Review Focus 3
    setNarrow(false);
    const { container } = bar(SAM);
    expect(await screen.findByRole("link", { name: "CAVE home" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Overview" })).not.toBeInTheDocument();
    expect(screen.queryByText("Set up")).not.toBeInTheDocument();
    await expectAccessible(container);
  });

  it("shows the admin link when you have a console section", async () => {
    setNarrow(false);
    bar(ADMIN);
    expect(await screen.findByRole("link", { name: "Overview" })).toHaveAttribute("href", "/admin");
    expect(screen.getByRole("link", { name: "People" })).toHaveAttribute("href", "/admin/users");
  });

  it("leaves out dashboards whose file was deleted", async () => {
    setNarrow(false);
    bar(ADMIN);
    expect(await screen.findByRole("link", { name: "Home" })).toBeInTheDocument();
    expect(screen.queryByText("Gate")).not.toBeInTheDocument();
  });

  it("counts new notifications live", async () => {
    setNarrow(false);
    const { live } = bar(SAM);
    const bell = await screen.findByRole("button", { name: "Notifications" });
    act(() => live.push({ id: 1, title: "Power", message: "UPS on battery" }));
    expect(await screen.findByRole("button", { name: "Notifications, 1 unread" })).toBeInTheDocument();
    expect(bell).toBeInTheDocument();
  });

  it("folds into one menu button on a phone", async () => {  // Review Focus 5
    setNarrow(true);
    bar(ADMIN);
    const menu = await screen.findByRole("button", { name: "Menu" });
    expect(screen.queryByRole("link", { name: "Overview" })).not.toBeInTheDocument();
    await userEvent.click(menu);
    expect(await screen.findByRole("link", { name: "Overview" })).toBeInTheDocument();
  });

  it("stops the live feed before signing out, so its closing socket can't redirect mid-sign-in", async () => {
    setNarrow(false);
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    const { live, calls } = bar(SAM);
    await userEvent.click(await screen.findByRole("button", { name: "Sam" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Sign out" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/login"));
    expect(live.feed.stop).toHaveBeenCalled();
    expect(calls.some((c) => c.path === "/auth/logout")).toBe(true);
  });
});
