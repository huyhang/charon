/** Whether a key press is meant for a text field rather than a global shortcut. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

export function isPaletteShortcut(
  event: Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey">,
): boolean {
  return event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey);
}
