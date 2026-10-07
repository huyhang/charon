import { errorHint } from "./errorHints";

describe("errorHint", () => {
  it.each([
    [{ hint: "Move it, then retry." }, "Move it, then retry."],
    [{ hint: null }, null],
    [null, null],
    [undefined, null],
  ])("%j", (error, expected) => {
    expect(errorHint(error)).toBe(expected);
  });
});
