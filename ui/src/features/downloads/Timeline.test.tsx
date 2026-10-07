import { render, screen } from "@testing-library/react";
import type { JobStatus } from "@/api/types";
import { Timeline } from "./Timeline";

const LABELS = ["Queued", "Downloading", "Downloaded", "Filing", "Done"];

function currentStep(): string | null {
  return (
    screen.getAllByRole("listitem").find((item) => item.getAttribute("aria-current") === "step")
      ?.textContent ?? null
  );
}

describe("Timeline", () => {
  it.each<[JobStatus, "download" | "processing" | undefined, string | null]>([
    ["queued", undefined, "Queued"],
    ["downloading", undefined, "Downloading"],
    ["completed", undefined, "Downloaded"],
    ["processing", undefined, "Filing"],
    ["done", undefined, null],
    ["failed", "download", null],
    ["failed", "processing", null],
    ["cancelled", undefined, null],
  ])("%s (%s) marks %s as the current step", (status, stage, expected) => {
    const error = stage ? { stage, code: "x", message: "x", hint: null } : null;
    render(<Timeline job={{ status, error }} />);
    expect(screen.getByRole("list", { name: "Progress" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual(LABELS);
    expect(currentStep()).toBe(expected);
  });
});
