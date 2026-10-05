import { diffNames, tokenize } from "./diff";

describe("tokenize", () => {
  it.each([
    ["Show.S01E01.mkv", ["Show", ".", "S01E01", ".", "mkv"]],
    ["a b", ["a", " ", "b"]],
    ["Café-2", ["Café", "-", "2"]],
    ["", []],
  ])("%s", (text, expected) => {
    expect(tokenize(text)).toEqual(expected);
  });
});

describe("diffNames", () => {
  const render = (segments: { text: string; changed: boolean }[]) =>
    segments.map((s) => (s.changed ? `[${s.text}]` : s.text)).join("");

  it.each([
    ["Show.XYZ.mkv", "Show.ABC.mkv", "Show.[XYZ].mkv", "Show.[ABC].mkv"],
    ["Show.1080p.mkv", "Show.mkv", "Show.[1080p.]mkv", "Show.mkv"],
    ["Same.mkv", "Same.mkv", "Same.mkv", "Same.mkv"],
    ["A.XYZ.1080p.mkv", "A.ABC.mkv", "A.[XYZ].[1080p.]mkv", "A.[ABC].mkv"],
    ["", "new", "", "[new]"],
  ])("%s -> %s", (before, after, expectedBefore, expectedAfter) => {
    const diff = diffNames(before, after);
    expect([render(diff.before), render(diff.after)]).toEqual([expectedBefore, expectedAfter]);
  });
});
