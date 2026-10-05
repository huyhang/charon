import createClient, { type Middleware } from "openapi-fetch";
import type { CharonClient } from "./client";
import { ApiError } from "./errors";
import type { paths } from "./schema";
import type { ErrorDetail } from "./types";

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

function toDetail(error: unknown, response: Response): ErrorDetail {
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

export function createHttpClient({ baseUrl = "", getKey, fetch }: HttpClientOptions): CharonClient {
  const api = createClient<paths>({ baseUrl, fetch: fetch && ((req) => fetch(req)) });
  api.use(authMiddleware(getKey));
  const byId = (id: string) => ({ params: { path: { job_id: id } } });

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
      unwrap(await api.POST("/api/v1/downloads", { body: { magnet, rule_id: ruleId ?? null } })),
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
    previewRule: async (request) =>
      unwrap(await api.POST("/api/v1/rules/preview", { body: request })),

    listApiKeys: async () => unwrap(await api.GET("/api/v1/api-keys")),
    issueApiKey: async (name, role) =>
      unwrap(await api.POST("/api/v1/api-keys", { body: { name, role } })),
    revokeApiKey: async (id) =>
      unwrap(await api.DELETE("/api/v1/api-keys/{key_id}", { params: { path: { key_id: id } } })),

    destinationRoots: async () => unwrap(await api.GET("/api/v1/destinations/roots")).roots,
    destinationFolders: async (path) =>
      unwrap(await api.GET("/api/v1/destinations/folders", { params: { query: { path } } })),
  };
}
