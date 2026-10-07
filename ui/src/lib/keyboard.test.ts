import { feedShortcut, hasOpenOverlay, isPaletteShortcut, isTypingTarget } from "./keyboard";

describe("isTypingTarget", () => {
  const make = (tag: string, editable = false) => {
    const el = document.createElement(tag);
    if (editable) el.contentEditable = "true";
    Object.defineProperty(el, "isContentEditable", { value: editable });
    return el;
  };

  it.each<[string, EventTarget | null, boolean]>([
    ["input", make("input"), true],
    ["textarea", make("textarea"), true],
    ["select", make("select"), true],
    ["contenteditable div", make("div", true), true],
    ["button", make("button"), false],
    ["body", document.body, false],
    ["null", null, false],
  ])("%s -> %s", (_, target, expected) => {
    expect(isTypingTarget(target)).toBe(expected);
  });
});

describe("hasOpenOverlay", () => {
  it.each([
    ["nothing open", "<main><button>x</button></main>", false],
    ["a dialog or sheet", '<div role="dialog"></div>', true],
    ["a confirmation", '<div role="alertdialog"></div>', true],
    ["a menu", '<div role="menu"></div>', true],
    ["a select's listbox, portaled outside any dialog", '<div role="listbox"></div>', true],
  ])("%s -> %s", (_, html, expected) => {
    const root = document.createElement("div");
    root.innerHTML = html;
    expect(hasOpenOverlay(root)).toBe(expected);
  });
});

describe("isPaletteShortcut", () => {
  it.each([
    [{ key: "k", metaKey: true, ctrlKey: false }, true],
    [{ key: "K", metaKey: false, ctrlKey: true }, true],
    [{ key: "k", metaKey: false, ctrlKey: false }, false],
    [{ key: "j", metaKey: true, ctrlKey: false }, false],
  ])("%j -> %s", (event, expected) => {
    expect(isPaletteShortcut(event)).toBe(expected);
  });
});

describe("feedShortcut", () => {
  it.each([
    [{ key: "j" }, "next"],
    [{ key: "k" }, "previous"],
    [{ key: "d" }, "download"],
    [{ key: "x" }, "select"],
    [{ key: "Enter" }, "expand"],
    [{ key: "o" }, "expand"],
    [{ key: "/" }, "search"],
    [{ key: "ArrowDown" }, null],
    [{ key: "q" }, null],
    [{ key: "j", metaKey: true }, null],
    [{ key: "d", ctrlKey: true }, null],
    [{ key: "x", altKey: true }, null],
  ])("%j -> %s", (event, expected) => {
    expect(feedShortcut({ metaKey: false, ctrlKey: false, altKey: false, ...event })).toBe(
      expected,
    );
  });
});
