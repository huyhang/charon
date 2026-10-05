import { errorHint } from "./errorHints";

describe("errorHint", () => {
  it.each([
    ["destination_exists", /already at the destination/],
    ["destination_not_allowed", /outside the folders/],
    ["filesystem_error", /permissions/],
    ["move_failed", /free space/],
    ["rule_timeout", /Simplify/],
    ["unsafe_name", /unsafe/],
    ["rule_not_found", /deleted/],
    ["task_missing", /fresh download/],
    ["backend_error", /Download Station/],
    ["internal_error", /log/],
  ])("%s", (code, expected) => {
    expect(errorHint({ code })).toMatch(expected);
  });

  it.each([[null], [undefined], [{ code: "something_new" }]])("no hint for %j", (error) => {
    expect(errorHint(error)).toBeNull();
  });
});
