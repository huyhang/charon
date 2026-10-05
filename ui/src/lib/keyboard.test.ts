import { isPaletteShortcut, isTypingTarget } from "./keyboard";

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
