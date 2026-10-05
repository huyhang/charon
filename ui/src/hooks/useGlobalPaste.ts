import { useEffect } from "react";
import { isTypingTarget } from "@/lib/keyboard";
import { findMagnet } from "@/lib/magnet";

/** Calls `onMagnet` when a magnet link is pasted anywhere outside a text field. */
export function useGlobalMagnetPaste(onMagnet: (magnet: string) => void): void {
  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => {
      if (isTypingTarget(event.target)) return;
      const magnet = findMagnet(event.clipboardData?.getData("text") ?? "");
      if (magnet) {
        event.preventDefault();
        onMagnet(magnet);
      }
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, [onMagnet]);
}
