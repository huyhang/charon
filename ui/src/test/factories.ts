import type {
  ApiKey,
  Feed,
  FeedItem,
  Job,
  MetadataProvider,
  Principal,
  Rule,
  TitleMatch,
} from "@/api/types";

const T0 = "2026-10-04T12:00:00Z";

export function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    status: "queued",
    name: "Some.Show.S01E01.mkv",
    magnet: "magnet:?xt=urn:btih:abc&dn=Some.Show.S01E01.mkv",
    progress: {
      percent: 0,
      downloaded_bytes: 0,
      size_bytes: null,
      download_speed_bps: null,
      eta_seconds: null,
    },
    processing: { rule_id: null, final_path: null },
    error: null,
    info_hash: null,
    created_by: null,
    created_at: T0,
    updated_at: T0,
    completed_at: null,
    ...overrides,
  };
}

export function makeRule(overrides: Partial<Rule> = {}): Rule {
  return {
    id: "rule-1",
    name: "TV",
    description: "",
    priority: 10,
    enabled: true,
    match_type: "glob",
    pattern: "*S0?E*",
    steps: [],
    destination: "/library/tv",
    created_at: T0,
    version: 1,
    created_by: null,
    updated_by: null,
    ...overrides,
  };
}

export function makeKey(overrides: Partial<ApiKey> = {}): ApiKey {
  return {
    id: "key-1",
    name: "phone",
    role: "client",
    prefix: "chk_abcdefgh",
    created_at: T0,
    revoked_at: null,
    ...overrides,
  };
}

export function makeFeed(overrides: Partial<Feed> = {}): Feed {
  return {
    id: "feed-1",
    name: "TV",
    url: "https://tracker.example/rss?passkey=••••",
    enabled: true,
    refresh_minutes: 15,
    auto_download: false,
    title: "Tracker · TV",
    created_at: T0,
    updated_at: T0,
    created_by: null,
    updated_by: null,
    last_checked_at: T0,
    next_check_at: "2026-10-04T12:15:00Z",
    last_error: null,
    ...overrides,
  };
}

export function makeFeedItem(overrides: Partial<FeedItem> = {}): FeedItem {
  return {
    info_hash: "a".repeat(40),
    name: "Some.Show.S01E02.1080p.mkv",
    title: "Some Show S01E02 1080p",
    magnet: `magnet:?xt=urn:btih:${"a".repeat(40)}&dn=Some.Show.S01E02.1080p.mkv`,
    size_bytes: 1_500_000_000,
    published_at: T0,
    published_estimated: false,
    first_seen_at: T0,
    seen: false,
    feeds: [{ id: "feed-1", name: "TV" }],
    match: {
      rule_id: "rule-1",
      rule_name: "TV",
      new_name: "Some.Show.S01E02.mkv",
      final_path: "/library/tv/Some.Show.S01E02.mkv",
    },
    match_error: null,
    job: null,
    auto_downloaded: false,
    auto_error: null,
    ...overrides,
  };
}

export const ADMIN: Principal = {
  name: "bootstrap-admin",
  role: "admin",
  key_id: null,
  auth_enabled: true,
};
export const CLIENT: Principal = {
  name: "phone",
  role: "client",
  key_id: "key-1",
  auth_enabled: true,
};

export const TMDB: MetadataProvider = {
  id: "tmdb",
  name: "TMDB",
  url: "https://www.themoviedb.org",
  notice:
    "This product uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise approved by TMDB.",
  configured: true,
};

/** Signed in with auth off: everyone is an admin, and there are no API keys. */
export const ANONYMOUS_ADMIN: Principal = {
  name: "anonymous",
  role: "admin",
  key_id: null,
  auth_enabled: false,
};

export function makeTitle(overrides: Partial<TitleMatch> = {}): TitleMatch {
  return {
    provider: "tmdb",
    id: "220542",
    kind: "tv",
    title: "The Apothecary Diaries",
    original_title: "薬屋のひとりごと",
    year: 2023,
    overview: "Maomao is sold into service at the imperial palace.",
    url: "https://www.themoviedb.org/tv/220542",
    ...overrides,
  };
}
