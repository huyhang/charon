import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import {
  nextPageCursor,
  PAGE_SIZE,
  pollInterval,
  statusesFor,
  summaryPollInterval,
  type FilterId,
} from "@/lib/jobs";
import { priorityChanges } from "@/lib/rules";
import { useClient } from "./context";
import type { Job, JobList, PreviewRequest, Principal, Role, Rule, RuleSpec } from "./types";

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
};

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
  const onSuccess = useInvalidate(queryKeys.rules);
  return useMutation({
    mutationFn: ({ id, spec }: { id?: string; spec: RuleSpec }) =>
      id ? client.updateRule(id, spec) : client.createRule(spec),
    onSuccess,
  });
}

export function useDeleteRule() {
  const client = useClient();
  const onSuccess = useInvalidate(queryKeys.rules);
  return useMutation({ mutationFn: (id: string) => client.deleteRule(id), onSuccess });
}

/** Saves a new rule order by re-spacing priorities, showing the new order immediately. */
export function useReorderRules() {
  const client = useClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (ordered: Rule[]) => {
      const changes = priorityChanges(ordered);
      await Promise.all(
        changes.map(({ rule, priority }) => client.updateRule(rule.id, { ...rule, priority })),
      );
    },
    onMutate: async (ordered) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.rules });
      const previous = queryClient.getQueryData<Rule[]>(queryKeys.rules);
      queryClient.setQueryData(queryKeys.rules, ordered);
      return { previous };
    },
    onError: (_error, _ordered, context) =>
      queryClient.setQueryData(queryKeys.rules, context?.previous),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.rules }),
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
