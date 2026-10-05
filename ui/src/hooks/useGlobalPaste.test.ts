import { renderHook } from "@testing-library/react";
import { useGlobalMagnetPaste } from "./useGlobalPaste";

const MAGNET = "magnet:?xt=urn:btih:abc&dn=Show.mkv";

/** Dispatches a paste of `text` on `target`, returning whether the page's default was blocked. */
function paste(target: EventTarget, text: string | null): boolean {
  const event = new Event("paste", { bubbles: true, cancelable: true });
  const clipboardData = text === null ? null : { getData: () => text };
  Object.defineProperty(event, "clipboardData", { value: clipboardData });
  target.dispatchEvent(event);
  return event.defaultPrevented;
}

function element(tag: string, attributes: Record<string, string> = {}): HTMLElement {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  document.body.append(node);
  return node;
}

describe("useGlobalMagnetPaste", () => {
  afterEach(() => document.body.replaceChildren());

  it.each<[string, () => EventTarget, string | null, string | null]>([
    ["a magnet pasted on the page", () => document.body, MAGNET, MAGNET],
    ["a magnet inside other text", () => element("div"), `look: ${MAGNET} ok`, MAGNET],
    ["text without a magnet", () => document.body, "just words", null],
    ["a paste with no clipboard data", () => document.body, null, null],
    ["a magnet pasted into a text field", () => element("input"), MAGNET, null],
    ["a magnet pasted into a text area", () => element("textarea"), MAGNET, null],
    [
      "a magnet pasted into editable content",
      () => element("div", { contenteditable: "true" }),
      MAGNET,
      null,
    ],
  ])("%s", (_label, target, text, expected) => {
    const onMagnet = vi.fn();
    renderHook(() => useGlobalMagnetPaste(onMagnet));
    const node = target();
    // jsdom doesn't implement isContentEditable; mirror what browsers report.
    if (node instanceof HTMLElement && node.getAttribute("contenteditable") === "true") {
      Object.defineProperty(node, "isContentEditable", { value: true });
    }
    const blocked = paste(node, text);
    expect(onMagnet.mock.calls).toEqual(expected ? [[expected]] : []);
    // The page's own paste handling is only taken over when a magnet is used.
    expect(blocked).toBe(expected !== null);
  });

  it("stops listening when unmounted", () => {
    const onMagnet = vi.fn();
    const { unmount } = renderHook(() => useGlobalMagnetPaste(onMagnet));
    unmount();
    paste(document.body, MAGNET);
    expect(onMagnet).not.toHaveBeenCalled();
  });
});
