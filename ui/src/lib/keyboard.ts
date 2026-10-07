/** Whether a key press is meant for a text field rather than a global shortcut. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

// Radix renders these only while open, and portals some (e.g. a select's listbox) out of
// the dialog that opened them, so page-wide keys and pastes check the whole document.
const OVERLAYS = "[role=dialog], [role=alertdialog], [role=menu], [role=listbox]";

/** Whether a dialog, sheet, menu or listbox is open, which then owns keys and pastes. */
export function hasOpenOverlay(root: ParentNode = document): boolean {
  return root.querySelector(OVERLAYS) !== null;
}

export function isPaletteShortcut(
  event: Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey">,
): boolean {
  return event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey);
}

export type FeedShortcut = "next" | "previous" | "download" | "select" | "expand" | "search";

// Arrow keys are left alone, so they keep scrolling the page.
const FEED_KEYS: Record<string, FeedShortcut> = {
  j: "next",
  k: "previous",
  d: "download",
  x: "select",
  Enter: "expand",
  o: "expand",
  "/": "search",
};

/** The feed inbox's single-key shortcuts; none fire with a modifier held. */
export function feedShortcut(
  event: Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "altKey">,
): FeedShortcut | null {
  if (event.metaKey || event.ctrlKey || event.altKey) return null;
  return FEED_KEYS[event.key] ?? null;
}
