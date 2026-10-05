import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/api/errors";

type Writer = (text: string) => Promise<void>;
type ErrorReporter = (error: unknown) => void;

export const COPY_UNAVAILABLE =
  "Copying isn't available here. Select the text and copy it yourself.";

/**
 * Copies with the Clipboard API where it exists. Browsers only offer it on secure pages, and
 * Charon is usually opened over plain HTTP on the LAN, so fall back to copying a selection.
 */
export async function writeClipboard(text: string, doc: Document = document): Promise<void> {
  const clipboard = doc.defaultView?.navigator.clipboard;
  if (clipboard) return clipboard.writeText(text);
  copySelection(text, doc);
}

function copySelection(text: string, doc: Document): void {
  const previous = doc.activeElement instanceof HTMLElement ? doc.activeElement : null;
  const area = doc.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  // Inside an open dialog, whose focus trap would otherwise pull focus back before copying.
  (previous?.closest('[role="dialog"], [role="alertdialog"]') ?? doc.body).append(area);
  area.focus();
  area.select();
  const copied = doc.execCommand("copy");
  area.remove();
  previous?.focus();
  if (!copied) throw new Error(COPY_UNAVAILABLE);
}

const toastError: ErrorReporter = (error) =>
  toast.error("Couldn't copy", { description: errorMessage(error) });

/** Copies text and reports `copied` for a moment, for a check-mark affordance. */
export function useCopy(write: Writer = writeClipboard, onError = toastError, resetMs = 1500) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), resetMs);
    return () => clearTimeout(timer);
  }, [copied, resetMs]);

  const copy = useCallback(
    async (text: string) => {
      try {
        await write(text);
        setCopied(true);
      } catch (error) {
        onError(error);
      }
    },
    [write, onError],
  );

  return { copied, copy };
}
