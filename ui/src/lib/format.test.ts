import {
  formatBytes,
  formatDateTime,
  formatEta,
  formatPercent,
  formatRelative,
  formatSpeed,
} from "./format";

describe("formatBytes", () => {
  it.each([
    [null, "—"],
    [undefined, "—"],
    [-1, "—"],
    [0, "0 B"],
    [512, "512 B"],
    [1536, "1.5 KB"],
    [10 * 1024 * 1024, "10.0 MB"],
    [150 * 1024 * 1024, "150 MB"],
    [1.5 * 1024 ** 3, "1.5 GB"],
    [3 * 1024 ** 5, "3072 TB"],
  ])("%s -> %s", (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });
});

describe("formatSpeed", () => {
  it.each([
    [null, "—"],
    [0, "—"],
    [2 * 1024 * 1024, "2.0 MB/s"],
  ])("%s -> %s", (bps, expected) => {
    expect(formatSpeed(bps)).toBe(expected);
  });
});

describe("formatEta", () => {
  it.each([
    [null, "—"],
    [-5, "—"],
    [0, "0s"],
    [42, "42s"],
    [185, "3m 05s"],
    [7800, "2h 10m"],
    [90000, "1d 1h"],
  ])("%s -> %s", (seconds, expected) => {
    expect(formatEta(seconds)).toBe(expected);
  });
});

describe("formatPercent", () => {
  it.each([
    [0, "0%"],
    [42.9, "42%"],
    [100, "100%"],
    [130, "100%"],
    [-3, "0%"],
  ])("%s -> %s", (percent, expected) => {
    expect(formatPercent(percent)).toBe(expected);
  });
});

describe("formatRelative", () => {
  const now = new Date("2026-10-04T12:00:00Z");
  it.each([
    ["2026-10-04T11:59:30Z", "just now"],
    ["2026-10-04T11:55:00Z", "5m ago"],
    ["2026-10-04T09:00:00Z", "3h ago"],
    ["2026-10-02T12:00:00Z", "2d ago"],
  ])("%s -> %s", (iso, expected) => {
    expect(formatRelative(iso, now)).toBe(expected);
  });

  it("falls back to a date after a week", () => {
    expect(formatRelative("2026-09-01T12:00:00Z", now)).toMatch(/Sep|9/);
  });
});

describe("formatDateTime", () => {
  it.each([[null], [undefined], [""]])("%s -> dash", (iso) => {
    expect(formatDateTime(iso)).toBe("—");
  });

  it("formats a timestamp", () => {
    expect(formatDateTime("2026-10-04T12:00:00Z")).toMatch(/2026/);
  });
});
