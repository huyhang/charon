/** A task as the fake Download Station reports it (Synology's getinfo shape). */
export interface FakeTask {
  id: string;
  title: string;
  size: string;
  status: string;
  status_extra: { error_detail: string } | null;
  additional: { transfer: { size_downloaded: string; speed_download: number } };
}

/** Steers the fake Download Station through its test-only `/_control` endpoints. */
export interface SimulatorClient {
  listTasks(): Promise<FakeTask[]>;
  complete(id: string): Promise<void>;
  fail(id: string, detail: string): Promise<void>;
  expireSessions(): Promise<void>;
  reset(): Promise<void>;
}

export function createHttpSimulator(
  baseUrl = "/_fake",
  fetchFn: typeof fetch = (...args) => fetch(...args),
): SimulatorClient {
  const call = async (path: string, init?: RequestInit) => {
    const response = await fetchFn(`${baseUrl}/_control${path}`, init);
    if (!response.ok) throw new Error(`Fake Download Station answered ${response.status}`);
    return response;
  };
  const post = (path: string, body?: unknown) =>
    call(path, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    }).then(() => undefined);

  return {
    listTasks: async () => (await call("/tasks")).json(),
    complete: (id) => post(`/tasks/${encodeURIComponent(id)}/complete`),
    fail: (id, detail) => post(`/tasks/${encodeURIComponent(id)}/fail`, { detail }),
    expireSessions: () => post("/sessions/expire"),
    reset: () => post("/reset"),
  };
}

export function taskPercent(task: FakeTask): number {
  const size = Number(task.size);
  return size > 0
    ? Math.min(100, (Number(task.additional.transfer.size_downloaded) / size) * 100)
    : 0;
}
