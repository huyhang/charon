import { ApiError } from "./errors";
import { createQueryClient, shouldRetry } from "./QueryProvider";

const apiError = (status: number) => new ApiError(status, { code: "x", message: "x" });

describe("shouldRetry", () => {
  it.each<[number, unknown, boolean]>([
    [0, apiError(401), false],
    [0, apiError(404), false],
    [0, apiError(422), false],
    [0, apiError(502), true],
    [2, apiError(502), false],
    [0, new TypeError("network"), true],
    [1, new TypeError("network"), true],
    [2, new TypeError("network"), false],
  ])("attempt %i after %s -> %s", (count, error, expected) => {
    expect(shouldRetry(count, error)).toBe(expected);
  });
});

describe("createQueryClient", () => {
  it.each<[unknown, number]>([
    [apiError(401), 1],
    [apiError(403), 0],
    [new Error("boom"), 0],
  ])("calls onUnauthorized for %s %i time(s)", async (error, calls) => {
    const onUnauthorized = vi.fn();
    const client = createQueryClient(onUnauthorized);
    await client
      .fetchQuery({ queryKey: ["x"], queryFn: () => Promise.reject(error), retry: false })
      .catch(() => {});
    expect(onUnauthorized).toHaveBeenCalledTimes(calls);
  });
});

describe("createQueryClient mutations", () => {
  it.each<[unknown, number]>([
    [apiError(401), 1],
    [apiError(409), 0],
  ])("a failed action with %s signs out %i time(s)", async (error, calls) => {
    const onUnauthorized = vi.fn();
    const client = createQueryClient(onUnauthorized);
    const mutation = client.getMutationCache().build(client, {
      mutationFn: () => Promise.reject(error),
    });
    await mutation.execute(undefined).catch(() => {});
    expect(onUnauthorized).toHaveBeenCalledTimes(calls);
  });
});
