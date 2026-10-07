import { useEffect } from "react";
import { isHttpUrl } from "@/lib/feeds";
import { hasOpenOverlay, isTypingTarget } from "@/lib/keyboard";

/** The pasted text, if it is meant for the page itself rather than a field or open dialog. */
function pastedOnPage(event: ClipboardEvent): string | null {
  if (event.defaultPrevented || isTypingTarget(event.target) || hasOpenOverlay()) return null;
  return event.clipboardData?.getData("text").trim() ?? null;
}

/** Calls `onUrl` when an http(s) address, and nothing else, is pasted onto the page. */
export function useUrlPaste(onUrl: (url: string) => void): void {
  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => {
      const text = pastedOnPage(event);
      if (text === null || !isHttpUrl(text)) return;
      event.preventDefault();
      onUrl(text);
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, [onUrl]);
}
