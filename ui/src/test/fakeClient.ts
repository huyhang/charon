import { vi, type Mock } from "vitest";
import type { CharonClient } from "@/api/client";
import { ADMIN } from "./factories";

export type FakeClient = { [K in keyof CharonClient]: Mock<CharonClient[K]> };

/** A CharonClient whose every method is a spy with a harmless default. */
export function createFakeClient(overrides: Partial<CharonClient> = {}): FakeClient {
  const defaults: CharonClient = {
    me: async () => ADMIN,
    health: async () => ({ status: "ok", downloader: "reachable" }),
    listDownloads: async () => ({ items: [], next_cursor: null }),
    downloadSummary: async () => ({ counts: {}, download_speed_bps: 0 }),
    getDownload: async () => {
      throw new Error("getDownload not stubbed");
    },
    submitDownload: async () => {
      throw new Error("submitDownload not stubbed");
    },
    cancelDownload: async () => {
      throw new Error("cancelDownload not stubbed");
    },
    retryDownload: async () => {
      throw new Error("retryDownload not stubbed");
    },
    listRules: async () => [],
    createRule: async () => {
      throw new Error("createRule not stubbed");
    },
    updateRule: async () => {
      throw new Error("updateRule not stubbed");
    },
    deleteRule: async () => {},
    previewRule: async ({ name }) => ({ rule_id: null, new_name: name, final_path: null }),
    listApiKeys: async () => [],
    issueApiKey: async () => {
      throw new Error("issueApiKey not stubbed");
    },
    revokeApiKey: async () => {
      throw new Error("revokeApiKey not stubbed");
    },
    destinationRoots: async () => ["/library"],
    destinationFolders: async (path) => ({ path, parent: null, folders: [] }),
  };
  const merged = { ...defaults, ...overrides };
  return Object.fromEntries(
    Object.entries(merged).map(([name, impl]) => [name, vi.fn(impl)]),
  ) as unknown as FakeClient;
}
