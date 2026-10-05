import { ApiError, errorMessage, isApiError } from "./errors";

const validation = new ApiError(422, {
  code: "invalid_request",
  message: "request validation failed",
  details: [{ loc: ["body", "pattern"], msg: "Value error, invalid regex '(': missing )" }],
});
const conflict = new ApiError(409, { code: "auth_disabled", message: "auth is off" });

describe("errorMessage", () => {
  it.each<[string, unknown, string]>([
    ["validation details win over the generic message", validation, "Invalid regex '(': missing )"],
    ["API error without details", conflict, "auth is off"],
    ["plain error", new TypeError("Failed to fetch"), "Failed to fetch"],
    ["not an error at all", "boom", "Something went wrong"],
  ])("%s", (_label, error, expected) => {
    expect(errorMessage(error)).toBe(expected);
  });
});

describe("isApiError", () => {
  it.each<[unknown, number | undefined, boolean]>([
    [conflict, undefined, true],
    [conflict, 409, true],
    [conflict, 401, false],
    [new Error("x"), undefined, false],
  ])("case %#", (error, status, expected) => {
    expect(isApiError(error, status)).toBe(expected);
  });
});
