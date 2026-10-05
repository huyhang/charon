import { makeRule } from "@/test/factories";
import { emptySpec, isPreviewable, moveItem, nextPriority, priorityChanges, toSpec } from "./rules";

describe("moveItem", () => {
  it.each([
    [0, 2, ["b", "c", "a"]],
    [2, 0, ["c", "a", "b"]],
    [1, 1, ["a", "b", "c"]],
    [5, 0, ["a", "b", "c"]],
  ])("%i -> %i", (from, to, expected) => {
    expect(moveItem(["a", "b", "c"], from, to)).toEqual(expected);
  });
});

describe("priorityChanges", () => {
  const rule = (id: string, priority: number) => makeRule({ id, priority });

  it.each([
    [[rule("a", 10), rule("b", 20)], []],
    [
      [rule("b", 20), rule("a", 10)],
      [
        ["b", 10],
        ["a", 20],
      ],
    ],
    [
      [rule("a", 5), rule("b", 5), rule("c", 30)],
      [
        ["a", 10],
        ["b", 20],
      ],
    ],
  ])("case %#", (ordered, expected) => {
    expect(priorityChanges(ordered).map((c) => [c.rule.id, c.priority])).toEqual(expected);
  });
});

describe("nextPriority", () => {
  it.each([
    [[], 10],
    [[makeRule({ priority: 30 }), makeRule({ priority: 100 })], 110],
  ])("case %#", (rules, expected) => {
    expect(nextPriority(rules)).toBe(expected);
  });
});

describe("toSpec", () => {
  const step = { op: "replace" as const, find: "a", replace: "b" };
  it.each([
    ["no steps", makeRule(), []],
    ["steps kept", makeRule({ steps: [step] }), [step]],
    // The API may omit `steps`, which defaults to none.
    ["steps omitted", { ...makeRule(), steps: undefined }, []],
  ])("drops identity fields (%s)", (_label, rule, steps) => {
    expect(toSpec(rule)).toEqual({
      name: "TV",
      priority: 10,
      enabled: true,
      match_type: "glob",
      pattern: "*S0?E*",
      steps,
      destination: "/library/tv",
    });
  });
});

describe("isPreviewable", () => {
  const base = { ...emptySpec(10), pattern: "*", destination: "/library" };
  it.each([
    [base, true],
    [{ ...base, pattern: "" }, false],
    [{ ...base, destination: "" }, false],
    [{ ...base, destination: "library" }, false],
    [{ ...base, steps: [{ op: "replace" as const, find: "", replace: "x" }] }, false],
    [{ ...base, steps: [{ op: "replace" as const, find: "a", replace: "" }] }, true],
  ])("case %#", (spec, expected) => {
    expect(isPreviewable(spec)).toBe(expected);
  });
});
