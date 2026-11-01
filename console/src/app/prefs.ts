/** Per-browser conveniences. Storage can be missing or blocked, so every access is guarded. */
import { createContext, useContext } from "react";
import type { ThemeName } from "./theme";

export function load(key: string): string | null {
  try {
    return localStorage.getItem(`cave.${key}`);
  } catch {
    return null;
  }
}

export function save(key: string, value: string): void {
  try {
    localStorage.setItem(`cave.${key}`, value);
  } catch {
    // private window or blocked storage: the choice lasts until the tab closes
  }
}

export function initialTheme(): ThemeName {
  const saved = load("theme");
  if (saved === "light" || saved === "dark" || saved === "contrast") return saved;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export const ThemeContext = createContext<{ theme: ThemeName; setTheme: (t: ThemeName) => void }>({
  theme: "light",
  setTheme: () => undefined,
});
export const useTheme = () => useContext(ThemeContext);
