import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@/api/errors";
import { ErrorState } from "./ErrorState";

describe("ErrorState", () => {
  it.each<[string, unknown, string]>([
    [
      "an API error",
      new ApiError(502, { code: "backend_error", message: "DS is down" }),
      "DS is down",
    ],
    ["a network error", new TypeError("Failed to fetch"), "Failed to fetch"],
    ["something unknown", "boom", "Something went wrong"],
  ])("explains %s", (_label, error, message) => {
    render(<ErrorState error={error} />);
    expect(screen.getByRole("alert")).toHaveTextContent(message);
  });

  it.each<[string, boolean]>([
    ["offers a retry when it can", true],
    ["offers no retry when it can't", false],
  ])("%s", async (_label, retryable) => {
    const onRetry = vi.fn();
    render(<ErrorState error={new Error("x")} onRetry={retryable ? onRetry : undefined} />);
    const button = screen.queryByRole("button", { name: "Try again" });
    expect(button !== null).toBe(retryable);
    if (button) await userEvent.click(button);
    expect(onRetry).toHaveBeenCalledTimes(retryable ? 1 : 0);
  });
});
