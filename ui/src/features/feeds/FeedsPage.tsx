import { CheckCheckIcon, Loader2Icon, PlusIcon, RefreshCwIcon, RssIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { errorMessage } from "@/api/errors";
import {
  allFeedItems,
  useFeedItems,
  useFeeds,
  useFeedSummary,
  useMarkAllFeedItemsSeen,
  useRefreshAllFeeds,
  useRefreshFeed,
} from "@/api/queries";
import type { Feed, FeedItem, MatchFilter } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import {
  canDownload,
  isHttpUrl,
  latestFirstSeen,
  MAX_FEED_ITEMS,
  parseMatchFilter,
} from "@/lib/feeds";
import { isListCapped } from "@/lib/jobs";
import { cn } from "@/lib/cn";
import { AddFeedDialog } from "./AddFeedDialog";
import { BulkBar } from "./BulkBar";
import { FeedList } from "./FeedList";
import { FeedProblems } from "./FeedProblems";
import { FeedSettingsSheet } from "./FeedSettingsSheet";
import { FeedSidebar } from "./FeedSidebar";
import { InboxToolbar } from "./InboxToolbar";
import { useFeedDownload } from "./useFeedDownload";
import { useFeedShortcuts } from "./useFeedShortcuts";
import { useInboxState } from "./useInboxState";
import { useMarkSeenOnLeave } from "./useMarkSeenOnLeave";
import { useUrlPaste } from "./useUrlPaste";

/** URL state: `?feed=` (one feed), `?match=` (which items), `?add=` (open "Add a feed"). */
function useInboxParams() {
  const [params, setParams] = useSearchParams();
  const set = useCallback(
    (key: string, value: string | null) =>
      setParams(
        (prev) => {
          if (value) prev.set(key, value);
          else prev.delete(key);
          return prev;
        },
        { replace: true },
      ),
    [setParams],
  );
  return {
    feedId: params.get("feed"),
    match: parseMatchFilter(params.get("match")),
    add: params.get("add"),
    set,
  };
}

function ListSkeleton() {
  return (
    <div className="space-y-2" aria-label="Loading items">
      {[0, 1, 2, 3].map((i) => (
        <Skeleton key={i} className="h-[66px] rounded-xl" />
      ))}
    </div>
  );
}

function focusRow(item: FeedItem | undefined) {
  if (!item) return;
  const row = document.querySelector<HTMLElement>(`[data-feed-item="${item.info_hash}"]`);
  row?.focus();
  row?.scrollIntoView?.({ block: "nearest" });
}

function ShortcutHints() {
  return (
    <p className="hidden items-center justify-center gap-3 pt-4 text-xs text-muted-foreground md:flex">
      <span>
        <Kbd>j</Kbd> <Kbd>k</Kbd> move
      </span>
      <span>
        <Kbd>x</Kbd> select
      </span>
      <span>
        <Kbd>d</Kbd> download
      </span>
      <span>
        <Kbd>⏎</Kbd> details
      </span>
      <span>
        <Kbd>/</Kbd> search
      </span>
    </p>
  );
}

export function FeedsPage() {
  const { feedId, match, add, set } = useInboxParams();
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search.trim(), 250);
  const [settingsId, setSettingsId] = useState<string | null>(null);
  const [adding, setAdding] = useState<{ url: string | null } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const feeds = useFeeds();
  const summary = useFeedSummary();
  const list = useFeedItems({ feedId, match, q });
  const items = allFeedItems(list.data);
  const state = useInboxState(items);
  const { start: download, pendingHashes } = useFeedDownload();
  const markAllSeen = useMarkAllFeedItemsSeen();
  const refreshAll = useRefreshAllFeeds();
  const refreshOne = useRefreshFeed();
  const unseenShown = useMemo(() => items.filter((i) => !i.seen).map((i) => i.info_hash), [items]);
  useMarkSeenOnLeave(unseenShown, `${feedId}|${match}|${q}`);

  const feedList = feeds.data ?? [];
  const settingsFeed = feedList.find((f) => f.id === settingsId) ?? null;
  const selectedFeed = feedList.find((f) => f.id === feedId) ?? null;

  // A feed that no longer exists (unsubscribed here or elsewhere) can't stay selected.
  const feedGone = feedId !== null && feeds.data !== undefined && selectedFeed === null;
  useEffect(() => {
    if (feedGone) set("feed", null);
  }, [feedGone, set]);
  useEffect(() => {
    if (add === null) return;
    setAdding({ url: isHttpUrl(add) ? add : null });
    set("add", null);
  }, [add, set]);
  useUrlPaste(useCallback((url: string) => setAdding({ url }), []));

  useFeedShortcuts({
    next: () => focusRow(state.move(1)),
    previous: () => focusRow(state.move(-1)),
    download: () => state.activeItem && canDownload(state.activeItem) && download(state.activeItem),
    select: () => state.activeItem && state.toggleSelected(state.activeItem.info_hash),
    expand: () => state.activeItem && state.toggleExpanded(state.activeItem.info_hash),
    search: () => searchRef.current?.focus(),
  });

  const onMarkAllSeen = () => {
    const upTo = latestFirstSeen(items) ?? new Date().toISOString();
    markAllSeen.mutate(
      { upTo, feedId, match, q },
      {
        onSuccess: (count) => toast(count ? `Marked ${count} as seen` : "Nothing new to mark"),
        onError: (error) =>
          toast.error("Couldn't mark items seen", { description: errorMessage(error) }),
      },
    );
  };

  const onRefresh = () => {
    if (selectedFeed) {
      refreshOne.mutate(selectedFeed.id, {
        onSuccess: (feed) =>
          feed.last_error
            ? toast.error(`${feed.name} can't be read`, { description: feed.last_error.message })
            : toast.success(`${feed.name} is up to date`),
        onError: (error) => toast.error("Couldn't refresh", { description: errorMessage(error) }),
      });
      return;
    }
    refreshAll.mutate(undefined, {
      onSuccess: (failing) =>
        failing
          ? toast.warning(`${failing} feed${failing === 1 ? "" : "s"} can't be read`)
          : toast.success("Feeds are up to date"),
      onError: (error) => toast.error("Couldn't refresh", { description: errorMessage(error) }),
    });
  };

  const refreshing = refreshAll.isPending || refreshOne.isPending;
  const unread = feedId ? (summary.data?.feeds[feedId] ?? 0) : (summary.data?.unread ?? 0);
  // The counts and the list are fetched separately, so either may know of a new item first.
  const anythingNew = unread > 0 || items.some((item) => !item.seen);
  const onCreated = (feed: Feed) => set("feed", feed.id);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Feeds"
        description="New torrents from your feeds, checked against your rules."
        actions={
          feedList.length > 0 && (
            <>
              <Button
                variant="ghost"
                size="sm"
                onClick={onMarkAllSeen}
                disabled={!anythingNew || markAllSeen.isPending}
              >
                <CheckCheckIcon /> <span className="hidden sm:inline">Mark all seen</span>
              </Button>
              <Button variant="outline" size="sm" onClick={onRefresh} disabled={refreshing}>
                <RefreshCwIcon className={cn(refreshing && "animate-spin")} />
                <span className="hidden sm:inline">Refresh</span>
              </Button>
              <Button size="sm" onClick={() => setAdding({ url: null })}>
                <PlusIcon /> Add feed
              </Button>
            </>
          )
        }
      />

      {feeds.isPending ? (
        <ListSkeleton />
      ) : feeds.isError ? (
        <ErrorState error={feeds.error} onRetry={() => feeds.refetch()} />
      ) : feedList.length === 0 ? (
        <EmptyState
          icon={RssIcon}
          title="No feeds yet"
          description="Subscribe to an RSS feed of magnet links to see what's new at a glance, and which of it your rules would file. Tip: paste a feed's address anywhere on this page."
          action={
            <Button onClick={() => setAdding({ url: null })}>
              <PlusIcon /> Add your first feed
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-6 md:grid-cols-[13rem_minmax(0,1fr)]">
          <aside className="md:sticky md:top-10 md:self-start">
            <FeedSidebar
              feeds={feedList}
              summary={summary.data}
              selectedId={feedId}
              onSelect={(id) => set("feed", id)}
              onSettings={(feed) => setSettingsId(feed.id)}
            />
          </aside>
          <section className="min-w-0 space-y-4" aria-label="Items">
            <FeedProblems
              feeds={selectedFeed ? [selectedFeed] : feedList}
              onSettings={(feed) => setSettingsId(feed.id)}
            />
            <InboxToolbar
              match={match}
              onMatch={(value: MatchFilter) => set("match", value === "all" ? null : value)}
              search={search}
              onSearch={setSearch}
              searchRef={searchRef}
              allSelected={state.allSelected}
              onSelectAll={state.selectAll}
              selectable={state.canSelect}
            />
            <BulkBar
              selected={state.selectedHashes}
              onClear={state.clearSelection}
              onKeep={state.keepSelected}
            />
            {list.isPending ? (
              <ListSkeleton />
            ) : list.isError ? (
              <ErrorState error={list.error} onRetry={() => list.refetch()} />
            ) : items.length === 0 ? (
              <EmptyState
                icon={RssIcon}
                title={q || match !== "all" ? "No items match" : "Nothing here yet"}
                description={
                  q || match !== "all"
                    ? "Try another filter, or clear the search."
                    : "New items appear here as the feed publishes them."
                }
              />
            ) : (
              <>
                <FeedList
                  items={items}
                  state={state}
                  pendingHashes={pendingHashes}
                  onDownload={download}
                />
                {list.hasNextPage && (
                  <div className="flex justify-center pt-2">
                    <Button
                      variant="outline"
                      onClick={() => list.fetchNextPage()}
                      disabled={list.isFetchingNextPage}
                    >
                      {list.isFetchingNextPage && <Loader2Icon className="animate-spin" />}
                      Load more
                    </Button>
                  </div>
                )}
                {isListCapped(list.data?.pages ?? [], MAX_FEED_ITEMS) && (
                  <p className="pt-2 text-center text-xs text-muted-foreground">
                    Showing the newest {MAX_FEED_ITEMS} items. Search or filter to find older ones.
                  </p>
                )}
                <ShortcutHints />
              </>
            )}
          </section>
        </div>
      )}

      <AddFeedDialog
        open={adding !== null}
        initialUrl={adding?.url}
        onOpenChange={(open) => !open && setAdding(null)}
        onCreated={onCreated}
      />
      <FeedSettingsSheet feed={settingsFeed} onClose={() => setSettingsId(null)} />
    </div>
  );
}
