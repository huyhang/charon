import createClient, { type Middleware } from "openapi-fetch";
import type { CharonClient } from "./client";
import { ApiError, type ErrorInit } from "./errors";
import type { paths } from "./schema";
import type { ErrorDetail, Job, Submission } from "./types";

export interface HttpClientOptions {
  baseUrl?: string;
  /** Read on every request, so signing in or out takes effect immediately. */
  getKey: () => string | null;
  fetch?: typeof globalThis.fetch;
}

type Result<T> = { data?: T; error?: unknown; response: Response };

export function unwrap<T>({ data, error, response }: Result<T>): T {
  if (response.ok) return data as T;
  throw new ApiError(response.status, toDetail(error, response));
}

/** Charon answers 202 for a new download and 200 for one it already had. */
export function submission(result: Result<Job>): Submission {
  return { job: unwrap(result), created: result.response.status === 202 };
}

function toDetail(error: unknown, response: Response): ErrorInit {
  const detail = (error as { error?: ErrorDetail } | undefined)?.error;
  if (detail?.code) return detail;
  return { code: "http_error", message: `${response.status} ${response.statusText}`.trim() };
}

export function authMiddleware(getKey: () => string | null): Middleware {
  return {
    onRequest({ request }) {
      const key = getKey();
      if (key) request.headers.set("X-API-Key", key);
      return request;
    },
  };
}

const PROVIDER_KEY = "/api/v1/metadata/providers/{provider_id}/key";

export function createHttpClient({ baseUrl = "", getKey, fetch }: HttpClientOptions): CharonClient {
  const api = createClient<paths>({ baseUrl, fetch: fetch && ((req) => fetch(req)) });
  api.use(authMiddleware(getKey));
  const byId = (id: string) => ({ params: { path: { job_id: id } } });
  const feed = (id: string) => ({ params: { path: { feed_id: id } } });
  const item = (infoHash: string) => ({ params: { path: { info_hash: infoHash } } });

  return {
    me: async () => unwrap(await api.GET("/api/v1/auth/me")),
    health: async () => unwrap(await api.GET("/api/v1/health")),

    listDownloads: async ({ status, limit, cursor }) =>
      unwrap(
        await api.GET("/api/v1/downloads", {
          params: { query: { status, limit, cursor: cursor ?? undefined } },
          querySerializer: { array: { style: "form", explode: true } },
        }),
      ),
    downloadSummary: async () => unwrap(await api.GET("/api/v1/downloads/summary")),
    getDownload: async (id) => unwrap(await api.GET("/api/v1/downloads/{job_id}", byId(id))),
    submitDownload: async (magnet, ruleId) =>
      submission(
        await api.POST("/api/v1/downloads", { body: { magnet, rule_id: ruleId ?? null } }),
      ),
    cancelDownload: async (id) => unwrap(await api.DELETE("/api/v1/downloads/{job_id}", byId(id))),
    retryDownload: async (id) =>
      unwrap(await api.POST("/api/v1/downloads/{job_id}/retry", byId(id))),

    listRules: async () => unwrap(await api.GET("/api/v1/rules")),
    createRule: async (spec) => unwrap(await api.POST("/api/v1/rules", { body: spec })),
    updateRule: async (id, spec) =>
      unwrap(
        await api.PUT("/api/v1/rules/{rule_id}", { params: { path: { rule_id: id } }, body: spec }),
      ),
    deleteRule: async (id) => {
      unwrap(await api.DELETE("/api/v1/rules/{rule_id}", { params: { path: { rule_id: id } } }));
    },
    reorderRules: async (ids) => unwrap(await api.POST("/api/v1/rules/reorder", { body: { ids } })),
    previewRule: async (request) =>
      unwrap(await api.POST("/api/v1/rules/preview", { body: request })),

    listFeeds: async () => unwrap(await api.GET("/api/v1/feeds")),
    createFeed: async (spec) => unwrap(await api.POST("/api/v1/feeds", { body: spec })),
    updateFeed: async (id, changes) =>
      unwrap(await api.PUT("/api/v1/feeds/{feed_id}", { ...feed(id), body: changes })),
    deleteFeed: async (id) => {
      unwrap(await api.DELETE("/api/v1/feeds/{feed_id}", feed(id)));
    },
    refreshFeed: async (id) => unwrap(await api.POST("/api/v1/feeds/{feed_id}/refresh", feed(id))),
    refreshAllFeeds: async () => unwrap(await api.POST("/api/v1/feeds/refresh")),
    revealFeedUrl: async (id) => unwrap(await api.GET("/api/v1/feeds/{feed_id}/url", feed(id))).url,
    previewFeed: async (url) => unwrap(await api.POST("/api/v1/feeds/preview", { body: { url } })),
    listFeedItems: async ({ feedId, match, unseen, q, limit, cursor }) =>
      unwrap(
        await api.GET("/api/v1/feeds/items", {
          params: {
            query: {
              feed_id: feedId ?? undefined,
              match,
              unseen,
              q: q || undefined,
              limit,
              cursor: cursor ?? undefined,
            },
          },
        }),
      ),
    getFeedItem: async (infoHash) =>
      unwrap(await api.GET("/api/v1/feeds/items/{info_hash}", item(infoHash))),
    feedSummary: async () => unwrap(await api.GET("/api/v1/feeds/summary")),
    markFeedItemsSeen: async (infoHashes) =>
      unwrap(
        await api.POST("/api/v1/feeds/items/seen", {
          body: { info_hashes: infoHashes },
          // Often sent as the page closes; keepalive lets the request outlive it.
          keepalive: true,
        }),
      ).marked,
    markAllFeedItemsSeen: async ({ upTo, feedId, match, q }) =>
      unwrap(
        await api.POST("/api/v1/feeds/items/seen-all", {
          body: { up_to: upTo, feed_id: feedId ?? null, match: match ?? "all", q: q || null },
        }),
      ).marked,
    downloadFeedItem: async (infoHash, ruleId) =>
      submission(
        await api.POST("/api/v1/feeds/items/{info_hash}/download", {
          ...item(infoHash),
          body: { rule_id: ruleId ?? null },
        }),
      ),

    listApiKeys: async () => unwrap(await api.GET("/api/v1/api-keys")),
    issueApiKey: async (name, role) =>
      unwrap(await api.POST("/api/v1/api-keys", { body: { name, role } })),
    revokeApiKey: async (id) =>
      unwrap(await api.DELETE("/api/v1/api-keys/{key_id}", { params: { path: { key_id: id } } })),

    destinationRoots: async () => unwrap(await api.GET("/api/v1/destinations/roots")).roots,
    destinationFolders: async (path) =>
      unwrap(await api.GET("/api/v1/destinations/folders", { params: { query: { path } } })),

    metadataProviders: async () => unwrap(await api.GET("/api/v1/metadata/providers")),
    searchTitles: async ({ q, provider, kind, refresh }) =>
      unwrap(
        await api.GET("/api/v1/metadata/search", {
          params: { query: { q, provider, kind, refresh } },
        }),
      ),
    providerKey: async (providerId) =>
      unwrap(await api.GET(PROVIDER_KEY, { params: { path: { provider_id: providerId } } })),
    saveProviderKey: async (providerId, key) =>
      unwrap(
        await api.PUT(PROVIDER_KEY, {
          params: { path: { provider_id: providerId } },
          body: { key },
        }),
      ),
    removeProviderKey: async (providerId) =>
      unwrap(await api.DELETE(PROVIDER_KEY, { params: { path: { provider_id: providerId } } })),
    clearTitleCache: async () => {
      unwrap(await api.DELETE("/api/v1/metadata/cache"));
    },
  };
}
