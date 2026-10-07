import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Job } from "@/api/types";
import { createFakeClient } from "@/test/fakeClient";
import { makeJob } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { JobCard } from "./JobCard";

const progress = {
  percent: 42.5,
  downloaded_bytes: 4.25 * 1024 ** 2,
  size_bytes: 10 * 1024 ** 2,
  download_speed_bps: 1024 ** 2,
  eta_seconds: 6,
};

describe("JobCard", () => {
  it.each<[string, Partial<Job>, RegExp[]]>([
    ["queued", { status: "queued" }, [/Waiting for Download Station/]],
    [
      "downloading",
      { status: "downloading", progress },
      [/42%/, /1\.0 MB\/s/, /6s left/, /4\.3 MB of 10\.0 MB/],
    ],
    ["processing", { status: "processing" }, [/Renaming and moving/]],
    [
      "done",
      { status: "done", processing: { rule_id: "r", final_path: "/tv/Show.mkv" } },
      [/\/tv\/Show\.mkv/],
    ],
    ["done, unmatched", { status: "done" }, [/No rule matched/]],
    [
      "failed",
      {
        status: "failed",
        error: {
          stage: "processing",
          code: "destination_exists",
          message: "/tv/x exists",
          hint: "Something is already at the destination.",
        },
      },
      [/\/tv\/x exists/, /already at the destination/],
    ],
    ["cancelled", { status: "cancelled" }, [/Cancelled\./]],
  ])("shows %s", async (_, overrides, texts) => {
    await renderWithApp(<JobCard job={makeJob(overrides)} onOpen={() => {}} />);
    for (const text of texts) expect(screen.getByText(text)).toBeInTheDocument();
  });

  it.each<[Job["status"], string[]]>([
    ["queued", ["Cancel"]],
    ["downloading", ["Cancel"]],
    ["completed", ["Cancel"]],
    ["processing", []],
    ["done", []],
    ["failed", ["Retry"]],
    ["cancelled", []],
  ])("offers the right actions when %s", async (status, actions) => {
    await renderWithApp(<JobCard job={makeJob({ status })} onOpen={() => {}} />);
    const buttons = ["Retry", "Cancel"].filter((name) => screen.queryByRole("button", { name }));
    expect(buttons).toEqual(actions);
  });

  it("falls back to the magnet's name", async () => {
    await renderWithApp(
      <JobCard
        job={makeJob({ name: null, magnet: "magnet:?xt=urn:btih:a&dn=From.Magnet.mkv" })}
        onOpen={() => {}}
      />,
    );
    expect(screen.getByText("From.Magnet.mkv")).toBeInTheDocument();
  });

  it("opens on click", async () => {
    const onOpen = vi.fn();
    const job = makeJob();
    await renderWithApp(<JobCard job={job} onOpen={onOpen} />);
    await userEvent.click(screen.getByRole("button", { name: job.name! }));
    expect(onOpen).toHaveBeenCalledWith(job);
  });

  it.each<[string, number]>([
    ["{Enter}", 1],
    [" ", 1],
    ["a", 0],
    ["{Tab}", 0],
  ])("pressing %j opens it %i time(s)", async (key, times) => {
    const onOpen = vi.fn();
    const job = makeJob();
    await renderWithApp(<JobCard job={job} onOpen={onOpen} />);
    screen.getByRole("button", { name: job.name! }).focus();
    await userEvent.keyboard(key);
    expect(onOpen).toHaveBeenCalledTimes(times);
  });

  it("says the name is on its way when nothing names the download yet", async () => {
    await renderWithApp(
      <JobCard job={makeJob({ name: null, magnet: "magnet:?xt=urn:btih:a" })} onOpen={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "Unnamed download" })).toHaveTextContent(
      "Fetching name…",
    );
  });

  // Every fix hint tells the user what to do before retrying.
  const ANY_HINT = /then retry|Retry to|retrying may help/;

  // `shown` counts the status badge too when the message is just "Failed".
  it.each<[string, Job["error"], string, number, string | null]>([
    ["no details", null, "Failed", 2, null],
    [
      "no known fix",
      { stage: "download", code: "mystery", message: "odd", hint: null },
      "odd",
      1,
      null,
    ],
    [
      "a known fix",
      {
        stage: "download",
        code: "task_missing",
        message: "gone",
        hint: "The task disappeared. Retry to start a fresh download.",
      },
      "gone",
      1,
      "Retry to start a fresh download.",
    ],
  ])("explains a failure with %s", async (_label, error, message, shown, hint) => {
    await renderWithApp(<JobCard job={makeJob({ status: "failed", error })} onOpen={() => {}} />);
    expect(screen.getAllByText(message)).toHaveLength(shown);
    if (hint) expect(screen.getByText(ANY_HINT)).toHaveTextContent(hint);
    else expect(screen.queryByText(ANY_HINT)).not.toBeInTheDocument();
  });

  it("doesn't open when an action is used", async () => {
    const onOpen = vi.fn();
    const client = createFakeClient({ retryDownload: async () => makeJob() });
    await renderWithApp(<JobCard job={makeJob({ status: "failed" })} onOpen={onOpen} />, {
      client,
    });
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(client.retryDownload).toHaveBeenCalled());
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("retries a failed job", async () => {
    const client = createFakeClient({ retryDownload: async () => makeJob({ status: "queued" }) });
    await renderWithApp(<JobCard job={makeJob({ status: "failed" })} onOpen={() => {}} />, {
      client,
    });
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(client.retryDownload).toHaveBeenCalledWith("job-1"));
  });

  it("asks before cancelling", async () => {
    const client = createFakeClient({
      cancelDownload: async () => makeJob({ status: "cancelled" }),
    });
    await renderWithApp(
      <JobCard job={makeJob({ status: "downloading", progress })} onOpen={() => {}} />,
      { client },
    );
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(client.cancelDownload).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByRole("button", { name: "Cancel download" }));
    await waitFor(() => expect(client.cancelDownload).toHaveBeenCalledWith("job-1"));
  });
});
