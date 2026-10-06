import type { JobList, JobStatus } from "@/api/types";
import { makeJob } from "@/test/factories";
import {
  canCancel,
  canRetry,
  FAST_POLL_MS,
  isInFlight,
  isListCapped,
  jobTitle,
  MAX_LISTED,
  nextPageCursor,
  PAGE_SIZE,
  pollInterval,
  SLOW_POLL_MS,
  statusesFor,
  summarize,
  summaryPollInterval,
  timeline,
  type FilterId,
  type Summary,
} from "./jobs";

describe("status predicates", () => {
  it.each<[JobStatus, boolean, boolean, boolean]>([
    ["queued", true, true, false],
    ["downloading", true, true, false],
    ["completed", true, true, false],
    ["processing", true, false, false],
    ["done", false, false, false],
    ["failed", false, false, true],
    ["cancelled", false, false, false],
  ])("%s: inFlight=%s cancel=%s retry=%s", (status, inFlight, cancel, retry) => {
    expect([isInFlight(status), canCancel(status), canRetry(status)]).toEqual([
      inFlight,
      cancel,
      retry,
    ]);
  });
});

describe("statusesFor", () => {
  it.each<[FilterId, JobStatus[] | undefined]>([
    ["all", undefined],
    ["active", ["queued", "downloading", "completed", "processing"]],
    ["done", ["done"]],
    ["failed", ["failed"]],
    ["cancelled", ["cancelled"]],
  ])("%s", (filter, expected) => {
    expect(statusesFor(filter)).toEqual(expected);
  });
});

describe("pollInterval", () => {
  it.each<[JobStatus[], number]>([
    [[], SLOW_POLL_MS],
    [["done", "failed"], SLOW_POLL_MS],
    [["done", "downloading"], FAST_POLL_MS],
    [["processing"], FAST_POLL_MS],
  ])("%j -> %i", (statuses, expected) => {
    expect(pollInterval(statuses.map((status) => makeJob({ status })))).toBe(expected);
  });
});

describe("summarize", () => {
  it.each<[string, Record<string, number>, number, Summary]>([
    ["nothing yet", {}, 0, { active: 0, speedBps: 0, done: 0, failed: 0 }],
    [
      "every in-flight status counts as active",
      { queued: 1, downloading: 2, completed: 3, processing: 4 },
      150,
      { active: 10, speedBps: 150, done: 0, failed: 0 },
    ],
    [
      "totals beyond one page",
      { done: 38, failed: 1, cancelled: 5 },
      0,
      { active: 0, speedBps: 0, done: 38, failed: 1 },
    ],
  ])("%s", (_label, counts, speed, expected) => {
    expect(summarize({ counts, download_speed_bps: speed })).toEqual(expected);
  });
});

describe("summaryPollInterval", () => {
  it.each<[string, Record<string, number> | undefined, number]>([
    ["not loaded", undefined, SLOW_POLL_MS],
    ["idle", { done: 3, failed: 1 }, SLOW_POLL_MS],
    ["something queued", { queued: 1 }, FAST_POLL_MS],
    ["something filing", { processing: 1 }, FAST_POLL_MS],
  ])("%s", (_label, counts, expected) => {
    const summary = counts && { counts, download_speed_bps: 0 };
    expect(summaryPollInterval(summary)).toBe(expected);
  });
});

describe("timeline", () => {
  const states = (status: JobStatus, stage?: "download" | "processing") =>
    timeline({
      status,
      error: stage ? { stage, code: "x", message: "x" } : null,
    }).map((step) => step.state);

  it.each<[JobStatus, "download" | "processing" | undefined, string[]]>([
    ["queued", undefined, ["current", "upcoming", "upcoming", "upcoming", "upcoming"]],
    ["downloading", undefined, ["complete", "current", "upcoming", "upcoming", "upcoming"]],
    ["processing", undefined, ["complete", "complete", "complete", "current", "upcoming"]],
    ["done", undefined, ["complete", "complete", "complete", "complete", "complete"]],
    ["failed", "download", ["complete", "failed", "upcoming", "upcoming", "upcoming"]],
    ["failed", "processing", ["complete", "complete", "complete", "failed", "upcoming"]],
    ["cancelled", undefined, ["skipped", "skipped", "skipped", "skipped", "skipped"]],
  ])("%s (%s)", (status, stage, expected) => {
    expect(states(status, stage)).toEqual(expected);
  });
});

describe("jobTitle", () => {
  it.each([
    ["Real.Name.mkv", "magnet:?xt=urn:btih:a&dn=Dn.Name.mkv", "Real.Name.mkv"],
    [null, "magnet:?xt=urn:btih:a&dn=Dn.Name.mkv", "Dn.Name.mkv"],
    [null, "magnet:?xt=urn:btih:a", null],
  ])("name=%s", (name, magnet, expected) => {
    expect(jobTitle({ name, magnet })).toBe(expected);
  });
});

describe("list cap", () => {
  /** Pages with these many jobs each; the last page reports `more` as its next cursor. */
  const pages = (sizes: number[], more: string | null): JobList[] =>
    sizes.map((size, index) => ({
      items: Array.from({ length: size }, (_, i) => makeJob({ id: `p${index}-${i}` })),
      next_cursor: index === sizes.length - 1 ? more : `c${index + 1}`,
    }));

  it("is a whole number of pages", () => {
    expect(MAX_LISTED % PAGE_SIZE).toBe(0);
  });

  it.each<[string, JobList[], string | null, boolean]>([
    ["nothing loaded yet", [], null, false],
    ["more to load", pages([25], "c1"), "c1", false],
    ["end of the list", pages([25, 10], null), null, false],
    ["three pages, more to load", pages([25, 25, 25], "c3"), "c3", false],
    ["cap reached, more in Charon", pages([25, 25, 25, 25], "c4"), null, true],
    ["cap reached exactly at the end", pages([25, 25, 25, 25], null), null, false],
    ["past the cap (larger pages)", pages([60, 60], "c2"), null, true],
  ])("%s", (_label, loaded, cursor, capped) => {
    expect(nextPageCursor(loaded)).toBe(cursor);
    expect(isListCapped(loaded)).toBe(capped);
  });
});
