import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";
import { toast } from "sonner";
import { useClient } from "@/api/context";
import { errorMessage } from "@/api/errors";
import { queryKeys } from "@/api/queries";

interface Scheduled {
  view: string;
  hashes: string[];
  timer: ReturnType<typeof setTimeout>;
}

/**
 * Marks the unseen items the inbox showed as seen once you move on: to another feed, filter or
 * search (`view`), off the page, or away from the tab. Items it never showed, because a filter
 * hid them or they weren't loaded yet, stay new.
 */
export function useMarkSeenOnLeave(shown: readonly string[], view: string): void {
  const client = useClient();
  const queryClient = useQueryClient();
  // Shown in the current view since they were last marked.
  const unmarked = useRef(new Set<string>());
  const scheduled = useRef<Scheduled | null>(null);

  useEffect(() => {
    for (const hash of shown) unmarked.current.add(hash);
  }, [shown]);

  const take = useCallback(() => {
    const hashes = [...unmarked.current];
    unmarked.current.clear();
    return hashes;
  }, []);

  const send = useCallback(
    (hashes: string[]) => {
      if (hashes.length === 0) return;
      client.markFeedItemsSeen(hashes).then(
        // Only the badge: rows still on screen keep their "new" look until the list reloads.
        () => queryClient.invalidateQueries({ queryKey: queryKeys.feedSummary }),
        (error) => toast.error("Couldn't mark items as seen", { description: errorMessage(error) }),
      );
    },
    [client, queryClient],
  );

  // When the view changes or the page closes, the outgoing view's items are taken at once and
  // sent a moment later: React's StrictMode (in dev builds) unmounts and remounts once on
  // mount, and a remount of the same view takes them back instead.
  useEffect(() => {
    const pending = scheduled.current;
    if (pending?.view === view) {
      clearTimeout(pending.timer);
      for (const hash of pending.hashes) unmarked.current.add(hash);
    }
    scheduled.current = null;
    return () => {
      const hashes = take();
      scheduled.current = { view, hashes, timer: setTimeout(() => send(hashes), 0) };
    };
  }, [view, take, send]);

  useEffect(() => {
    const markShown = () => send(take());
    const onHidden = () => document.visibilityState === "hidden" && markShown();
    document.addEventListener("visibilitychange", onHidden);
    window.addEventListener("pagehide", markShown);
    return () => {
      document.removeEventListener("visibilitychange", onHidden);
      window.removeEventListener("pagehide", markShown);
    };
  }, [take, send]);
}
