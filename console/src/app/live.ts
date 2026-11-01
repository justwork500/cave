import { createContext, useContext, useSyncExternalStore } from "react";
import type { LiveFeed } from "../api/ws";

export const LiveContext = createContext<Pick<LiveFeed, "onState" | "onNotification" | "stop"> | null>(null);
export const useLive = () => useContext(LiveContext);

const NARROW = "(max-width: 600px)";

/** True on a phone-width screen; the menu bar folds into one button there. */
export function useNarrow(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(NARROW);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(NARROW).matches,
  );
}
