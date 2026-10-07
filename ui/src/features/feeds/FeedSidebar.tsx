import { InboxIcon, Settings2Icon } from "lucide-react";
import type { Feed, FeedSummary } from "@/api/types";
import { cn } from "@/lib/cn";
import { feedHealth, HEALTH_META } from "@/lib/feeds";

interface FeedSidebarProps {
  feeds: Feed[];
  summary: FeedSummary | undefined;
  selectedId: string | null;
  onSelect(id: string | null): void;
  onSettings(feed: Feed): void;
}

function Unread({ count }: { count: number | undefined }) {
  if (!count) return null;
  return (
    <span className="rounded-full bg-primary/15 px-1.5 text-[11px] font-medium text-primary tabular-nums">
      {count > 99 ? "99+" : count}
    </span>
  );
}

/** What a screen reader says for a sidebar entry, e.g. "TV, healthy, 3 new". */
function describe(name: string, unread: number | undefined): string {
  return unread ? `${name}, ${unread} new` : name;
}

const itemClass = (active: boolean) =>
  cn(
    "flex h-9 min-w-0 shrink-0 items-center gap-2 rounded-lg px-2.5 text-sm text-muted-foreground transition hover:bg-accent/60 hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:outline-none",
    active && "bg-accent text-foreground",
  );

/** Every feed with its unread count and health; a row of chips on phones. */
export function FeedSidebar({
  feeds,
  summary,
  selectedId,
  onSelect,
  onSettings,
}: FeedSidebarProps) {
  return (
    <nav
      aria-label="Feeds"
      className="-mx-4 flex gap-1 overflow-x-auto px-4 pb-1 md:mx-0 md:flex-col md:overflow-visible md:px-0"
    >
      <button
        type="button"
        className={itemClass(selectedId === null)}
        aria-current={selectedId === null ? "page" : undefined}
        aria-label={describe("All feeds", summary?.unread)}
        onClick={() => onSelect(null)}
      >
        <InboxIcon className="size-4 shrink-0" />
        <span className="flex-1 text-left whitespace-nowrap">All feeds</span>
        <Unread count={summary?.unread} />
      </button>
      {feeds.map((feed) => {
        const health = feedHealth(feed);
        const { label, dot } = HEALTH_META[health];
        return (
          <div key={feed.id} className="group/feed relative flex shrink-0 items-center md:w-full">
            <button
              type="button"
              className={cn(itemClass(selectedId === feed.id), "w-full pr-8")}
              aria-current={selectedId === feed.id ? "page" : undefined}
              aria-label={describe(`${feed.name}, ${label.toLowerCase()}`, summary?.feeds[feed.id])}
              onClick={() => onSelect(feed.id)}
            >
              <span
                className={cn("size-2 shrink-0 rounded-full", dot)}
                title={feed.last_error ? `${label}: ${feed.last_error.message}` : label}
              />
              <span className="min-w-0 flex-1 truncate text-left whitespace-nowrap">
                {feed.name}
              </span>
              <Unread count={summary?.feeds[feed.id]} />
            </button>
            <button
              type="button"
              className="absolute right-1 rounded-md p-1 text-muted-foreground opacity-60 transition group-hover/feed:opacity-100 hover:bg-background hover:text-foreground focus-visible:opacity-100 focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:outline-none"
              aria-label={`Settings for ${feed.name}`}
              onClick={() => onSettings(feed)}
            >
              <Settings2Icon className="size-3.5" />
            </button>
          </div>
        );
      })}
    </nav>
  );
}
