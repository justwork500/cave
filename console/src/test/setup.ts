import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom has no matchMedia; a wide screen is the default, tests narrow it with setNarrow
window.matchMedia ??= (q: string) =>
  ({ matches: false, media: q, addEventListener: () => undefined, removeEventListener: () => undefined }) as never;

// Fluent's MessageBar measures itself; jsdom has no layout, so a no-op observer is enough
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

afterEach(() => cleanup());
