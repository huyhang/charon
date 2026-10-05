import { screen } from "@testing-library/react";
import type { Health } from "@/api/types";
import { createFakeClient } from "@/test/fakeClient";
import { renderWithApp } from "@/test/render";
import { HealthIndicator, healthState } from "./HealthIndicator";

describe("healthState", () => {
  it.each([
    [undefined, false, "checking"],
    [{ downloader: "reachable" as const }, false, "reachable"],
    [{ downloader: "unreachable" as const }, false, "unreachable"],
    [{ downloader: "reachable" as const }, true, "offline"],
  ])("%j error=%s -> %s", (data, isError, expected) => {
    expect(healthState(data, isError)).toBe(expected);
  });
});

const never = () => new Promise<Health>(() => {});

describe("HealthIndicator", () => {
  it.each<[string, () => Promise<Health>, string]>([
    ["still checking", never, "Checking connection…"],
    [
      "Download Station up",
      async () => ({ status: "ok", downloader: "reachable" }),
      "Download Station connected",
    ],
    [
      "Download Station down",
      async () => ({ status: "ok", downloader: "unreachable" }),
      "Download Station unreachable",
    ],
    [
      "Charon down",
      async () => Promise.reject(new TypeError("Failed to fetch")),
      "Charon unreachable",
    ],
  ])("%s", async (_label, health, message) => {
    await renderWithApp(<HealthIndicator />, { client: createFakeClient({ health }) });
    const status = await screen.findByRole("status");
    expect(await screen.findByText(message)).toBeVisible();
    expect(status).toHaveAttribute("title", message);
  });

  it.each<[boolean, boolean]>([
    [false, false],
    [true, true],
  ])("compact=%s keeps the label for screen readers only: %s", async (compact, hidden) => {
    await renderWithApp(<HealthIndicator compact={compact} />);
    const label = await screen.findByText("Download Station connected");
    expect(label.classList.contains("sr-only")).toBe(hidden);
  });
});
