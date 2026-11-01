import { describe, expect, it } from "vitest";
import { contrast, themes } from "./theme";

describe("themes", () => {
  it.each(Object.entries(themes))("%s: brand text and links meet 4.5:1 on their surfaces", (_name, t) => {
    expect(contrast(t.colorBrandForegroundLink, t.colorNeutralBackground1)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t.colorNeutralForeground1, t.colorNeutralBackground1)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t.colorNeutralForegroundOnBrand, t.colorBrandBackground)).toBeGreaterThanOrEqual(4.5);
  });

  it("computes contrast like WCAG", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 0);
    expect(contrast("#777777", "#ffffff")).toBeCloseTo(4.48, 1);
  });
});
