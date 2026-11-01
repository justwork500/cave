import axe from "axe-core";
import { expect } from "vitest";

/** Fails the test when axe finds any accessibility violation in the rendered container. */
export async function expectAccessible(container: Element): Promise<void> {
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  const problems = result.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`);
  expect(problems.join("; ")).toBe("");
}
