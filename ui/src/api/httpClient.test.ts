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
  priority: 10,
  enabled: true,
  match_type: "glob" as const,
  pattern: "*",
  steps: [],
  destination: "/tv",
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
        (api) => api.updateRule("r1", SPEC),
        { method: "PUT", url: "/api/v1/rules/r1", body: SPEC },
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
