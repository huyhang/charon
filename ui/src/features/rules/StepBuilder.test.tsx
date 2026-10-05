import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import type { RuleSpec } from "@/api/types";
import { emptySpec } from "@/lib/rules";
import { StepBuilder } from "./StepBuilder";

const step = (find: string) => ({ op: "replace" as const, find, replace: "" });
const withSteps = (...finds: string[]): RuleSpec => ({ ...emptySpec(10), steps: finds.map(step) });

function Harness({ initial, errors = {} }: { initial: RuleSpec; errors?: Record<string, string> }) {
  const [spec, setSpec] = useState(initial);
  return <StepBuilder spec={spec} onChange={setSpec} errors={errors} />;
}

const finds = () =>
  screen.queryAllByLabelText(/^Step \d+ find$/).map((input) => (input as HTMLInputElement).value);

describe("StepBuilder", () => {
  it.each<[string, RuleSpec]>([
    ["no steps", withSteps()],
    // The API may omit `steps`; that means none.
    ["steps omitted", { ...emptySpec(10), steps: undefined }],
  ])("says the name is kept with %s", (_label, spec) => {
    render(<Harness initial={spec} />);
    expect(screen.getByText("No rename steps: the name is kept as is.")).toBeInTheDocument();
  });

  it("adds a step and edits it", async () => {
    render(<Harness initial={withSteps()} />);
    await userEvent.click(screen.getByRole("button", { name: /add step/i }));
    await userEvent.type(screen.getByLabelText("Step 1 find"), "XYZ");
    await userEvent.type(screen.getByLabelText("Step 1 replace"), "ABC");
    expect(finds()).toEqual(["XYZ"]);
    expect(screen.getByLabelText("Step 1 replace")).toHaveValue("ABC");
  });

  it.each<[string, string[]]>([
    ["Move step 1 down", ["b", "a", "c"]],
    ["Move step 3 up", ["a", "c", "b"]],
    ["Move step 2 up", ["b", "a", "c"]],
    ["Remove step 2", ["a", "c"]],
  ])("%s", async (button, expected) => {
    render(<Harness initial={withSteps("a", "b", "c")} />);
    await userEvent.click(screen.getByRole("button", { name: button }));
    expect(finds()).toEqual(expected);
  });

  it.each([
    ["Move step 1 up", true],
    ["Move step 3 down", true],
    ["Move step 2 up", false],
    ["Move step 2 down", false],
  ])("%s is disabled: %s", (button, disabled) => {
    render(<Harness initial={withSteps("a", "b", "c")} />);
    expect(screen.getByRole("button", { name: button }).hasAttribute("disabled")).toBe(disabled);
  });

  it.each([
    ["Replace text", "Find, e.g. XYZ", "Replace with (blank removes)"],
    ["Replace regex", "Regex, e.g. \\.1080p", "Replacement, e.g. \\1 (blank removes)"],
  ])("switching to %s explains what to type", async (op, findHint, replaceHint) => {
    const initial: RuleSpec = {
      ...emptySpec(10),
      steps: [{ op: "regex_replace", find: "", replace: "" }],
    };
    render(<Harness initial={initial} />);
    await userEvent.click(screen.getByRole("combobox", { name: "Step 1 type" }));
    await userEvent.click(await screen.findByRole("option", { name: op }));
    expect(screen.getByRole("combobox", { name: "Step 1 type" })).toHaveTextContent(op);
    expect(screen.getByLabelText("Step 1 find")).toHaveAttribute("placeholder", findHint);
    expect(screen.getByLabelText("Step 1 replace")).toHaveAttribute("placeholder", replaceHint);
  });

  it.each<[string, Record<string, string>, string, boolean, boolean]>([
    ["find", { "steps.0.find": "Find can't be empty" }, "Find can't be empty", true, false],
    ["a whole step", { "steps.0": "Invalid regex" }, "Invalid regex", true, false],
    ["replace", { "steps.0.replace": "Invalid group" }, "Invalid group", false, true],
    [
      "find and replace (find first)",
      { "steps.0.find": "Bad find", "steps.0.replace": "Bad replace" },
      "Bad find",
      true,
      true,
    ],
  ])("shows an error on %s", (_label, errors, message, findInvalid, replaceInvalid) => {
    render(<Harness initial={withSteps("a")} errors={errors} />);
    expect(screen.getByRole("alert")).toHaveTextContent(message);
    expect(screen.getByLabelText("Step 1 find")).toHaveAttribute(
      "aria-invalid",
      String(findInvalid),
    );
    expect(screen.getByLabelText("Step 1 replace")).toHaveAttribute(
      "aria-invalid",
      String(replaceInvalid),
    );
  });
});
