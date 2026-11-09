import userEvent from "@testing-library/user-event";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { EntityView } from "../api/types";
import { expectAccessible } from "../test/axe";
import { mockApi, renderWith } from "../test/render";
import { Controls } from "./controls";
import { Tile } from "./Tile";

const tv = (state: string, attributes: Record<string, unknown> = {}): EntityView => ({
  entity_id: "media_player.living_tv", name: "Living TV", area_id: null, capability: "media_player",
  state, attributes, last_changed: null,
});
const strip: EntityView = {
  entity_id: "select.strip", name: "Strip preset", area_id: null, capability: "select",
  state: "Rainbow", attributes: { options: ["Rainbow", "Fire"] }, last_changed: null,
};

describe("tile controls", () => {
  it("pauses a playing TV", async () => {
    const calls = mockApi({ "POST /entities/media_player.living_tv/commands/pause": {} });
    renderWith(<Controls entity={tv("playing")} />);
    await userEvent.click(screen.getByRole("button", { name: "Pause" }));
    await waitFor(() => expect(calls.at(-1)?.path).toBe("/entities/media_player.living_tv/commands/pause"));
  });

  it("turns an off TV on", async () => {
    const calls = mockApi({ "POST /entities/media_player.living_tv/commands/turn_on": {} });
    renderWith(<Controls entity={tv("off")} />);
    expect(screen.queryByRole("button", { name: /^(Pause|Play)$/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Power" }));
    await waitFor(() => expect(calls.at(-1)?.path).toBe("/entities/media_player.living_tv/commands/turn_on"));
  });

  it("sets volume on release", async () => {
    const calls = mockApi({ "POST /entities/media_player.living_tv/commands/volume_set": {} });
    renderWith(<Controls entity={tv("on", { volume: 10 })} />);
    const slider = screen.getByRole("slider", { name: "Volume" });
    fireEvent.change(slider, { target: { value: "40" } });
    expect(calls).toHaveLength(0);
    fireEvent.pointerUp(slider);
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]?.body).toEqual({ level: 40 });
  });

  it("applies a preset", async () => {
    const calls = mockApi({ "POST /entities/select.strip/commands/select_option": {} });
    renderWith(<Controls entity={strip} />);
    await userEvent.click(screen.getByRole("combobox", { name: "Strip preset" }));
    await userEvent.click(screen.getByRole("option", { name: "Fire" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]?.body).toEqual({ option: "Fire" });
  });

  it("shows no controls for a restricted device", () => {
    renderWith(<Controls entity={{ entity_id: "media_player.living_tv", name: "Living TV", area_id: null, restricted: true }} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("slider")).toBeNull();
  });

  it("shows the server's refusal", async () => {
    mockApi({
      "POST /entities/media_player.living_tv/commands/pause": [409, { detail: "This device can't take commands right now." }],
    });
    renderWith(<Controls entity={tv("playing")} />);
    await userEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(await screen.findByText("This device can't take commands right now.")).toBeInTheDocument();
  });

  it("is accessible", async () => {
    mockApi({});
    const { container } = renderWith(
      <>
        <Controls entity={tv("playing", { volume: 30, sources: ["HDMI 1"] })} />
        <Controls entity={strip} />
        <Controls entity={{ ...strip, capability: "number", state: "5", attributes: { min: 0, max: 10, step: 1, unit: "m" } }} />
      </>,
    );
    await expectAccessible(container);
  });
});

describe("controls on toggle tiles", () => {
  it("shows media controls, not a toggle button, on a toggle tile", () => {
    mockApi({});
    renderWith(<Tile entity={tv("playing")} tapAction="toggle" />);
    expect(screen.getByRole("button", { name: "Power" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Living TV/ })).toBeNull();
  });

  it("keeps a switch tile as a toggle button", async () => {
    const calls = mockApi({ "POST /entities/switch.lamp/commands/toggle": {} });
    renderWith(
      <Tile entity={{ entity_id: "switch.lamp", name: "Lamp", area_id: null, capability: "switch", state: "off", attributes: {}, last_changed: null }} tapAction="toggle" />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Lamp/ }));
    await waitFor(() => expect(calls.at(-1)?.path).toBe("/entities/switch.lamp/commands/toggle"));
  });

  it("sends volume once after a key release", async () => {
    const calls = mockApi({ "POST /entities/media_player.living_tv/commands/volume_set": {} });
    renderWith(<Controls entity={tv("on", { volume: 10 })} />);
    const slider = screen.getByRole("slider", { name: "Volume" });
    slider.focus();
    // jsdom doesn't move a range input on arrow keys, so apply the browser's change by hand.
    fireEvent.change(slider, { target: { value: "11" } });
    expect(calls).toHaveLength(0);
    await userEvent.keyboard("{ArrowRight}");
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]?.body).toEqual({ level: 11 });
  });
});

describe("slider follows the device", () => {
  it("moves when the entity's volume changes", () => {
    mockApi({});
    function Host() {
      const [volume, setVolume] = useState(10);
      return (
        <>
          <button type="button" onClick={() => setVolume(55)}>Elsewhere</button>
          <Controls entity={tv("on", { volume })} />
        </>
      );
    }
    renderWith(<Host />);
    expect(screen.getByRole("slider", { name: "Volume" })).toHaveValue("10");
    fireEvent.click(screen.getByRole("button", { name: "Elsewhere" }));
    expect(screen.getByRole("slider", { name: "Volume" })).toHaveValue("55");
  });

  it("snaps back after a refused command", async () => {
    mockApi({
      "POST /entities/media_player.living_tv/commands/volume_set": [409, { detail: "This device can't take commands right now." }],
    });
    renderWith(<Controls entity={tv("on", { volume: 10 })} />);
    const slider = screen.getByRole("slider", { name: "Volume" });
    fireEvent.change(slider, { target: { value: "40" } });
    fireEvent.pointerUp(slider);
    await screen.findByText("This device can't take commands right now.");
    expect(slider).toHaveValue("10");
  });
});
