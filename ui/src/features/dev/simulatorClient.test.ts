import {
  createHttpSimulator,
  taskPercent,
  type FakeTask,
  type SimulatorClient,
} from "./simulatorClient";

function fakeFetch(status = 200, body: unknown = []) {
  const calls: { url: string; method: string; body?: unknown }[] = [];
  const fn = async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: String(url),
      method: init?.method ?? "GET",
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    return new Response(JSON.stringify(body), { status });
  };
  return { calls, fn: fn as typeof fetch };
}

describe("createHttpSimulator", () => {
  it.each<
    [
      string,
      (s: SimulatorClient) => Promise<unknown>,
      { url: string; method: string; body?: unknown },
    ]
  >([
    ["listTasks", (s) => s.listTasks(), { url: "/_fake/_control/tasks", method: "GET" }],
    [
      "complete",
      (s) => s.complete("dbid_1"),
      { url: "/_fake/_control/tasks/dbid_1/complete", method: "POST" },
    ],
    [
      "fail",
      (s) => s.fail("dbid_1", "broken_link"),
      { url: "/_fake/_control/tasks/dbid_1/fail", method: "POST", body: { detail: "broken_link" } },
    ],
    [
      "expireSessions",
      (s) => s.expireSessions(),
      { url: "/_fake/_control/sessions/expire", method: "POST" },
    ],
    ["reset", (s) => s.reset(), { url: "/_fake/_control/reset", method: "POST" }],
    ["listFeeds", (s) => s.listFeeds(), { url: "/_fake/_control/feeds", method: "GET" }],
    [
      "publish",
      (s) => s.publish("tv"),
      { url: "/_fake/_control/feeds/tv/publish", method: "POST" },
    ],
    [
      "breakFeed",
      (s) => s.breakFeed("tv", "bad_xml"),
      { url: "/_fake/_control/feeds/tv/break", method: "POST", body: { mode: "bad_xml" } },
    ],
    ["healFeed", (s) => s.healFeed("tv"), { url: "/_fake/_control/feeds/tv/heal", method: "POST" }],
    ["tmdbState", (s) => s.tmdbState(), { url: "/_fake/_control/tmdb", method: "GET" }],
    [
      "setTmdbMode throttled",
      (s) => s.setTmdbMode("throttled"),
      { url: "/_fake/_control/tmdb/throttle", method: "POST" },
    ],
    [
      "setTmdbMode down",
      (s) => s.setTmdbMode("down"),
      { url: "/_fake/_control/tmdb/down", method: "POST" },
    ],
    [
      "setTmdbMode ok",
      (s) => s.setTmdbMode("ok"),
      { url: "/_fake/_control/tmdb/heal", method: "POST" },
    ],
  ])("%s", async (_, call, expected) => {
    const fake = fakeFetch();
    await call(createHttpSimulator("/_fake", fake.fn));
    expect(fake.calls).toEqual([expected]);
  });

  it("rejects on an error status", async () => {
    const fake = fakeFetch(404);
    await expect(createHttpSimulator("/_fake", fake.fn).complete("x")).rejects.toThrow("404");
  });
});

describe("taskPercent", () => {
  const task = (size: string, downloaded: string) =>
    ({
      size,
      additional: { transfer: { size_downloaded: downloaded, speed_download: 0 } },
    }) as FakeTask;
  it.each([
    [task("100", "25"), 25],
    [task("100", "100"), 100],
    [task("0", "0"), 0],
    [task("100", "150"), 100],
  ])("case %#", (t, expected) => {
    expect(taskPercent(t)).toBe(expected);
  });
});
