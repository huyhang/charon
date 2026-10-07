import { makeFeed, makeFeedItem } from "@/test/factories";
import { FAST_POLL_MS } from "./jobs";
import {
  canDownload,
  dayLabel,
  FEED_POLL_MS,
  feedHealth,
  feedPollInterval,
  formatInterval,
  groupByDay,
  isHttpUrl,
  jobBadge,
  latestFirstSeen,
  newDividerBefore,
  parseMatchFilter,
  suggestRule,
} from "./feeds";

const job = (status: "queued" | "downloading" | "done" | "failed" | "cancelled", percent = 0) => ({
  id: "j",
  status,
  percent,
  error_code: null,
});

describe("parseMatchFilter", () => {
  it.each([
    ["matched", "matched"],
    ["unmatched", "unmatched"],
    ["all", "all"],
    ["bogus", "all"],
    [null, "all"],
  ])("%s -> %s", (value, expected) => {
    expect(parseMatchFilter(value)).toBe(expected);
  });
});

describe("feedPollInterval", () => {
  it.each([
    [[], FEED_POLL_MS],
    [[makeFeedItem({ job: job("done") })], FEED_POLL_MS],
    [[makeFeedItem(), makeFeedItem({ job: job("downloading", 40) })], FAST_POLL_MS],
  ])("case %#", (items, expected) => {
    expect(feedPollInterval(items)).toBe(expected);
  });
});

describe("latestFirstSeen", () => {
  it.each([
    [[], null],
    [
      [
        makeFeedItem({ first_seen_at: "2026-10-04T12:00:00Z" }),
        makeFeedItem({ first_seen_at: "2026-10-04T13:00:00Z" }),
        makeFeedItem({ first_seen_at: "2026-10-04T11:00:00Z" }),
      ],
      "2026-10-04T13:00:00Z",
    ],
  ])("case %#", (items, expected) => {
    expect(latestFirstSeen(items)).toBe(expected);
  });
});

describe("dayLabel", () => {
  const now = new Date(2026, 9, 6, 15, 0);
  it.each([
    [new Date(2026, 9, 6, 1, 0), "Today"],
    [new Date(2026, 9, 5, 23, 0), "Yesterday"],
    [
      new Date(2026, 9, 2, 12, 0),
      new Date(2026, 9, 2).toLocaleDateString(undefined, { weekday: "long" }),
    ],
    [
      new Date(2026, 8, 20, 12, 0),
      new Date(2026, 8, 20).toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
      }),
    ],
    [
      new Date(2025, 11, 31, 12, 0),
      new Date(2025, 11, 31).toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
      }),
    ],
  ])("%s", (date, expected) => {
    expect(dayLabel(date, now)).toBe(expected);
  });
});

describe("groupByDay", () => {
  it("groups consecutive items published on the same local day, keeping their order", () => {
    const now = new Date(2026, 9, 6, 15, 0);
    const at = (day: number, hour: number) => new Date(2026, 9, day, hour).toISOString();
    const items = [
      makeFeedItem({ info_hash: "a", published_at: at(6, 14) }),
      makeFeedItem({ info_hash: "b", published_at: at(6, 9) }),
      makeFeedItem({ info_hash: "c", published_at: at(5, 20) }),
    ];
    const groups = groupByDay(items, now);
    expect(groups.map((g) => [g.label, g.items.map((i) => i.info_hash)])).toEqual([
      ["Today", ["a", "b"]],
      ["Yesterday", ["c"]],
    ]);
  });
});

describe("newDividerBefore", () => {
  const item = (hash: string, seen: boolean) => makeFeedItem({ info_hash: hash, seen });
  it.each([
    [[], null],
    [[item("a", false), item("b", false)], null],
    [[item("a", true), item("b", true)], null],
    [[item("a", false), item("b", true), item("c", true)], "b"],
    [[item("a", true), item("b", false), item("c", true)], "c"],
    // A slow feed's new item dated between seen ones: no line may claim it was seen.
    [[item("a", false), item("b", true), item("c", false)], null],
    [[item("a", false), item("b", true), item("c", false), item("d", true)], "d"],
  ])("case %#", (items, expected) => {
    expect(newDividerBefore(items)).toBe(expected);
  });
});

describe("feedHealth", () => {
  const error = { code: "feed_http_error", message: "403", hint: null };
  it.each([
    [{ enabled: false, last_error: error }, "paused"],
    [{ last_error: error }, "failing"],
    [{ last_checked_at: null }, "pending"],
    [{}, "healthy"],
  ])("%j -> %s", (overrides, expected) => {
    expect(feedHealth(makeFeed(overrides))).toBe(expected);
  });
});

describe("jobBadge and canDownload", () => {
  it.each([
    [job("queued"), "Queued", false],
    [job("downloading", 42.7), "42%", false],
    [job("done"), "Done", false],
    [job("failed"), "Failed", true],
    [job("cancelled"), "Cancelled", true],
  ])("%j", (itemJob, label, downloadable) => {
    expect(jobBadge(itemJob).label).toBe(label);
    expect(canDownload({ job: itemJob })).toBe(downloadable);
  });

  it("allows downloading an item that isn't in Charon", () => {
    expect(canDownload({ job: null })).toBe(true);
  });
});

describe("isHttpUrl", () => {
  it.each([
    ["https://t.example/rss?passkey=x", true],
    ["http://prowlarr:9696/1/api?t=search", true],
    ["see http://t.example/rss for more", false],
    ["ftp://t.example", false],
    ["t.example/rss", false],
    ["magnet:?xt=urn:btih:abc&tr=http://tracker.example:6969/announce", false],
  ])("%s -> %s", (text, expected) => {
    expect(isHttpUrl(text)).toBe(expected);
  });
});

describe("formatInterval", () => {
  it.each([
    [5, "5 min"],
    [60, "1 hour"],
    [180, "3 hours"],
    [1440, "1 day"],
    [2880, "2 days"],
  ])("%i", (minutes, expected) => {
    expect(formatInterval(minutes)).toBe(expected);
  });
});

describe("suggestRule", () => {
  it.each([
    [
      "Some.Documentary.Special.1080p.mkv",
      "Some Documentary Special",
      "Some.Documentary.Special.*",
    ],
    ["The.Expanse.S02E06.1080p.WEB-DL.mkv", "The Expanse", "The.Expanse.*"],
    ["Dune.Part.Two.2024.2160p.mkv", "Dune Part Two", "Dune.Part.Two.*"],
    ["[SubsPlease] Frieren - 13 (1080p).mkv", "Frieren", "*Frieren *"],
    ["[Group] Show [Special] - 01.mkv", "Show [Special]", "*Show [[]Special[]] *"],
    ["What?.Show*.mkv", "What? Show* mkv", "What[?].Show[*].mkv*"],
    ["One.Two.Three.Four.Five.Six", "One Two Three Four", "One.Two.Three.Four.*"],
    // A number that is part of the title isn't taken for an episode.
    ["The.100.S01E01.720p.mkv", "The 100", "The.100.*"],
    ["24.S09E01.1080p.mkv", "24", "24.*"],
    // The separator after the title is the one the name really uses.
    ["Show.Name_S01E01.mkv", "Show Name", "Show.Name_*"],
  ])("%s", (name, expectedName, pattern) => {
    expect(suggestRule(name)).toEqual({ name: expectedName, pattern });
  });
});
