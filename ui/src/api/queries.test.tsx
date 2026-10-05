import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { createFakeClient, type FakeClient } from "@/test/fakeClient";
import { ADMIN, makeJob, makeRule } from "@/test/factories";
import { ClientProvider } from "./context";
import { ApiError } from "./errors";
import { createQueryClient } from "./QueryProvider";
import {
  findCachedJob,
  queryKeys,
  SESSION_CHECK_MS,
  useDeleteRule,
  useDestinationRoots,
  useFolders,
  useHealth,
  usePreview,
  useRecentJobs,
  useReorderRules,
  useSaveRule,
  useSessionCheck,
} from "./queries";
import type { Principal, Rule, RuleSpec } from "./types";

function wrapperFor(client: FakeClient, onUnauthorized: () => void) {
  const queryClient = createQueryClient(onUnauthorized);
  return ({ children }: { children: ReactNode }) => (
    <ClientProvider client={client}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ClientProvider>
  );
}

const revoked = () => new ApiError(401, { code: "unauthorized", message: "revoked" });

describe("useSessionCheck", () => {
  afterEach(() => vi.useRealTimers());

  it.each<[string, () => Promise<Principal>, number]>([
    ["signs out once the key is revoked", async () => Promise.reject(revoked()), 1],
    ["stays signed in while the key works", async () => ADMIN, 0],
    ["stays signed in through a network blip", async () => Promise.reject(new TypeError("x")), 0],
  ])("%s", async (_label, me, signOuts) => {
    vi.useFakeTimers();
    const client = createFakeClient({ me });
    const onUnauthorized = vi.fn();
    renderHook(() => useSessionCheck(ADMIN), { wrapper: wrapperFor(client, onUnauthorized) });
    // Seeded with the principal from sign-in, so nothing is re-checked at startup.
    expect(client.me).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(SESSION_CHECK_MS));
    expect(client.me).toHaveBeenCalledTimes(1);
    expect(onUnauthorized).toHaveBeenCalledTimes(signOuts);
  });
});

/** A plain query client (no retries) shared by the hook and the test, so the cache is visible. */
function harness(client: FakeClient) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ClientProvider client={client}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ClientProvider>
  );
  return { queryClient, wrapper };
}

const RULES = [
  makeRule({ id: "a", name: "TV", priority: 10 }),
  makeRule({ id: "b", name: "Movies", priority: 20 }),
  makeRule({ id: "c", name: "Anime", priority: 30 }),
];
const [TV, MOVIES, ANIME] = RULES as [Rule, Rule, Rule];
const ids = (rules: Rule[] | undefined) => rules?.map((rule) => rule.id);

describe("useReorderRules", () => {
  it.each<[string, Rule[], [string, number][]]>([
    [
      "swap the first two",
      [MOVIES, TV, ANIME],
      [
        ["b", 10],
        ["a", 20],
      ],
    ],
    [
      "move the last to the top",
      [ANIME, TV, MOVIES],
      [
        ["c", 10],
        ["a", 20],
        ["b", 30],
      ],
    ],
    ["keep the order", RULES, []],
  ])("%s: saves only the priorities that change", async (_label, ordered, saved) => {
    const client = createFakeClient({ updateRule: async (id, spec) => makeRule({ ...spec, id }) });
    const { queryClient, wrapper } = harness(client);
    queryClient.setQueryData(queryKeys.rules, RULES);
    const { result } = renderHook(() => useReorderRules(), { wrapper });
    await act(() => result.current.mutateAsync(ordered));
    expect(client.updateRule.mock.calls.map(([id, spec]) => [id, spec.priority])).toEqual(saved);
    expect(ids(queryClient.getQueryData(queryKeys.rules))).toEqual(ids(ordered));
    expect(queryClient.getQueryState(queryKeys.rules)?.isInvalidated).toBe(true);
  });

  it("shows the new order while saving, and puts the old one back if saving fails", async () => {
    let fail: (error: Error) => void = () => {};
    const client = createFakeClient({
      updateRule: () => new Promise<Rule>((_, reject) => (fail = reject)),
    });
    const { queryClient, wrapper } = harness(client);
    queryClient.setQueryData(queryKeys.rules, RULES);
    const { result } = renderHook(() => useReorderRules(), { wrapper });
    act(() => result.current.mutate([MOVIES, TV, ANIME]));
    await waitFor(() =>
      expect(ids(queryClient.getQueryData(queryKeys.rules))).toEqual(["b", "a", "c"]),
    );
    await act(async () => fail(new ApiError(500, { code: "internal_error", message: "x" })));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(ids(queryClient.getQueryData(queryKeys.rules))).toEqual(["a", "b", "c"]);
  });
});

describe("useSaveRule", () => {
  const spec: RuleSpec = { ...TV, name: "Shows" };
  it.each<[string, string | undefined, "createRule" | "updateRule"]>([
    ["creates a new rule", undefined, "createRule"],
    ["updates an existing rule", "a", "updateRule"],
  ])("%s and refreshes the rule list", async (_label, id, method) => {
    const client = createFakeClient({
      createRule: async (body) => makeRule({ ...body, id: "new" }),
      updateRule: async (ruleId, body) => makeRule({ ...body, id: ruleId }),
    });
    const { queryClient, wrapper } = harness(client);
    queryClient.setQueryData(queryKeys.rules, RULES);
    const { result } = renderHook(() => useSaveRule(), { wrapper });
    const saved = await act(() => result.current.mutateAsync({ id, spec }));
    expect(saved.name).toBe("Shows");
    expect(client[method]).toHaveBeenCalledTimes(1);
    expect(client[method === "createRule" ? "updateRule" : "createRule"]).not.toHaveBeenCalled();
    expect(queryClient.getQueryState(queryKeys.rules)?.isInvalidated).toBe(true);
  });
});

describe("useDeleteRule", () => {
  it("deletes and refreshes the rule list", async () => {
    const client = createFakeClient();
    const { queryClient, wrapper } = harness(client);
    queryClient.setQueryData(queryKeys.rules, RULES);
    const { result } = renderHook(() => useDeleteRule(), { wrapper });
    await act(() => result.current.mutateAsync("b"));
    expect(client.deleteRule).toHaveBeenCalledWith("b");
    expect(queryClient.getQueryState(queryKeys.rules)?.isInvalidated).toBe(true);
  });
});

describe("queries that wait for their input", () => {
  it.each<[string, () => unknown, keyof FakeClient, unknown[]]>([
    [
      "usePreview",
      () => usePreview({ name: "Show.mkv", rule_id: "a" }),
      "previewRule",
      [{ name: "Show.mkv", rule_id: "a" }],
    ],
    ["useFolders", () => useFolders("/library"), "destinationFolders", ["/library"]],
    ["useRecentJobs", () => useRecentJobs(true), "listDownloads", [{ limit: 8 }]],
    ["useRecentJobs with a limit", () => useRecentJobs(true, 3), "listDownloads", [{ limit: 3 }]],
    ["useDestinationRoots", () => useDestinationRoots(), "destinationRoots", []],
    ["useHealth", () => useHealth(), "health", []],
  ])("%s fetches", async (_label, hook, method, args) => {
    const client = createFakeClient();
    const { wrapper } = harness(client);
    renderHook(() => hook(), { wrapper });
    await waitFor(() => expect(client[method]).toHaveBeenCalledWith(...args));
  });

  it.each<[string, () => unknown, keyof FakeClient]>([
    ["usePreview without a request", () => usePreview(null), "previewRule"],
    ["useFolders without a path", () => useFolders(null), "destinationFolders"],
    ["useRecentJobs while closed", () => useRecentJobs(false), "listDownloads"],
  ])("%s fetches nothing", async (_label, hook, method) => {
    const client = createFakeClient();
    const { wrapper } = harness(client);
    const { result } = renderHook(() => hook(), { wrapper });
    await waitFor(() => expect(result.current).toMatchObject({ fetchStatus: "idle" }));
    expect(client[method]).not.toHaveBeenCalled();
  });
});

describe("findCachedJob", () => {
  const page = (...jobIds: string[]) => ({
    pages: [{ items: jobIds.map((id) => makeJob({ id })), next_cursor: null }],
    pageParams: [null],
  });
  it.each<[string, string | undefined]>([
    ["in-all", "in-all"],
    ["in-failed", "in-failed"],
    ["nowhere", undefined],
  ])("finds %s in any cached list", (id, expected) => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(queryKeys.downloadList("all"), page("in-all", "other"));
    queryClient.setQueryData(queryKeys.downloadList("failed"), page("in-failed"));
    expect(findCachedJob(queryClient, id)?.id).toBe(expected);
  });
});
