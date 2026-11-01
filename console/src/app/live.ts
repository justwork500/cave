import { createContext, useContext, useSyncExternalStore } from "react";
import type { LiveFeed } from "../api/ws";

export const LiveContext = createContext<Pick<LiveFeed, "onState" | "onNotification" | "stop"> | null>(null);
export const useLive = () => useContext(LiveContext);

const NARROW = "(max-width: 600px)";
const FOLDED = "(max-width: 1100px)";

function useMedia(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(query);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(query).matches,
  );
}

/** True on a phone-width screen: dashboard cards go to one column. */
export const useNarrow = () => useMedia(NARROW);
/** True up to tablet width: the sidebar folds into a top bar with a menu sheet. */
export const useFolded = () => useMedia(FOLDED);
