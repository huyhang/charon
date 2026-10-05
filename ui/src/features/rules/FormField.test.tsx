import { render, screen } from "@testing-library/react";
import { errorProps, FormField } from "./FormField";

describe("errorProps", () => {
  it.each<[string | null | undefined, Record<string, unknown>]>([
    [undefined, { "aria-invalid": false }],
    [null, { "aria-invalid": false }],
    ["", { "aria-invalid": false }],
    ["Too short", { "aria-invalid": true, "aria-describedby": "name-error" }],
  ])("%j", (error, expected) => {
    expect(errorProps("name", error)).toEqual(expected);
  });
});

describe("FormField", () => {
  it.each<[string | undefined, string | undefined, boolean, string]>([
    ["Name taken", "A short label", true, "Name taken"],
    [undefined, "A short label", false, ""],
  ])("error %j links to the input (invalid=%s)", (error, hint, invalid, description) => {
    render(
      <FormField id="name" label="Name" error={error} hint={hint}>
        <input id="name" {...errorProps("name", error)} />
      </FormField>,
    );
    const input = screen.getByLabelText("Name");
    expect(input).toHaveAttribute("aria-invalid", String(invalid));
    expect(input).toHaveAccessibleDescription(description);
    // The hint shows only while there's no error.
    expect(screen.queryByText("A short label") !== null).toBe(!error);
  });
});
