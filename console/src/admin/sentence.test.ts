import Ajv from "ajv";
import { parse } from "yaml";
import { describe, expect, it } from "vitest";
import schemaText from "../../../schemas/automation.json?raw";
import { RECIPES } from "./recipes";
import { fromYaml, toYaml } from "./sentence";

const UPS = `automation:
  id: ups-on-battery
  name: UPS on battery — alert and shut down lab
  mode: single
  triggers:
    - type: state
      entity: binary_sensor.ups_on_battery
      to: "on"
      for: "00:02:00"
  conditions:
    - type: numeric_state
      entity: sensor.ups_battery_runtime_min
      below: 15
  actions:
    - type: notify
      title: Power outage
      message: "UPS on battery. {{ states('sensor.ups_battery_runtime_min') }} min left."
    - type: sequence
      ref: sequence.lab_safe_shutdown
      with:
        grace_seconds: 120
`;

const schema: object = JSON.parse(schemaText);
const validate = new Ajv({ strict: false, validateFormats: false }).compile(schema);

const roundTrips = (text: string) => {
  const s = fromYaml(text);
  expect(s).not.toBeNull();
  expect(parse(toYaml(s!), { version: "1.1" })).toEqual(parse(text, { version: "1.1" }));
};

describe("sentence <-> YAML", () => {
  it("round-trips the UPS example", () => roundTrips(UPS));

  it("keeps on/off as strings, so the server's YAML 1.1 doesn't read them as true/false", () => {
    const out = toYaml(fromYaml(UPS)!);
    expect(out).toMatch(/to: "on"/);
  });

  it("gives null for anything the Simple view can't show", () => {
    expect(fromYaml(UPS.replace("    - type: sequence\n", "    - type: choose\n      options: []\n    - type: sequence\n")))
      .toBeNull();
    expect(fromYaml(UPS.replace("  mode: single\n", "  mode: single\n  # keep this comment\n"))).toBeNull();
    expect(fromYaml("automation: [")).toBeNull();
    expect(fromYaml(UPS.replace("  conditions:\n", "  conditions:\n    - type: template\n      value: x\n")))
      .toBeNull();
  });

  it("gives null when a plain value means different things to the server and to the browser", () => {
    // yaml (1.1) reads 07:00 as 420; the server's PyYAML keeps "07:00". Showing either would be a guess.
    expect(fromYaml(UPS.replace('for: "00:02:00"', "for: 00:02:00"))).toBeNull();
    expect(fromYaml(UPS.replace('to: "on"', "to: on"))).toBeNull();
    expect(fromYaml(UPS.replace("below: 15", "below: 0700"))).toBeNull(); // octal 448 to both: still a surprise
    expect(fromYaml(UPS.replace("below: 15", "below: 20"))).not.toBeNull(); // a plain number is fine
  });

  it("gives null for a time or message that isn't text", () => {
    expect(fromYaml(UPS.replace('to: "on"', "to: 5"))).toBeNull();
  });

  it("notices comments anywhere, including on lists", () => {
    expect(fromYaml(UPS.replace("  triggers:\n", "  triggers: # why\n"))).toBeNull();
    expect(fromYaml(UPS.replace("  actions:\n", "  actions:\n    # first we tell people\n"))).toBeNull();
  });

  it.each(RECIPES.filter((r) => !r.later).map((r) => [r.id, r] as const))("recipe %s builds valid simple YAML",
    (_, recipe) => {
      const docs = recipe.build(Object.fromEntries(recipe.blanks.map((b) => [b.id, b.example])));
      expect(docs.length).toBeGreaterThan(0);
      for (const doc of docs) {
        const text = toYaml(doc);
        expect(validate(parse(text, { version: "1.1" })), JSON.stringify(validate.errors)).toBe(true);
        roundTrips(text);
      }
    });

  it("lists presence recipes as coming later", () => {
    expect(RECIPES.filter((r) => r.later).map((r) => r.title)).toEqual([
      "Everything off when the last person leaves", "Tell me if a door opens while I'm away"]);
  });
});
