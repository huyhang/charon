import type { RuleSpec } from "@/api/types";
import {
  addStep,
  clearStaleErrors,
  draftProblems,
  fieldForCode,
  moveStep,
  removeStep,
  updateStep,
} from "./ruleDraft";
import { emptySpec } from "./rules";

const step = (find: string) => ({ op: "replace" as const, find, replace: "" });
const withSteps = (...finds: string[]): RuleSpec => ({ ...emptySpec(10), steps: finds.map(step) });
const finds = (spec: RuleSpec) => spec.steps?.map((s) => s.find);

describe("step edits", () => {
  it("adds an empty replace step", () => {
    expect(addStep(withSteps("a")).steps).toEqual([
      step("a"),
      { op: "replace", find: "", replace: "" },
    ]);
  });

  it("updates one step", () => {
    expect(updateStep(withSteps("a", "b"), 1, { op: "regex_replace", replace: "x" }).steps).toEqual(
      [step("a"), { op: "regex_replace", find: "b", replace: "x" }],
    );
  });

  it.each([
    [0, ["b", "c"]],
    [2, ["a", "b"]],
    [9, ["a", "b", "c"]],
  ])("removes step %i", (index, expected) => {
    expect(finds(removeStep(withSteps("a", "b", "c"), index))).toEqual(expected);
  });

  it.each([
    [0, 1, ["b", "a", "c"]],
    [2, 1, ["a", "c", "b"]],
    [0, -1, ["a", "b", "c"]],
    [2, 3, ["a", "b", "c"]],
  ])("moves step %i to %i", (from, to, expected) => {
    expect(finds(moveStep(withSteps("a", "b", "c"), from, to))).toEqual(expected);
  });

  it("does not mutate the original", () => {
    const original = withSteps("a");
    updateStep(original, 0, { find: "z" });
    expect(finds(original)).toEqual(["a"]);
  });

  // The API may omit `steps` (it defaults to none); every edit treats that as an empty list.
  it.each<[string, (spec: RuleSpec) => RuleSpec, string[]]>([
    ["add", addStep, [""]],
    ["update", (spec) => updateStep(spec, 0, { find: "z" }), []],
    ["remove", (spec) => removeStep(spec, 0), []],
    ["move", (spec) => moveStep(spec, 0, 1), []],
  ])("%s works on a draft without steps", (_label, edit, expected) => {
    const draft: RuleSpec = { ...emptySpec(10), steps: undefined };
    expect(finds(edit(draft)) ?? []).toEqual(expected);
  });
});

describe("fieldForCode", () => {
  it.each([
    ["destination_not_allowed", "destination"],
    ["rule_timeout", "pattern"],
    ["rule_not_found", null],
  ])("%s -> %s", (code, expected) => {
    expect(fieldForCode(code)).toBe(expected);
  });
});

describe("draftProblems", () => {
  const valid: RuleSpec = { ...emptySpec(10), name: "TV", pattern: "*", destination: "/tv" };
  it.each<[Partial<RuleSpec>, number]>([
    [{}, 0],
    [{ name: " " }, 1],
    [{ pattern: "" }, 1],
    [{ destination: "tv" }, 1],
    [{ steps: [step("")] }, 1],
    [{ name: "", pattern: "", destination: "" }, 3],
  ])("%j -> %i problems", (patch, count) => {
    expect(draftProblems({ ...valid, ...patch })).toHaveLength(count);
  });
});

describe("clearStaleErrors", () => {
  const errors = {
    _: "whole form",
    name: "name taken",
    pattern: "invalid regex",
    "steps.0.find": "empty",
    "steps.1.replace": "bad template",
    destination: "outside roots",
  };
  it.each<[string[], string[]]>([
    [[], ["name", "pattern", "steps.0.find", "steps.1.replace", "destination"]],
    [["name"], ["pattern", "steps.0.find", "steps.1.replace", "destination"]],
    [["steps"], ["name", "pattern", "destination"]],
    [["match_type"], ["name", "steps.0.find", "steps.1.replace", "destination"]],
    [["enabled"], ["name", "pattern", "steps.0.find", "steps.1.replace", "destination"]],
    [
      ["destination", "pattern"],
      ["name", "steps.0.find", "steps.1.replace"],
    ],
  ])("editing %j keeps %j", (changed, kept) => {
    expect(Object.keys(clearStaleErrors(errors, changed))).toEqual(kept);
  });

  it("doesn't confuse a field with one that shares its prefix", () => {
    expect(clearStaleErrors({ "steps2.x": "e" }, ["steps"])).toEqual({ "steps2.x": "e" });
  });
});
