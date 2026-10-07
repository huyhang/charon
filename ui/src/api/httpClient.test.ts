import { createHttpClient } from "./httpClient";
import { ApiError } from "./errors";

interface Call {
  method: string;
  url: string;
  key: string | null;
  body: unknown;
}

function fakeFetch(status = 200, body: unknown = {}) {
  const calls: Call[] = [];
  const fetch = async (request: Request) => {
    const text = await request.text();
    calls.push({
      method: request.method,
      url: request.url.replace("http://charon", ""),
      key: request.headers.get("X-API-Key"),
      body: text ? JSON.parse(text) : undefined,
    });
    return new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  };
  return { calls, fetch: fetch as typeof globalThis.fetch };
}

function client(key: string | null = "secret", status = 200, body: unknown = {}) {
  const fake = fakeFetch(status, body);
  return {
    calls: fake.calls,
    api: createHttpClient({ baseUrl: "http://charon", getKey: () => key, fetch: fake.fetch }),
  };
}

const SPEC = {
  name: "tv",
  description: "",
  priority: 10,
  enabled: true,
  match_type: "glob" as const,
  pattern: "*",
  steps: [],
  destination: "/tv",
};

const FEED = {
  name: "TV",
  url: "https://t.example/rss",
  enabled: true,
  refresh_minutes: 15,
  auto_download: false,
};

describe("createHttpClient requests", () => {
  it.each<[string, (api: ReturnType<typeof client>["api"]) => Promise<unknown>, Omit<Call, "key">]>(
    [
      ["me", (api) => api.me(), { method: "GET", url: "/api/v1/auth/me", body: undefined }],
      ["health", (api) => api.health(), { method: "GET", url: "/api/v1/health", body: undefined }],
      [
        "listDownloads",
        (api) => api.listDownloads({ status: ["queued", "failed"], limit: 20, cursor: "c1" }),
        {
          method: "GET",
          url: "/api/v1/downloads?status=queued&status=failed&limit=20&cursor=c1",
          body: undefined,
        },
      ],
      [
        "listDownloads bare",
        (api) => api.listDownloads({}),
        { method: "GET", url: "/api/v1/downloads", body: undefined },
      ],
      [
        "downloadSummary",
        (api) => api.downloadSummary(),
        { method: "GET", url: "/api/v1/downloads/summary", body: undefined },
      ],
      [
        "submitDownload",
        (api) => api.submitDownload("magnet:?x", "r1"),
        { method: "POST", url: "/api/v1/downloads", body: { magnet: "magnet:?x", rule_id: "r1" } },
      ],
      [
        "getDownload",
        (api) => api.getDownload("j1"),
        { method: "GET", url: "/api/v1/downloads/j1", body: undefined },
      ],
      [
        "cancelDownload",
        (api) => api.cancelDownload("j1"),
        { method: "DELETE", url: "/api/v1/downloads/j1", body: undefined },
      ],
      [
        "retryDownload",
        (api) => api.retryDownload("j1"),
        { method: "POST", url: "/api/v1/downloads/j1/retry", body: undefined },
      ],
      [
        "listRules",
        (api) => api.listRules(),
        { method: "GET", url: "/api/v1/rules", body: undefined },
      ],
      [
        "createRule",
        (api) => api.createRule(SPEC),
        { method: "POST", url: "/api/v1/rules", body: SPEC },
      ],
      [
        "updateRule",
        (api) => api.updateRule("r1", { ...SPEC, version: 3 }),
        { method: "PUT", url: "/api/v1/rules/r1", body: { ...SPEC, version: 3 } },
      ],
      [
        "reorderRules",
        (api) => api.reorderRules(["b", "a"]),
        { method: "POST", url: "/api/v1/rules/reorder", body: { ids: ["b", "a"] } },
      ],
      [
        "listFeeds",
        (api) => api.listFeeds(),
        { method: "GET", url: "/api/v1/feeds", body: undefined },
      ],
      [
        "createFeed",
        (api) => api.createFeed(FEED),
        { method: "POST", url: "/api/v1/feeds", body: FEED },
      ],
      [
        "updateFeed",
        (api) => api.updateFeed("f1", { ...FEED, url: null }),
        { method: "PUT", url: "/api/v1/feeds/f1", body: { ...FEED, url: null } },
      ],
      [
        "deleteFeed",
        (api) => api.deleteFeed("f1"),
        { method: "DELETE", url: "/api/v1/feeds/f1", body: undefined },
      ],
      [
        "refreshFeed",
        (api) => api.refreshFeed("f1"),
        { method: "POST", url: "/api/v1/feeds/f1/refresh", body: undefined },
      ],
      [
        "revealFeedUrl",
        (api) => api.revealFeedUrl("f1"),
        { method: "GET", url: "/api/v1/feeds/f1/url", body: undefined },
      ],
      [
        "previewFeed",
        (api) => api.previewFeed("https://t.example/rss"),
        { method: "POST", url: "/api/v1/feeds/preview", body: { url: "https://t.example/rss" } },
      ],
      [
        "listFeedItems",
        (api) =>
          api.listFeedItems({
            feedId: "f1",
            match: "matched",
            unseen: true,
            q: "show",
            limit: 50,
            cursor: "c",
          }),
        {
          method: "GET",
          url: "/api/v1/feeds/items?feed_id=f1&match=matched&unseen=true&q=show&limit=50&cursor=c",
          body: undefined,
        },
      ],
      [
        "listFeedItems with defaults",
        (api) => api.listFeedItems({ q: "" }),
        { method: "GET", url: "/api/v1/feeds/items", body: undefined },
      ],
      [
        "getFeedItem",
        (api) => api.getFeedItem("abc"),
        { method: "GET", url: "/api/v1/feeds/items/abc", body: undefined },
      ],
      [
        "feedSummary",
        (api) => api.feedSummary(),
        { method: "GET", url: "/api/v1/feeds/summary", body: undefined },
      ],
      [
        "markFeedItemsSeen",
        (api) => api.markFeedItemsSeen(["h1", "h2"]),
        { method: "POST", url: "/api/v1/feeds/items/seen", body: { info_hashes: ["h1", "h2"] } },
      ],
      [
        "markAllFeedItemsSeen in a view",
        (api) =>
          api.markAllFeedItemsSeen({
            upTo: "2026-10-01T12:00:00Z",
            feedId: "f1",
            match: "matched",
            q: "show",
          }),
        {
          method: "POST",
          url: "/api/v1/feeds/items/seen-all",
          body: { up_to: "2026-10-01T12:00:00Z", feed_id: "f1", match: "matched", q: "show" },
        },
      ],
      [
        "markAllFeedItemsSeen everywhere",
        (api) => api.markAllFeedItemsSeen({ upTo: "2026-10-01T12:00:00Z" }),
        {
          method: "POST",
          url: "/api/v1/feeds/items/seen-all",
          body: { up_to: "2026-10-01T12:00:00Z", feed_id: null, match: "all", q: null },
        },
      ],
      [
        "refreshAllFeeds",
        (api) => api.refreshAllFeeds(),
        { method: "POST", url: "/api/v1/feeds/refresh", body: undefined },
      ],
      [
        "downloadFeedItem",
        (api) => api.downloadFeedItem("abc", "r1"),
        { method: "POST", url: "/api/v1/feeds/items/abc/download", body: { rule_id: "r1" } },
      ],
      [
        "downloadFeedItem without a rule",
        (api) => api.downloadFeedItem("abc"),
        { method: "POST", url: "/api/v1/feeds/items/abc/download", body: { rule_id: null } },
      ],
      [
        "previewRule",
        (api) => api.previewRule({ name: "a", rule: SPEC }),
        { method: "POST", url: "/api/v1/rules/preview", body: { name: "a", rule: SPEC } },
      ],
      [
        "listApiKeys",
        (api) => api.listApiKeys(),
        { method: "GET", url: "/api/v1/api-keys", body: undefined },
      ],
      [
        "issueApiKey",
        (api) => api.issueApiKey("phone", "client"),
        { method: "POST", url: "/api/v1/api-keys", body: { name: "phone", role: "client" } },
      ],
      [
        "revokeApiKey",
        (api) => api.revokeApiKey("k1"),
        { method: "DELETE", url: "/api/v1/api-keys/k1", body: undefined },
      ],
      [
        "destinationFolders",
        (api) => api.destinationFolders("/library/tv shows"),
        {
          method: "GET",
          url: "/api/v1/destinations/folders?path=%2Flibrary%2Ftv%20shows",
          body: undefined,
        },
      ],
    ],
  )("%s", async (_, call, expected) => {
    const { api, calls } = client();
    await call(api);
    expect(calls).toEqual([{ ...expected, key: "secret" }]);
  });
});

describe("createHttpClient responses", () => {
  it("unwraps destination roots", async () => {
    const { api } = client("k", 200, { roots: ["/library"] });
    await expect(api.destinationRoots()).resolves.toEqual(["/library"]);
  });

  it.each([
    [202, true],
    [200, false],
  ])("a download answered %i was created: %s", async (status, created) => {
    const job = { id: "j1" };
    const { api } = client("k", status, job);
    await expect(api.submitDownload("magnet:?xt=x")).resolves.toEqual({ job, created });
    await expect(api.downloadFeedItem("abc")).resolves.toEqual({ job, created });
  });

  it.each([
    [
      "revealFeedUrl",
      { url: "https://t.example/rss?passkey=x" },
      "https://t.example/rss?passkey=x",
    ],
    ["markFeedItemsSeen", { marked: 3 }, 3],
    ["markAllFeedItemsSeen", { marked: 4 }, 4],
  ] as const)("unwraps %s", async (method, body, expected) => {
    const { api } = client("k", 200, body);
    const calls = {
      revealFeedUrl: () => api.revealFeedUrl("f1"),
      markFeedItemsSeen: () => api.markFeedItemsSeen(["h1"]),
      markAllFeedItemsSeen: () => api.markAllFeedItemsSeen({ upTo: "t" }),
    };
    await expect(calls[method]()).resolves.toEqual(expected);
  });

  it("marks items seen with keepalive, so the request outlives a closing page", async () => {
    let keepalive: boolean | undefined;
    const fetch = (async (request: Request) => {
      keepalive = request.keepalive;
      return new Response(JSON.stringify({ marked: 1 }), {
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof globalThis.fetch;
    const api = createHttpClient({ baseUrl: "http://charon", getKey: () => "k", fetch });
    await api.markFeedItemsSeen(["h1"]);
    expect(keepalive).toBe(true);
  });

  it("keeps hints and retryability from error bodies", async () => {
    const body = {
      error: { code: "feed_unreachable", message: "m", hint: "Check it", retryable: true },
    };
    const { api } = client("k", 422, body);
    const error = (await api.previewFeed("x").catch((e: unknown) => e)) as ApiError;
    expect([error.hint, error.retryable]).toEqual(["Check it", true]);
  });

  it("resolves deleteRule on 204", async () => {
    const { api } = client("k", 204);
    await expect(api.deleteRule("r1")).resolves.toBeUndefined();
  });

  it("sends no key header when signed out", async () => {
    const { api, calls } = client(null);
    await api.health();
    expect(calls[0]!.key).toBeNull();
  });

  it.each([
    [404, { error: { code: "job_not_found", message: "nope" } }, "job_not_found", "nope"],
    [502, "Bad gateway", "http_error", "502"],
  ])("rejects %i with ApiError", async (status, body, code, message) => {
    const { api } = client("k", status, body);
    const error = await api.cancelDownload("x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(status);
    expect((error as ApiError).code).toBe(code);
    expect((error as ApiError).message).toContain(message);
  });

  it("keeps validation details", async () => {
    const details = [{ loc: ["body", "pattern"], msg: "bad" }];
    const { api } = client("k", 422, { error: { code: "invalid_request", message: "m", details } });
    const error = (await api.createRule(SPEC).catch((e: unknown) => e)) as ApiError;
    expect(error.details).toEqual(details);
  });
});
