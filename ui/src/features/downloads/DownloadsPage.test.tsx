import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@/api/errors";
import type { JobStatus } from "@/api/types";
import type { FilterId } from "@/lib/jobs";
import { createFakeClient } from "@/test/fakeClient";
import { makeJob } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { DownloadsPage, parseFilter } from "./DownloadsPage";

const PATH = "/downloads/:jobId?";

describe("parseFilter", () => {
  it.each<[string | null, FilterId]>([
    ["failed", "failed"],
    ["active", "active"],
    ["bogus", "all"],
    [null, "all"],
  ])("%s -> %s", (value, expected) => {
    expect(parseFilter(value)).toBe(expected);
  });
});

describe("DownloadsPage", () => {
  it("lists jobs and summarizes them", async () => {
    const client = createFakeClient({
      listDownloads: async () => ({
        items: [
          makeJob({ id: "a", name: "A.mkv", status: "done" }),
          makeJob({ id: "b", name: "B.mkv", status: "failed" }),
        ],
        next_cursor: null,
      }),
    });
    await renderWithApp(<DownloadsPage />, { client, route: "/downloads", path: PATH });
    expect(await screen.findByRole("button", { name: "A.mkv" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "B.mkv" })).toBeInTheDocument();
  });

  it.each<[string, string]>([
    ["In progress", "2"],
    ["Download speed", "2.0 KB/s"],
    ["Done", "38"],
    ["Failed", "1"],
  ])("shows Charon's total for %s, not one page's", async (label, value) => {
    const client = createFakeClient({
      listDownloads: async () => ({ items: [makeJob({ status: "done" })], next_cursor: "more" }),
      downloadSummary: async () => ({
        counts: { done: 38, failed: 1, downloading: 2 },
        download_speed_bps: 2048,
      }),
    });
    await renderWithApp(<DownloadsPage />, { client, route: "/downloads", path: PATH });
    const stat = await screen.findByRole("group", { name: label });
    await waitFor(() => expect(stat).toHaveTextContent(value));
  });

  it.each<[string, JobStatus[] | undefined]>([
    ["Failed", ["failed"]],
    ["Active", ["queued", "downloading", "completed", "processing"]],
  ])("filters by %s", async (tab, statuses) => {
    const client = createFakeClient();
    await renderWithApp(<DownloadsPage />, { client, route: "/downloads", path: PATH });
    await userEvent.click(await screen.findByRole("tab", { name: tab }));
    await waitFor(() =>
      expect(client.listDownloads).toHaveBeenCalledWith({
        status: statuses,
        limit: 30,
        cursor: null,
      }),
    );
  });

  it("loads more pages", async () => {
    const client = createFakeClient({
      listDownloads: async ({ cursor }) =>
        cursor
          ? { items: [makeJob({ id: "old", name: "Old.mkv" })], next_cursor: null }
          : { items: [makeJob({ id: "new", name: "New.mkv" })], next_cursor: "c1" },
    });
    await renderWithApp(<DownloadsPage />, { client, route: "/downloads", path: PATH });
    await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("button", { name: "Old.mkv" })).toBeInTheDocument();
  });

  it("opens a job's details from the URL", async () => {
    const job = makeJob({
      id: "j1",
      name: "Deep.Link.mkv",
      status: "failed",
      error: { stage: "download", code: "backend_error", message: "broken_link" },
    });
    const client = createFakeClient({ getDownload: async () => job });
    await renderWithApp(<DownloadsPage />, { client, route: "/downloads/j1", path: PATH });
    expect(await screen.findByRole("dialog", { name: "Deep.Link.mkv" })).toBeInTheDocument();
    expect(screen.getByText("Download failed")).toBeInTheDocument();
  });

  it("prefills a magnet passed in ?add", async () => {
    const magnet = "magnet:?xt=urn:btih:a&dn=Pasted.mkv";
    await renderWithApp(<DownloadsPage />, {
      route: `/downloads?add=${encodeURIComponent(magnet)}`,
      path: PATH,
    });
    await waitFor(() => expect(screen.getByLabelText("Magnet link")).toHaveValue(magnet));
  });

  it("drops the filter from the URL when going back to All", async () => {
    const { router } = await renderWithApp(<DownloadsPage />, {
      route: "/downloads?status=failed",
      path: PATH,
    });
    await userEvent.click(await screen.findByRole("tab", { name: "All" }));
    await waitFor(() => expect(router.state.location.search).toBe(""));
  });

  it("is busy while the next page loads", async () => {
    const client = createFakeClient({
      listDownloads: ({ cursor }) =>
        cursor
          ? new Promise(() => {})
          : Promise.resolve({ items: [makeJob({ name: "New.mkv" })], next_cursor: "c1" }),
    });
    await renderWithApp(<DownloadsPage />, { client, route: "/downloads", path: PATH });
    await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Load more" })).toBeDisabled());
  });

  it("opens a job in the drawer and closes it, keeping the filter", async () => {
    const job = makeJob({ id: "a", name: "A.mkv", status: "failed" });
    const client = createFakeClient({
      listDownloads: async () => ({ items: [job], next_cursor: null }),
      getDownload: async () => job,
    });
    const { router } = await renderWithApp(<DownloadsPage />, {
      client,
      route: "/downloads?status=failed",
      path: PATH,
    });
    await userEvent.click(await screen.findByRole("button", { name: "A.mkv" }));
    expect(await screen.findByRole("dialog", { name: "A.mkv" })).toBeInTheDocument();
    expect(router.state.location).toMatchObject({
      pathname: "/downloads/a",
      search: "?status=failed",
    });
    await userEvent.keyboard("{Escape}");
    await waitFor(() =>
      expect(router.state.location).toMatchObject({
        pathname: "/downloads",
        search: "?status=failed",
      }),
    );
  });

  it("explains a list that can't be loaded, and tries again", async () => {
    const listDownloads = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(502, { code: "http_error", message: "502 Bad Gateway" }))
      .mockResolvedValue({ items: [makeJob({ name: "Back.mkv" })], next_cursor: null });
    const client = createFakeClient({ listDownloads });
    await renderWithApp(<DownloadsPage />, { client, route: "/downloads", path: PATH });
    expect(await screen.findByRole("alert")).toHaveTextContent("502 Bad Gateway");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("button", { name: "Back.mkv" })).toBeInTheDocument();
  });

  it("focuses the magnet field for ?add without a magnet, and tidies the URL", async () => {
    const { router } = await renderWithApp(<DownloadsPage />, {
      route: "/downloads?add=1",
      path: PATH,
    });
    const input = screen.getByLabelText("Magnet link");
    await waitFor(() => expect(input).toHaveFocus());
    expect(input).toHaveValue("");
    expect(router.state.location.search).toBe("");
  });

  it.each<[string, string, string]>([
    ["/downloads", "Nothing here yet", "Paste a magnet link above"],
    ["/downloads?status=cancelled", "No downloads match", "Try another filter."],
  ])("explains an empty list at %s", async (route, title, hint) => {
    await renderWithApp(<DownloadsPage />, { route, path: PATH });
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(hint))).toBeInTheDocument();
  });
});
