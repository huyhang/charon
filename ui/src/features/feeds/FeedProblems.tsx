import { TriangleAlertIcon } from "lucide-react";
import type { Feed } from "@/api/types";
import { Button } from "@/components/ui/button";

interface FeedProblemsProps {
  feeds: Feed[];
  onSettings(feed: Feed): void;
}

/** A banner for each enabled feed that can't be read, with Charon's advice. */
export function FeedProblems({ feeds, onSettings }: FeedProblemsProps) {
  const failing = feeds.filter((feed) => feed.enabled && feed.last_error);
  if (failing.length === 0) return null;
  return (
    <div className="space-y-2">
      {failing.map((feed) => (
        <div
          key={feed.id}
          role="alert"
          className="flex items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm"
        >
          <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-destructive" />
          <div className="min-w-0 flex-1 space-y-0.5">
            <p>
              <span className="font-medium">{feed.name}</span> can&apos;t be read:{" "}
              {feed.last_error!.message}
            </p>
            {feed.last_error!.hint && (
              <p className="text-xs text-muted-foreground">{feed.last_error!.hint}</p>
            )}
          </div>
          <Button size="sm" variant="outline" onClick={() => onSettings(feed)}>
            Fix
          </Button>
        </div>
      ))}
    </div>
  );
}
