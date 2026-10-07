import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@/api/errors";
import type { Job } from "@/api/types";
import { createFakeClient } from "@/test/fakeClient";
import { makeJob, makeRule } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { JobDrawer } from "./JobDrawer";

const HASH_MAGNET = "magnet:?xt=urn:btih:ABCDEF&dn=Show.mkv";

async function openDrawer(job: Job, rules = [makeRule({ id: "tv", name: "TV" })]) {
  const client = createFakeClient({ getDownload: async () => job, listRules: async () => rules });
  const onClose = vi.fn();
  const result = await renderWithApp(<JobDrawer jobId={job.id} onClose={onClose} />, { client });
  const dialog = await screen.findByRole("dialog");
  return { ...result, dialog, onClose };
}

/** The value next to a label in the drawer's details list. */
function detail(dialog: HTMLElement, label: string): HTMLElement {
  const term = within(dialog).getByText(label, { selector: "dt" });
  return term.nextElementSibling as HTMLElement;
}

describe("JobDrawer", () => {
  it.each<[string, Partial<Job>, string]>([
    ["the rule's name", { status: "done", processing: { rule_id: "tv", final_path: "/x" } }, "TV"],
    [
      "the id of a rule since deleted",
      { status: "done", processing: { rule_id: "gone", final_path: "/x" } },
      "gone",
    ],
    ["that no rule matched", { status: "done" }, "None matched"],
    ["that no rule is chosen yet", { status: "downloading" }, "Not chosen yet"],
  ])("shows %s", async (_label, overrides, expected) => {
    const { dialog } = await openDrawer(makeJob(overrides));
    await waitFor(() => expect(detail(dialog, "Rule")).toHaveTextContent(expected));
  });

  it("links a matched rule to the rules page", async () => {
    const { dialog } = await openDrawer(
      makeJob({ status: "done", processing: { rule_id: "tv", final_path: "/x" } }),
    );
    expect(await within(dialog).findByRole("link", { name: "TV" })).toHaveAttribute(
      "href",
      "/rules",
    );
  });

  it("shows live progress while downloading", async () => {
    const progress = {
      percent: 42.5,
      downloaded_bytes: 4 * 1024 ** 2,
      size_bytes: 10 * 1024 ** 2,
      download_speed_bps: 1024 ** 2,
      eta_seconds: 6,
    };
    const { dialog } = await openDrawer(makeJob({ status: "downloading", progress }));
    expect(within(dialog).getByText("42%")).toBeInTheDocument();
    expect(within(dialog).getByText("1.0 MB/s · 6s left")).toBeInTheDocument();
    expect(detail(dialog, "Size")).toHaveTextContent("10.0 MB");
  });

  it.each<[string, Job["error"], string, string | null]>([
    [
      "a download failure with a fix",
      {
        stage: "download",
        code: "backend_error",
        message: "broken_link",
        hint: "Check the link is still valid, then retry.",
      },
      "Download failed",
      "Check the link is still valid",
    ],
    [
      "a filing failure with a fix",
      {
        stage: "processing",
        code: "destination_exists",
        message: "/tv/x exists",
        hint: "Something is already at the destination.",
      },
      "Filing failed",
      "already at the destination",
    ],
    [
      "a failure with no known fix",
      { stage: "processing", code: "mystery", message: "odd", hint: null },
      "Filing failed",
      null,
    ],
  ])("explains %s", async (_label, error, heading, hint) => {
    const { dialog } = await openDrawer(makeJob({ status: "failed", error }));
    const alert = within(dialog).getByRole("alert");
    expect(alert).toHaveTextContent(heading);
    expect(alert).toHaveTextContent(error!.code);
    expect(alert).toHaveTextContent(error!.message);
    if (hint) expect(alert).toHaveTextContent(hint);
    else expect(alert.querySelectorAll("p")).toHaveLength(2);
  });

  it.each<[string, Partial<Job>, string[], string[]]>([
    [
      "a filed download",
      { magnet: HASH_MAGNET, processing: { rule_id: null, final_path: "/tv/Show.mkv" } },
      ["Copy saved to", "Copy info hash", "Copy magnet"],
      [],
    ],
    [
      "a download that isn't filed, from a magnet without a hash",
      { magnet: "magnet:?dn=Show.mkv" },
      ["Copy magnet"],
      ["Copy saved to", "Copy info hash"],
    ],
  ])("offers copy buttons for %s", async (_label, overrides, present, absent) => {
    const { dialog } = await openDrawer(makeJob(overrides));
    for (const name of present) expect(within(dialog).getByRole("button", { name })).toBeVisible();
    for (const name of absent) {
      expect(within(dialog).queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });

  it.each<[string, Partial<Job>, string, string]>([
    ["the hash", { magnet: HASH_MAGNET }, "Info hash", "abcdef"],
    ["a dash without a hash", { magnet: "magnet:?dn=Show.mkv" }, "Info hash", "—"],
    ["a dash when not filed", {}, "Saved to", "—"],
  ])("shows %s", async (_label, overrides, label, expected) => {
    const { dialog } = await openDrawer(makeJob(overrides));
    expect(detail(dialog, label)).toHaveTextContent(expected);
  });

  it.each<[string, Partial<Job>, string]>([
    ["Download Station's name", { name: "DS.Name.mkv" }, "DS.Name.mkv"],
    ["the magnet's name", { name: null, magnet: "magnet:?xt=urn:btih:a&dn=Dn.mkv" }, "Dn.mkv"],
    ["a placeholder", { name: null, magnet: "magnet:?xt=urn:btih:a" }, "Unnamed download"],
  ])("titles a job with %s", async (_label, overrides, title) => {
    await openDrawer(makeJob(overrides));
    expect(screen.getByRole("dialog", { name: title })).toBeInTheDocument();
  });

  it("offers the job's actions", async () => {
    const { dialog } = await openDrawer(makeJob({ status: "failed" }));
    expect(within(dialog).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("explains a job that can't be loaded", async () => {
    const client = createFakeClient({
      getDownload: async () =>
        Promise.reject(new ApiError(404, { code: "job_not_found", message: "no such job" })),
    });
    await renderWithApp(<JobDrawer jobId="missing" onClose={() => {}} />, { client });
    const dialog = await screen.findByRole("dialog", { name: "Download" });
    expect(await within(dialog).findByText("no such job")).toBeInTheDocument();
  });

  it("shows a placeholder while the job loads", async () => {
    const client = createFakeClient({ getDownload: () => new Promise<Job>(() => {}) });
    await renderWithApp(<JobDrawer jobId="slow" onClose={() => {}} />, { client });
    const dialog = await screen.findByRole("dialog", { name: "Download" });
    expect(within(dialog).queryByText("Details")).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("stays closed without a job", async () => {
    await renderWithApp(<JobDrawer jobId={undefined} onClose={() => {}} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it.each<[string, (user: ReturnType<typeof userEvent.setup>) => Promise<void>]>([
    ["Escape", (user) => user.keyboard("{Escape}")],
    ["the close button", (user) => user.click(screen.getByRole("button", { name: "Close" }))],
  ])("closes with %s", async (_label, close) => {
    const user = userEvent.setup();
    const { onClose } = await openDrawer(makeJob());
    await close(user);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
