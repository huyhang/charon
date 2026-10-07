import {
  CalendarIcon,
  FolderIcon,
  SparklesIcon,
  TagIcon,
  TriangleAlertIcon,
  WandSparklesIcon,
  ZapIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import type { FeedItem } from "@/api/types";
import { NameDiff } from "@/components/NameDiff";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/cn";
import { formatBytes, formatDateTime, formatRelative } from "@/lib/format";
import { ItemActions } from "./ItemActions";
import { MatchChip } from "./MatchChip";

interface FeedItemRowProps {
  item: FeedItem;
  /** Whether Tab lands on this row (one row in the list at a time). */
  tabStop: boolean;
  expanded: boolean;
  selected: boolean;
  pending: boolean;
  onToggleExpanded(): void;
  onToggleSelected(): void;
  onDownload(ruleId?: string | null): void;
  onFocus(): void;
}

function Detail({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-xs text-muted-foreground [&>svg]:mt-0.5 [&>svg]:size-3.5 [&>svg]:shrink-0">
      {icon}
      <div className="min-w-0 flex-1 break-all">{children}</div>
    </div>
  );
}

function folderOf(path: string, name: string): string {
  return path.slice(0, path.length - name.length - 1) || "/";
}

/** What happens to the item, and what you can do about it. */
function Expanded({ item }: { item: FeedItem }) {
  return (
    <div className="space-y-2.5 border-t pt-3">
      {item.match && (
        <>
          <Detail icon={<WandSparklesIcon className="text-primary" />}>
            Filed by <span className="font-medium text-foreground">{item.match.rule_name}</span>
          </Detail>
          <NameDiff before={item.name} after={item.match.new_name} className="pl-5.5" />
          <Detail icon={<FolderIcon />}>
            <span className="font-mono">
              {folderOf(item.match.final_path, item.match.new_name)}
            </span>
          </Detail>
        </>
      )}
      {item.match_error && (
        <Detail icon={<TriangleAlertIcon className="text-warning" />}>
          <span className="text-warning">{item.match_error.message}</span>
          {item.match_error.hint && <span className="block">{item.match_error.hint}</span>}
        </Detail>
      )}
      {!item.match && !item.match_error && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">
            No rule matches this name, so it would stay in the download folder.
          </p>
          <Button asChild size="sm" variant="outline" className="h-7">
            <Link to={`/rules?new=1&sample=${encodeURIComponent(item.name)}`}>
              <SparklesIcon /> Create rule from this
            </Link>
          </Button>
        </div>
      )}
      {item.auto_error && (
        <Detail icon={<TriangleAlertIcon className="text-destructive" />}>
          Auto-download couldn&apos;t start it: {item.auto_error}
        </Detail>
      )}
      {item.title !== item.name && <Detail icon={<TagIcon />}>Listed as “{item.title}”</Detail>}
      <Detail icon={<CalendarIcon />}>
        Published {formatDateTime(item.published_at)}
        {item.published_estimated && " (the feed gave no date; this is when Charon first saw it)"}
      </Detail>
    </div>
  );
}

export function FeedItemRow({
  item,
  tabStop,
  expanded,
  selected,
  pending,
  onToggleExpanded,
  onToggleSelected,
  onDownload,
  onFocus,
}: FeedItemRowProps) {
  return (
    <li
      data-feed-item={item.info_hash}
      tabIndex={tabStop ? 0 : -1}
      aria-label={item.name}
      aria-expanded={expanded}
      onFocus={onFocus}
      onClick={onToggleExpanded}
      onKeyDown={(event) => {
        if (event.key === " " && event.target === event.currentTarget) {
          event.preventDefault();
          onToggleExpanded();
        }
      }}
      className={cn(
        "group cursor-pointer space-y-3 rounded-xl border bg-card/70 px-3 py-3 transition outline-none hover:border-primary/30 hover:bg-card focus-visible:ring-[3px] focus-visible:ring-ring sm:px-4",
        selected && "border-primary/40 bg-primary/[0.04]",
        item.job?.status === "done" && "opacity-75",
      )}
    >
      {/* On phones the chip and actions wrap below the name, so the name gets the full width. */}
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2 sm:flex-nowrap">
        <div className="flex h-5 items-center gap-2" onClick={(event) => event.stopPropagation()}>
          <Checkbox
            checked={selected}
            onCheckedChange={onToggleSelected}
            aria-label={`Select ${item.name}`}
          />
        </div>
        <div className="min-w-0 flex-1 basis-[calc(100%-1.75rem)] space-y-1 sm:basis-0">
          <div className="flex items-center gap-2">
            {!item.seen && (
              <span
                role="img"
                className="size-2 shrink-0 rounded-full bg-primary"
                aria-label="New"
              />
            )}
            <h3 className="min-w-0 flex-1 truncate font-mono text-sm font-medium">{item.name}</h3>
          </div>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span>{item.feeds.map((feed) => feed.name).join(" · ") || "No feed"}</span>
            <span aria-hidden>·</span>
            <span title={formatDateTime(item.published_at)}>
              {item.published_estimated && "≈ "}
              {formatRelative(item.published_at)}
            </span>
            {item.size_bytes != null && (
              <>
                <span aria-hidden>·</span>
                <span>{formatBytes(item.size_bytes)}</span>
              </>
            )}
            {item.auto_downloaded && (
              <Badge tone="info" className="py-0">
                <ZapIcon /> Auto
              </Badge>
            )}
          </p>
        </div>
        <div className="ml-7 flex flex-wrap items-center gap-2 sm:ml-0 sm:shrink-0 sm:flex-nowrap">
          <MatchChip item={item} />
          <ItemActions item={item} pending={pending} onDownload={onDownload} />
        </div>
      </div>
      {expanded && <Expanded item={item} />}
    </li>
  );
}
