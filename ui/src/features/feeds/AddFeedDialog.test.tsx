import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CharonClient } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { FeedPreview } from "@/api/types";
import { Toaster } from "@/components/ui/sonner";
import { createFakeClient } from "@/test/fakeClient";
import { makeFeed, makeFeedItem } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { findToast } from "@/test/toast";
import { AddFeedDialog } from "./AddFeedDialog";

const URL = "https://tracker.example/rss?passkey=s3cret";
const PREVIEW: FeedPreview = {
  title: "Tracker · TV",
  item_count: 7,
  skipped_count: 1,
  newest_published_at: new Date().toISOString(),
  items: [
    makeFeedItem({ info_hash: "a", name: "Show.S01E01.mkv" }),
    makeFeedItem({ info_hash: "b", name: "Mystery.mkv", match: null }),
  ],
};

async function setup(overrides: Partial<CharonClient> = {}, initialUrl: string | null = null) {
  const onOpenChange = vi.fn();
  const onCreated = vi.fn();
  const client = createFakeClient({ previewFeed: async () => PREVIEW, ...overrides });
  const result = await renderWithApp(
    <>
      <AddFeedDialog
        open
        initialUrl={initialUrl}
        onOpenChange={onOpenChange}
        onCreated={onCreated}
      />
      <Toaster />
    </>,
    { client },
  );
  return { ...result, onOpenChange, onCreated };
}

const address = () => screen.getByRole("textbox", { name: "Address" });

describe("AddFeedDialog", () => {
  it("explains what to do before an address is given", async () => {
    await setup();
    expect(screen.getByText(/Paste the feed's address/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Subscribe" })).toBeDisabled();
  });

  it("previews the feed, checked against the rules, and names it after the feed", async () => {
    const { client } = await setup();
    await userEvent.type(address(), URL);
    expect(await screen.findByText("Tracker · TV")).toBeInTheDocument();
    expect(screen.getByText(/7 items with magnet links/)).toHaveTextContent("1 skipped");
    const items = screen.getByRole("list", { name: "Newest items" });
    expect(within(items).getByText("Show.S01E01.mkv")).toBeInTheDocument();
    expect(within(items).getByText("No rule")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Tracker · TV");
    expect(client.previewFeed).toHaveBeenLastCalledWith(URL);
    expect(screen.queryByText(/Feed addresses start with/)).not.toBeInTheDocument();
  });

  it("keeps a name you typed", async () => {
    await setup();
    await userEvent.type(screen.getByRole("textbox", { name: "Name" }), "Mine");
    await userEvent.type(address(), URL);
    await screen.findByText("Tracker · TV");
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Mine");
  });

  it.each([["not a url"], ["tracker.example/rss?passkey=abc"], ["ftp://tracker.example/rss"]])(
    "says what a feed address looks like, without fetching %s",
    async (text) => {
      const { client } = await setup();
      await userEvent.type(address(), text);
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Feed addresses start with http:// or https://",
      );
      expect(address()).toHaveAttribute("aria-invalid", "true");
      expect(client.previewFeed).not.toHaveBeenCalled();
      expect(screen.getByRole("button", { name: "Subscribe" })).toBeDisabled();
    },
  );

  it("says why a feed can't be read, and still lets you subscribe", async () => {
    await setup(
      {
        previewFeed: async () => {
          throw new ApiError(422, {
            code: "feed_http_error",
            message: "tracker.example answered 403 Forbidden",
            hint: "Check your passkey.",
          });
        },
      },
      URL,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "tracker.example answered 403 ForbiddenCheck your passkey.",
    );
    await userEvent.type(screen.getByRole("textbox", { name: "Name" }), "TV");
    expect(screen.getByRole("button", { name: "Subscribe anyway" })).toBeEnabled();
  });

  it.each<[boolean]>([[false], [true]])("subscribes (auto-download %s)", async (auto) => {
    const feed = makeFeed({ id: "new", name: "Tracker · TV" });
    const { client, onCreated, onOpenChange } = await setup({ createFeed: async () => feed }, URL);
    await screen.findByText("Tracker · TV");
    if (auto)
      await userEvent.click(screen.getByRole("switch", { name: "Download matches automatically" }));
    await userEvent.click(screen.getByRole("button", { name: "Subscribe" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(feed));
    expect(client.createFeed).toHaveBeenCalledWith({
      name: "Tracker · TV",
      url: URL,
      enabled: true,
      refresh_minutes: 15,
      auto_download: auto,
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(await findToast("Subscribed to Tracker · TV")).toHaveTextContent(
      "Its items are in your inbox.",
    );
  });

  it("says when a new feed can't be read yet", async () => {
    const error = {
      code: "feed_unreachable",
      message: "couldn't reach tracker.example",
      hint: null,
    };
    await setup({ createFeed: async () => makeFeed({ name: "TV", last_error: error }) }, URL);
    await screen.findByText("Tracker · TV");
    await userEvent.click(screen.getByRole("button", { name: "Subscribe" }));
    expect(await findToast("Subscribed to TV")).toHaveTextContent("couldn't reach tracker.example");
  });

  it("says when subscribing fails", async () => {
    const { onCreated } = await setup(
      { createFeed: async () => Promise.reject(new Error("Charon is down")) },
      URL,
    );
    await screen.findByText("Tracker · TV");
    await userEvent.click(screen.getByRole("button", { name: "Subscribe" }));
    expect(await findToast("Couldn't subscribe")).toHaveTextContent("Charon is down");
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("closes on cancel", async () => {
    const { onOpenChange } = await setup();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
