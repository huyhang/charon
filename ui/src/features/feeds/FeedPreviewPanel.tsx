import { Loader2Icon, RssIcon, TriangleAlertIcon } from "lucide-react";
import { errorHintOf, errorMessage } from "@/api/errors";
import type { FeedPreview } from "@/api/types";
import { formatRelative } from "@/lib/format";
import { MatchChip } from "./MatchChip";

interface FeedPreviewPanelProps {
  preview: FeedPreview | undefined;
  error: unknown;
  loading: boolean;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** What Charon found at a feed's address, checked against the rules, before subscribing. */
export function FeedPreviewPanel({ preview, error, loading }: FeedPreviewPanelProps) {
  if (loading) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2Icon className="size-4 animate-spin" /> Reading the feed…
      </p>
    );
  }
  if (error) {
    return (
      <div role="alert" className="space-y-1 text-sm">
        <p className="flex items-start gap-2 text-destructive">
          <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" /> {errorMessage(error)}
        </p>
        {errorHintOf(error) && (
          <p className="pl-6 text-xs text-muted-foreground">{errorHintOf(error)}</p>
        )}
      </div>
    );
  }
  if (!preview) {
    return (
      <p className="text-sm text-muted-foreground">
        Paste the feed&apos;s address. Charon reads it and checks it against your rules before you
        subscribe.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <div className="space-y-0.5">
        <p className="flex items-center gap-2 font-medium">
          <RssIcon className="size-4 text-primary" /> {preview.title ?? "Untitled feed"}
        </p>
        <p className="text-xs text-muted-foreground">
          {plural(preview.item_count, "item")} with magnet links
          {preview.newest_published_at &&
            ` · newest ${formatRelative(preview.newest_published_at)}`}
          {preview.skipped_count > 0 && ` · ${preview.skipped_count} skipped (not magnet links)`}
        </p>
      </div>
      {preview.items.length > 0 && (
        <ul className="space-y-1.5" aria-label="Newest items">
          {preview.items.map((item) => (
            <li key={item.info_hash} className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate font-mono text-xs">{item.name}</span>
              <MatchChip item={item} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
