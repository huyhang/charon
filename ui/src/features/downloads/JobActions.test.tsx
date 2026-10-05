import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@/api/errors";
import type { CharonClient } from "@/api/client";
import type { Job } from "@/api/types";
import { Toaster } from "@/components/ui/sonner";
import { createFakeClient } from "@/test/fakeClient";
import { makeJob } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { JobActions } from "./JobActions";

const conflict = (message: string) => new ApiError(409, { code: "job_changed", message });

async function renderActions(job: Job, overrides: Partial<CharonClient> = {}) {
  const client = createFakeClient(overrides);
  await renderWithApp(
    <>
      <JobActions job={job} />
      <Toaster />
    </>,
    { client },
  );
  return client;
}

/** The toast with this title. Sonner briefly renders a second copy while it animates in. */
async function findToast(title: string): Promise<HTMLElement> {
  const [toastTitle] = await screen.findAllByText(title);
  return toastTitle!.closest("[data-sonner-toast]") as HTMLElement;
}

async function cancel() {
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  await userEvent.click(await screen.findByRole("button", { name: "Cancel download" }));
}

describe("JobActions", () => {
  it.each<[string, Partial<CharonClient>, string, string]>([
    [
      "confirms a retry",
      { retryDownload: async () => makeJob({ status: "queued" }) },
      "Retrying",
      "Some.Show.S01E01.mkv",
    ],
    [
      "explains a failed retry",
      { retryDownload: async () => Promise.reject(conflict("job is done")) },
      "Couldn't retry",
      "job is done",
    ],
  ])("%s", async (_label, overrides, title, description) => {
    const client = await renderActions(makeJob({ status: "failed" }), overrides);
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await findToast(title)).toHaveTextContent(description);
    expect(client.retryDownload).toHaveBeenCalledWith("job-1");
  });

  it.each<[string, Partial<CharonClient>, string, string]>([
    [
      "confirms a cancellation",
      { cancelDownload: async () => makeJob({ status: "cancelled" }) },
      "Download cancelled",
      "Some.Show.S01E01.mkv",
    ],
    [
      "explains a failed cancellation",
      { cancelDownload: async () => Promise.reject(conflict("job is processing")) },
      "Couldn't cancel",
      "job is processing",
    ],
  ])("%s", async (_label, overrides, title, description) => {
    const client = await renderActions(makeJob({ status: "downloading" }), overrides);
    await cancel();
    expect(await findToast(title)).toHaveTextContent(description);
    expect(client.cancelDownload).toHaveBeenCalledWith("job-1");
  });

  it("keeps the download when the confirmation is dismissed", async () => {
    const client = await renderActions(makeJob({ status: "queued" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(client.cancelDownload).not.toHaveBeenCalled();
  });

  it.each<[string, Partial<Job>, string]>([
    ["its name", {}, "Some.Show.S01E01.mkv will be removed"],
    ["a placeholder", { name: null, magnet: "magnet:?xt=urn:btih:a" }, "this download will be"],
  ])("names the download in the confirmation by %s", async (_label, overrides, text) => {
    await renderActions(makeJob({ status: "downloading", ...overrides }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent(text);
  });

  it("doesn't let a click on an action reach the card behind it", async () => {
    const onCard = vi.fn();
    await renderWithApp(
      <div onClick={onCard}>
        <JobActions job={makeJob({ status: "failed" })} />
      </div>,
      { client: createFakeClient({ retryDownload: async () => makeJob() }) },
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onCard).not.toHaveBeenCalled();
  });
});
