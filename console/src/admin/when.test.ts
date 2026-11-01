import { describe, expect, it } from "vitest";
import { when } from "./Page";

describe("when", () => {
  const now = new Date(2026, 10, 1, 9, 12);
  it("says times the way people do", () => {
    expect(when(new Date(2026, 10, 1, 7, 37).toISOString(), now)).toBe("07:37");
    expect(when(new Date(2026, 9, 31, 21, 10).toISOString(), now)).toBe("Yesterday 21:10");
    expect(when(new Date(2026, 9, 23, 14, 2).toISOString(), now)).toBe("23 Oct, 14:02");
    expect(when(new Date(2025, 9, 23, 14, 2).toISOString(), now)).toBe("23 Oct 2025, 14:02");
    expect(when(null, now)).toBe("");
  });
});
