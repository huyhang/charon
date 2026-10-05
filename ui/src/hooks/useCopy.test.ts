import { act, renderHook } from "@testing-library/react";
import { COPY_UNAVAILABLE, useCopy, writeClipboard } from "./useCopy";

describe("writeClipboard", () => {
  it("uses the Clipboard API when the page has it", async () => {
    const writeText = vi.fn(async () => {});
    const doc = { defaultView: { navigator: { clipboard: { writeText } } } };
    await writeClipboard("chk_secret", doc as unknown as Document);
    expect(writeText).toHaveBeenCalledWith("chk_secret");
  });

  describe("without the Clipboard API (plain HTTP)", () => {
    beforeEach(() => {
      Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    });
    afterEach(() => document.body.replaceChildren());

    it.each<[string, boolean, string | null]>([
      ["copies a hidden selection", true, null],
      ["says so when the browser can't copy either", false, COPY_UNAVAILABLE],
    ])("%s", async (_label, copies, error) => {
      let selected = "";
      document.execCommand = vi.fn(() => {
        selected = (document.activeElement as HTMLTextAreaElement | null)?.value ?? "";
        return copies;
      });
      const result = writeClipboard("chk_secret");
      if (error) await expect(result).rejects.toThrow(error);
      else await expect(result).resolves.toBeUndefined();
      expect(document.execCommand).toHaveBeenCalledWith("copy");
      expect(selected).toBe("chk_secret");
      expect(document.querySelector("textarea")).toBeNull();
    });

    it("copies from inside an open dialog and gives focus back", async () => {
      document.body.innerHTML = `<div role="dialog"><button>Copy</button></div>`;
      const button = document.querySelector("button") as HTMLButtonElement;
      button.focus();
      let host: Element | null = null;
      document.execCommand = vi.fn(() => {
        host = document.activeElement?.parentElement ?? null;
        return true;
      });
      await writeClipboard("chk_secret");
      expect(host).toBe(document.querySelector('[role="dialog"]'));
      expect(document.activeElement).toBe(button);
    });
  });
});

describe("useCopy", () => {
  afterEach(() => vi.useRealTimers());

  it("shows copied for a moment", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useCopy(async () => {}, vi.fn(), 1000));
    await act(() => result.current.copy("x"));
    expect(result.current.copied).toBe(true);
    await act(async () => vi.advanceTimersByTime(1000));
    expect(result.current.copied).toBe(false);
  });

  it("reports a failure instead of throwing it", async () => {
    const failure = new Error(COPY_UNAVAILABLE);
    const onError = vi.fn();
    const { result } = renderHook(() => useCopy(async () => Promise.reject(failure), onError));
    await act(() => result.current.copy("x"));
    expect(onError).toHaveBeenCalledWith(failure);
    expect(result.current.copied).toBe(false);
  });
});
