import { fieldErrors, firstFieldMessage } from "./fieldErrors";

describe("firstFieldMessage", () => {
  it.each([
    [null, null],
    [[], null],
    [[{ msg: 42 }], null],
    [[{ loc: ["body", "pattern"], msg: "Value error, invalid regex '('" }], "Invalid regex '('"],
    [
      [
        { loc: ["body"], msg: 7 },
        { loc: ["body", "name"], msg: "too short" },
      ],
      "Too short",
    ],
  ])("case %#", (details, expected) => {
    expect(firstFieldMessage(details)).toBe(expected);
  });
});

describe("fieldErrors", () => {
  it.each([
    [null, {}],
    [undefined, {}],
    [[], {}],
    [
      [{ loc: ["body", "pattern"], msg: "Value error, invalid regex '('" }],
      { pattern: "Invalid regex '('" },
    ],
    [
      [{ loc: ["body", "steps", 0, "find"], msg: "String should have at least 1 character" }],
      { "steps.0.find": "String should have at least 1 character" },
    ],
    [
      [{ loc: ["body"], msg: "Value error, give rule_id or rule, not both" }],
      { _: "Give rule_id or rule, not both" },
    ],
    [
      [
        { loc: ["body", "name"], msg: "first" },
        { loc: ["body", "name"], msg: "second" },
      ],
      { name: "First" },
    ],
    [[{ loc: ["query", "path"], msg: "missing" }], { "query.path": "Missing" }],
    [[{ msg: 42 }], { _: "Invalid value" }],
  ])("case %#", (details, expected) => {
    expect(fieldErrors(details)).toEqual(expected);
  });
});
