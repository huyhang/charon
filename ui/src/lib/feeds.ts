import type { Feed, FeedItem, ItemJob, MatchFilter } from "@/api/types";
import { FAST_POLL_MS, isInFlight, STATUS_META, type Tone } from "./jobs";

/** Feed items per page; the inbox stops at MAX_FEED_ITEMS, a whole number of pages. */
export const FEED_PAGE_SIZE = 50;
export const MAX_FEED_ITEMS = 200;
export const FEED_POLL_MS = 15000;

export const MATCH_FILTERS: { id: MatchFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "matched", label: "Matches a rule" },
  { id: "unmatched", label: "No rule" },
];

export function parseMatchFilter(value: string | null): MatchFilter {
  return MATCH_FILTERS.some((f) => f.id === value) ? (value as MatchFilter) : "all";
}

/** Poll quickly only while one of the listed items is downloading. */
export function feedPollInterval(items: readonly FeedItem[]): number {
  return items.some((item) => item.job && isInFlight(item.job.status))
    ? FAST_POLL_MS
    : FEED_POLL_MS;
}

/** The newest time Charon first saw any of these items: marking up to it spares later arrivals. */
export function latestFirstSeen(items: readonly FeedItem[]): string | null {
  return items.reduce<string | null>(
    (latest, item) =>
      latest === null || item.first_seen_at > latest ? item.first_seen_at : latest,
    null,
  );
}

export interface DayGroup {
  key: string;
  label: string;
  items: FeedItem[];
}

/** Items grouped by the local day they were published, keeping their order. */
export function groupByDay(items: readonly FeedItem[], now: Date = new Date()): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const item of items) {
    const date = new Date(item.published_at);
    const key = localDayKey(date);
    const last = groups.at(-1);
    if (last?.key === key) last.items.push(item);
    else groups.push({ key, label: dayLabel(date, now), items: [item] });
  }
  return groups;
}

export function dayLabel(date: Date, now: Date = new Date()): string {
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days > 1 && days < 7) return date.toLocaleDateString(undefined, { weekday: "long" });
  const sameYear = date.getFullYear() === now.getFullYear();
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    ...(sameYear ? {} : { year: "numeric" }),
  });
}

const startOfDay = (date: Date) =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();

const localDayKey = (date: Date) => `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;

/**
 * Where the "seen before" divider goes: right after the last new item, so that everything
 * below it really was seen before. Null when no seen item follows the last new one, e.g. when
 * a slow feed's new items are dated between ones already seen.
 */
export function newDividerBefore(items: readonly FeedItem[]): string | null {
  const lastNew = items.findLastIndex((item) => !item.seen);
  if (lastNew === -1) return null;
  return items[lastNew + 1]?.info_hash ?? null;
}

export type FeedHealth = "healthy" | "failing" | "pending" | "paused";

export function feedHealth(
  feed: Pick<Feed, "enabled" | "last_error" | "last_checked_at">,
): FeedHealth {
  if (!feed.enabled) return "paused";
  if (feed.last_error) return "failing";
  return feed.last_checked_at ? "healthy" : "pending";
}

export const HEALTH_META: Record<FeedHealth, { label: string; dot: string }> = {
  healthy: { label: "Healthy", dot: "bg-success" },
  failing: { label: "Can't be read", dot: "bg-destructive" },
  pending: { label: "Not checked yet", dot: "bg-muted-foreground" },
  paused: { label: "Paused", dot: "bg-muted-foreground/50" },
};

/** What the inbox shows for a torrent that's already in Charon. */
export function jobBadge(job: ItemJob): { label: string; tone: Tone } {
  if (job.status === "downloading")
    return { label: `${Math.floor(job.percent)}%`, tone: "progress" };
  return STATUS_META[job.status];
}

// Charon starts these torrents afresh when they are downloaded again.
const RESTARTABLE: readonly ItemJob["status"][] = ["cancelled", "failed"];

/** A download from the inbox makes sense unless the torrent is already on its way or done. */
export function canDownload(item: Pick<FeedItem, "job">): boolean {
  return !item.job || RESTARTABLE.includes(item.job.status);
}

/** Whether the whole text is an http(s) address, e.g. a feed link (a magnet isn't). */
export function isHttpUrl(text: string): boolean {
  return /^https?:\/\/[^\s"'<>]+$/i.test(text);
}

export const REFRESH_CHOICES = [5, 15, 30, 60, 180, 360, 720, 1440];

export function formatInterval(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 1440) {
    const hours = minutes / 60;
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  const days = minutes / 1440;
  return `${days} day${days === 1 ? "" : "s"}`;
}

// Where a release's title ends, strongest first: a season/episode, a year, a resolution, a
// dash or bracketed detail, and only then a lone number, which may be part of the title
// ("The.100", "24").
const TITLE_ENDS = [
  /^(s\d{1,2}(e\d{1,3})?|e\d{1,3})$/i,
  /^(19|20)\d{2}$/,
  /^\d{3,4}p$/i,
  /^(-|\(.*)$/,
  /^\d{1,3}$/,
];
const MAX_TITLE_WORDS = 4;
const GLOB_SPECIAL = /[[\]*?]/g;

/** How many leading words make the title: up to the strongest terminator found after it. */
function titleLength(words: readonly string[]): number {
  for (const end of TITLE_ENDS) {
    const index = words.findIndex((word, i) => i > 0 && end.test(word));
    if (index !== -1) return index;
  }
  return Math.min(words.length, MAX_TITLE_WORDS);
}

interface ReleaseTitle {
  /** Whether the name starts with a [Group] tag. */
  grouped: boolean;
  /** The name after the tag: words at even indexes, the separators between them at odd ones. */
  parts: string[];
  words: string[];
  /** How many leading words make the title. */
  length: number;
}

function releaseTitle(name: string): ReleaseTitle {
  const rest = name.replace(/^\[[^\]]*\]\s*/, "").replace(/^[.\s_]+/, "");
  const parts = rest.split(/([.\s_]+)/);
  const words = parts.filter((part, i) => i % 2 === 0 && part !== "");
  return { grouped: name.startsWith("["), parts, words, length: titleLength(words) };
}

/**
 * A starting point for a rule that files releases like `name`: its title, and a glob that
 * matches other releases of the same title. The glob keeps the separator after the title, so
 * "The.100.*" doesn't also match "The.1000..." or "Theater...".
 */
export function suggestRule(name: string): { name: string; pattern: string } {
  const { grouped, parts, words, length } = releaseTitle(name);
  const prefix = parts.slice(0, 2 * length).join("");
  const glob = prefix.replace(GLOB_SPECIAL, (c) => `[${c}]`);
  return { name: words.slice(0, length).join(" "), pattern: `${grouped ? "*" : ""}${glob}*` };
}

/** The title as the release spells it, separators and all: "Kusuriya.no.Hitorigoto". */
export function titleInName(name: string): string {
  const { parts, length } = releaseTitle(name);
  return parts.slice(0, Math.max(0, 2 * length - 1)).join("");
}
