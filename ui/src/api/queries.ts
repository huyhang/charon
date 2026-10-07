import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useMutationState,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { useEffect } from "react";
import {
  nextPageCursor,
  PAGE_SIZE,
  pollInterval,
  statusesFor,
  summaryPollInterval,
  type FilterId,
} from "@/lib/jobs";
import { FEED_PAGE_SIZE, feedPollInterval, MAX_FEED_ITEMS } from "@/lib/feeds";
import { useClient } from "./context";
import { isApiError } from "./errors";
import type {
  FeedItemList,
  FeedSpec,
  FeedUpdate,
  Job,
  JobList,
  ListFeedItemsQuery,
  MarkAllSeenQuery,
  PreviewRequest,
  Principal,
  Role,
  Rule,
  RuleUpdate,
} from "./types";

export const queryKeys = {
  downloads: ["downloads"] as const,
  downloadLists: ["downloads", "list"] as const,
  downloadList: (filter: FilterId) => ["downloads", "list", filter] as const,
  downloadSummary: ["downloads", "summary"] as const,
  recentJobs: ["downloads", "recent"] as const,
  job: (id: string | undefined) => ["downloads", "job", id] as const,
  rules: ["rules"] as const,
  apiKeys: ["api-keys"] as const,
  health: ["health"] as const,
  session: ["auth", "me"] as const,
  roots: ["destinations", "roots"] as const,
  folders: (path: string) => ["destinations", "folders", path] as const,
  preview: (request: PreviewRequest) => ["preview", request] as const,
  feeds: ["feeds"] as const,
  feedList: ["feeds", "list"] as const,
  feedItems: ["feeds", "items"] as const,
  feedItemList: (query: ListFeedItemsQuery) => ["feeds", "items", query] as const,
  feedSummary: ["feeds", "summary"] as const,
  feedPreview: (url: string) => ["feed-preview", url] as const,
};

const FEEDS_POLL_MS = 30000;

const HEALTH_POLL_MS = 15000;
export const SESSION_CHECK_MS = 30000;

type JobPages = { pages: JobList[] };

export function allJobs(data: JobPages | undefined): Job[] {
  return data?.pages.flatMap((page) => page.items) ?? [];
}

/** Finds a job in any cached download list, so a drawer can open without a fetch. */
export function findCachedJob(client: QueryClient, id: string): Job | undefined {
  return client
    .getQueriesData<JobPages>({ queryKey: queryKeys.downloadLists })
    .flatMap(([, data]) => allJobs(data))
    .find((job) => job.id === id);
}

export function useDownloads(filter: FilterId) {
  const client = useClient();
  return useInfiniteQuery({
    queryKey: queryKeys.downloadList(filter),
    queryFn: ({ pageParam }) =>
      client.listDownloads({ status: statusesFor(filter), limit: PAGE_SIZE, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (_last, pages) => nextPageCursor(pages),
    refetchInterval: (query) => pollInterval(allJobs(query.state.data)),
  });
}

/** Totals across every job, so the stats don't depend on how much of the list is loaded. */
export function useDownloadSummary() {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.downloadSummary,
    queryFn: () => client.downloadSummary(),
    refetchInterval: (query) => summaryPollInterval(query.state.data),
  });
}

/** The newest few jobs, fetched only while `enabled` (e.g. the command palette is open). */
export function useRecentJobs(enabled: boolean, limit = 8) {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.recentJobs,
    queryFn: () => client.listDownloads({ limit }),
    enabled,
  });
}

export function useJob(id: string | undefined) {
  const client = useClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: queryKeys.job(id),
    queryFn: () => client.getDownload(id!),
    enabled: id !== undefined,
    initialData: () => (id ? findCachedJob(queryClient, id) : undefined),
    refetchInterval: (query) => pollInterval(query.state.data ? [query.state.data] : []),
  });
}

function useInvalidate(...keys: readonly (readonly unknown[])[]) {
  const queryClient = useQueryClient();
  return () => Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
}

export function useSubmitDownload() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.downloads);
  return useMutation({
    mutationFn: ({ magnet, ruleId }: { magnet: string; ruleId?: string | null }) =>
      client.submitDownload(magnet, ruleId),
    onSuccess,
  });
}

export function useCancelDownload() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.downloads);
  return useMutation({ mutationFn: (id: string) => client.cancelDownload(id), onSuccess });
}

export function useRetryDownload() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.downloads);
  return useMutation({ mutationFn: (id: string) => client.retryDownload(id), onSuccess });
}

export function useRules() {
  const client = useClient();
  return useQuery({ queryKey: queryKeys.rules, queryFn: () => client.listRules() });
}

export function useSaveRule() {
  const client = useClient();
  // Feed items show which rule matches, so they change with the rules.
  const onSuccess = useInvalidate(queryKeys.rules, queryKeys.feedItems);
  const reloadRules = useInvalidate(queryKeys.rules);
  return useMutation({
    mutationFn: ({ id, spec }: { id?: string; spec: RuleUpdate }) =>
      id ? client.updateRule(id, spec) : client.createRule(spec),
    onSuccess,
    // Someone else changed the rule: load its latest version, so opening it again can save.
    onError: (error) => (isApiError(error, 409) ? reloadRules() : undefined),
  });
}

export function useDeleteRule() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.rules, queryKeys.feedItems);
  return useMutation({ mutationFn: (id: string) => client.deleteRule(id), onSuccess });
}

/** Saves a new rule order in one request, showing the new order immediately. */
export function useReorderRules() {
  const client = useClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ordered: Rule[]) => client.reorderRules(ordered.map((rule) => rule.id)),
    onMutate: async (ordered) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.rules });
      const previous = queryClient.getQueryData<Rule[]>(queryKeys.rules);
      queryClient.setQueryData(queryKeys.rules, ordered);
      return { previous };
    },
    onError: (_error, _ordered, context) =>
      queryClient.setQueryData(queryKeys.rules, context?.previous),
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.rules }),
        queryClient.invalidateQueries({ queryKey: queryKeys.feedItems }),
      ]),
  });
}

export function usePreview(request: PreviewRequest | null) {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.preview(request ?? { name: "" }),
    queryFn: () => client.previewRule(request!),
    enabled: request !== null,
    placeholderData: keepPreviousData,
    retry: false,
    staleTime: 5000,
  });
}

export function useApiKeys(enabled = true) {
  const client = useClient();
  return useQuery({ queryKey: queryKeys.apiKeys, queryFn: () => client.listApiKeys(), enabled });
}

export function useIssueKey() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.apiKeys);
  return useMutation({
    mutationFn: ({ name, role }: { name: string; role: Role }) => client.issueApiKey(name, role),
    onSuccess,
  });
}

export function useRevokeKey() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.apiKeys);
  return useMutation({ mutationFn: (id: string) => client.revokeApiKey(id), onSuccess });
}

/**
 * Re-checks the key now and then and when the tab regains focus, so a revoked key signs out
 * (through the query client's 401 handler) even on pages that poll nothing. `/health` can't
 * tell: it needs no key.
 */
export function useSessionCheck(principal: Principal) {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.session,
    queryFn: () => client.me(),
    initialData: principal,
    staleTime: SESSION_CHECK_MS,
    refetchInterval: SESSION_CHECK_MS,
  });
}

export function useHealth() {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => client.health(),
    refetchInterval: HEALTH_POLL_MS,
    retry: false,
  });
}

export function useDestinationRoots() {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.roots,
    queryFn: () => client.destinationRoots(),
    staleTime: 60000,
  });
}

export function useFolders(path: string | null) {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.folders(path ?? ""),
    queryFn: () => client.destinationFolders(path!),
    enabled: path !== null,
    retry: false,
  });
}

type FeedItemPages = { pages: FeedItemList[] };

export function allFeedItems(data: FeedItemPages | undefined) {
  return data?.pages.flatMap((page) => page.items) ?? [];
}

export function useFeeds() {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.feedList,
    queryFn: () => client.listFeeds(),
    refetchInterval: FEEDS_POLL_MS,
  });
}

/** Unseen items, for the nav badge. */
export function useFeedSummary() {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.feedSummary,
    queryFn: () => client.feedSummary(),
    refetchInterval: FEEDS_POLL_MS,
  });
}

export function useFeedItems(query: Omit<ListFeedItemsQuery, "cursor" | "limit">) {
  const client = useClient();
  const queryClient = useQueryClient();
  const items = useInfiniteQuery({
    queryKey: queryKeys.feedItemList(query),
    queryFn: ({ pageParam }) =>
      client.listFeedItems({ ...query, limit: FEED_PAGE_SIZE, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (_last, pages) => nextPageCursor(pages, MAX_FEED_ITEMS),
    refetchInterval: (q) => feedPollInterval(allFeedItems(q.state.data)),
    placeholderData: keepPreviousData,
  });
  // Charon's poller adds items in the background, so each fresh list may hold new ones: the
  // unread counts (badge, sidebar, "Mark all seen") are refreshed with it to agree with it.
  useEffect(() => {
    if (items.dataUpdatedAt)
      void queryClient.invalidateQueries({ queryKey: queryKeys.feedSummary });
  }, [items.dataUpdatedAt, queryClient]);
  return items;
}

export function useFeedPreview(url: string | null) {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.feedPreview(url ?? ""),
    queryFn: () => client.previewFeed(url!),
    enabled: url !== null,
    retry: false,
    staleTime: 30000,
  });
}

export function useCreateFeed() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.feeds);
  return useMutation({ mutationFn: (spec: FeedSpec) => client.createFeed(spec), onSuccess });
}

export function useUpdateFeed() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.feeds);
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: FeedUpdate }) =>
      client.updateFeed(id, changes),
    onSuccess,
  });
}

export function useDeleteFeed() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.feeds);
  return useMutation({ mutationFn: (id: string) => client.deleteFeed(id), onSuccess });
}

export function useRefreshFeed() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.feeds);
  return useMutation({ mutationFn: (id: string) => client.refreshFeed(id), onSuccess });
}

/** Refreshes every enabled feed on the server; resolves to how many couldn't be read. */
export function useRefreshAllFeeds() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.feeds);
  return useMutation({
    mutationFn: async () => {
      const feeds = await client.refreshAllFeeds();
      return feeds.filter((feed) => feed.enabled && feed.last_error).length;
    },
    onSuccess,
  });
}

export function useRevealFeedUrl() {
  const client = useClient();
  return useMutation({ mutationFn: (id: string) => client.revealFeedUrl(id) });
}

/** "Mark all seen" for a view of the inbox: items the view hides stay new. */
export function useMarkAllFeedItemsSeen() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.feedSummary, queryKeys.feedItems);
  return useMutation({
    mutationFn: (view: MarkAllSeenQuery) => client.markAllFeedItemsSeen(view),
    onSuccess,
  });
}

const DOWNLOAD_FEED_ITEM = ["feeds", "download"] as const;
type FeedItemDownload = { infoHash: string; ruleId?: string | null };

export function useDownloadFeedItem() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.feedItems, queryKeys.downloads);
  return useMutation({
    mutationKey: DOWNLOAD_FEED_ITEM,
    mutationFn: ({ infoHash, ruleId }: FeedItemDownload) =>
      client.downloadFeedItem(infoHash, ruleId),
    onSuccess,
  });
}

/** The info hashes of every single-item download still in flight, however many there are. */
export function usePendingFeedDownloads(): ReadonlySet<string> {
  const hashes = useMutationState({
    filters: { mutationKey: DOWNLOAD_FEED_ITEM, status: "pending" },
    select: (mutation) => (mutation.state.variables as FeedItemDownload).infoHash,
  });
  return new Set(hashes);
}

export interface BulkDownloadResult {
  started: number;
  already: number;
  /** The items that couldn't start, with why. */
  failed: { infoHash: string; error: unknown }[];
}

/** Downloads several items; resolves to how many started, and which failed and why. */
export function useDownloadFeedItems() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.feedItems, queryKeys.downloads);
  return useMutation({
    mutationFn: async (infoHashes: string[]): Promise<BulkDownloadResult> => {
      const results = await Promise.allSettled(infoHashes.map((h) => client.downloadFeedItem(h)));
      const failed = results.flatMap((r, i) =>
        r.status === "rejected" ? [{ infoHash: infoHashes[i]!, error: r.reason }] : [],
      );
      const started = results.filter((r) => r.status === "fulfilled" && r.value.created).length;
      return { started, already: results.length - started - failed.length, failed };
    },
    onSuccess,
  });
}
