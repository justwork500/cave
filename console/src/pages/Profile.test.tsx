import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeContext } from "../app/prefs";
import { expectAccessible } from "../test/axe";
import { mockApi, renderWith } from "../test/render";
import { Profile } from "./Profile";

describe("profile", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("changes the theme and the password", async () => {
    const calls = mockApi({ "GET /items": [], "POST /me/password": [204, undefined] });
    const setTheme = vi.fn();
    const { container } = renderWith(
      <ThemeContext.Provider value={{ theme: "light", setTheme }}>
        <Profile />
      </ThemeContext.Provider>,
    );
    await expectAccessible(container);
    await userEvent.click(screen.getByLabelText("Dark"));
    expect(setTheme).toHaveBeenCalledWith("dark");
    await userEvent.type(screen.getByLabelText("Current password"), "old-password");
    await userEvent.type(screen.getByLabelText("New password"), "a-brand-new-password");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("Password changed.")).toBeInTheDocument();
    expect(calls.at(-1)).toMatchObject({ path: "/me/password", body: { current: "old-password" } });
  });
});
