import type { ApiKey, Job, Principal, Rule } from "@/api/types";

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
    priority: 10,
    enabled: true,
    match_type: "glob",
    pattern: "*S0?E*",
    steps: [],
    destination: "/library/tv",
    created_at: T0,
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
