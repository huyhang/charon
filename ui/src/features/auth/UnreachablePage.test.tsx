import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UnreachablePage } from "./UnreachablePage";

describe("UnreachablePage", () => {
  afterEach(() => vi.useRealTimers());

  it.each([1, 3])("retries on its own every interval (%i times)", async (ticks) => {
    vi.useFakeTimers();
    const onRetry = vi.fn(async () => {});
    render(<UnreachablePage error="Failed to fetch" onRetry={onRetry} retryMs={1000} />);
    expect(onRetry).not.toHaveBeenCalled();
    await act(async () => vi.advanceTimersByTime(1000 * ticks));
    expect(onRetry).toHaveBeenCalledTimes(ticks);
  });

  it("stops retrying once it goes away", async () => {
    vi.useFakeTimers();
    const onRetry = vi.fn(async () => {});
    const { unmount } = render(<UnreachablePage error="x" onRetry={onRetry} retryMs={1000} />);
    unmount();
    await act(async () => vi.advanceTimersByTime(5000));
    expect(onRetry).not.toHaveBeenCalled();
  });

  it("retries at once on request, showing the reason meanwhile", async () => {
    const onRetry = vi.fn(async () => {});
    render(<UnreachablePage error="502 Bad Gateway" onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("502 Bad Gateway");
    await userEvent.click(screen.getByRole("button", { name: /retry now/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
