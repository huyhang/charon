import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CharonClient } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { Feed } from "@/api/types";
import { Toaster } from "@/components/ui/sonner";
import { createFakeClient } from "@/test/fakeClient";
import { CLIENT, makeFeed } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { findToast } from "@/test/toast";
import { FeedSettingsSheet } from "./FeedSettingsSheet";

const FEED = makeFeed({ id: "tv", name: "TV", refresh_minutes: 15 });

async function setup(
  overrides: Partial<CharonClient> = {},
  feed: Feed = FEED,
  principal = undefined,
) {
  const onClose = vi.fn();
  const client = createFakeClient({
    updateFeed: async (_id, changes) => ({ ...feed, ...changes, url: feed.url }),
    refreshFeed: async () => feed,
    ...overrides,
  });
  const result = await renderWithApp(
    <>
      <FeedSettingsSheet feed={feed} onClose={onClose} />
      <Toaster />
    </>,
    { client, principal },
  );
  return { ...result, onClose };
}

describe("FeedSettingsSheet", () => {
  it("shows how the feed is doing", async () => {
    await setup();
    const status = screen.getByRole("region", { name: "Status" });
    expect(status).toHaveTextContent("Healthy");
    expect(status).toHaveTextContent("Next check");
  });

  it("explains a failing feed", async () => {
    const error = { code: "feed_http_error", message: "answered 403", hint: "Check your passkey." };
    await setup({}, makeFeed({ last_error: error }));
    expect(screen.getByRole("alert")).toHaveTextContent("answered 403Check your passkey.");
  });

  it("says when a paused feed won't be checked", async () => {
    await setup({}, makeFeed({ enabled: false, next_check_at: null, last_checked_at: null }));
    const status = screen.getByRole("region", { name: "Status" });
    expect(status).toHaveTextContent("Paused");
    expect(status).toHaveTextContent("Never");
  });

  it.each<[string, Feed | Error, string]>([
    ["up to date", FEED, "TV is up to date"],
    [
      "still failing",
      makeFeed({ name: "TV", last_error: { code: "x", message: "answered 503", hint: null } }),
      "TV can't be read",
    ],
    ["unreachable", new Error("Charon is down"), "Couldn't refresh"],
  ])("refreshes now (%s)", async (_label, outcome, title) => {
    await setup({
      refreshFeed: async () => {
        if (outcome instanceof Error) throw outcome;
        return outcome;
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "Refresh now" }));
    expect(await findToast(title)).toBeInTheDocument();
  });

  it("saves new settings", async () => {
    const { client, onClose } = await setup();
    const name = screen.getByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Shows");
    await userEvent.click(screen.getByRole("switch", { name: "Check this feed" }));
    await userEvent.click(screen.getByRole("switch", { name: "Download matches automatically" }));
    await userEvent.click(screen.getByRole("combobox", { name: "Check every" }));
    await userEvent.click(await screen.findByRole("option", { name: "1 hour" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(client.updateFeed).toHaveBeenCalledWith("tv", {
      name: "Shows",
      url: null,
      enabled: false,
      refresh_minutes: 60,
      auto_download: true,
    });
    expect(await findToast("Feed saved")).toHaveTextContent("Shows");
  });

  it("lets an admin reveal and change the address", async () => {
    const { client } = await setup({
      revealFeedUrl: async () => "https://t.example/rss?passkey=s3cret",
    });
    expect(screen.getByText(FEED.url)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reveal" }));
    const url = await screen.findByRole("textbox", { name: "Address" });
    expect(url).toHaveValue("https://t.example/rss?passkey=s3cret");
    // Focus moves to the address, so pasting a new one lands there.
    expect(url).toHaveFocus();
    expect(screen.getByText(/fetched on the feed's next check/)).toBeInTheDocument();
    await userEvent.clear(url);
    await userEvent.type(url, "https://t.example/rss?passkey=new");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(client.updateFeed).toHaveBeenCalledWith(
        "tv",
        expect.objectContaining({ url: "https://t.example/rss?passkey=new" }),
      ),
    );
  });

  it("says when the address can't be revealed", async () => {
    await setup({ revealFeedUrl: async () => Promise.reject(new Error("forbidden")) });
    await userEvent.click(screen.getByRole("button", { name: "Reveal" }));
    expect(await findToast("Couldn't reveal the address")).toHaveTextContent("forbidden");
  });

  it("doesn't offer client keys the address", async () => {
    await setup({}, FEED, CLIENT as never);
    expect(screen.queryByRole("button", { name: "Reveal" })).not.toBeInTheDocument();
    expect(screen.getByText(/Only admins can see or change the address/)).toBeInTheDocument();
  });

  it("offers a feed's own interval even if it isn't a usual choice", async () => {
    await setup({}, makeFeed({ refresh_minutes: 45 }));
    expect(screen.getByRole("combobox", { name: "Check every" })).toHaveTextContent("45 min");
  });

  it("says when saving fails", async () => {
    const { onClose } = await setup({
      updateFeed: async () => {
        throw new ApiError(403, { code: "forbidden", message: "admins only" });
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await findToast("Couldn't save the feed")).toHaveTextContent("admins only");
    expect(onClose).not.toHaveBeenCalled();
  });

  it.each<[string, CharonClient["deleteFeed"], string]>([
    ["unsubscribes after confirming", async () => {}, "Unsubscribed"],
    [
      "says when unsubscribing fails",
      async () => Promise.reject(new Error("nope")),
      "Couldn't remove the feed",
    ],
  ])("%s", async (_label, deleteFeed, title) => {
    const { client } = await setup({ deleteFeed });
    await userEvent.click(screen.getByRole("button", { name: "Unsubscribe" }));
    const confirm = await screen.findByRole("alertdialog");
    await userEvent.click(within(confirm).getByRole("button", { name: "Unsubscribe" }));
    expect(await findToast(title)).toBeInTheDocument();
    expect(client.deleteFeed).toHaveBeenCalledWith("tv");
  });

  it("closes on cancel", async () => {
    const { onClose } = await setup();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalled();
  });
});
