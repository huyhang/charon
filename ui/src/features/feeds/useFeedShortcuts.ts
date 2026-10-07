import { useEffect, useRef } from "react";
import { feedShortcut, hasOpenOverlay, isTypingTarget, type FeedShortcut } from "@/lib/keyboard";

export type FeedShortcutHandlers = Record<FeedShortcut, () => void>;

/** Whether a key press belongs to something else: an open dialog or menu, a field, a button. */
function belongsElsewhere(target: EventTarget | null, action: FeedShortcut): boolean {
  if (isTypingTarget(target) || hasOpenOverlay()) return true;
  if (!(target instanceof Element)) return false;
  // Enter on a focused button or link should press it, not expand the row.
  return action === "expand" && target.closest("button, a") !== null;
}

/** The inbox's single-key shortcuts (j/k, d, x, Enter, /), while the page is open. */
export function useFeedShortcuts(handlers: FeedShortcutHandlers): void {
  const latest = useRef(handlers);
  useEffect(() => {
    latest.current = handlers;
  });
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const action = feedShortcut(event);
      if (!action || belongsElsewhere(event.target, action)) return;
      event.preventDefault();
      latest.current[action]();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);
}
