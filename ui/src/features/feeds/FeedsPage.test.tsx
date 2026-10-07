import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode, useState } from "react";
import type { CharonClient } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { FeedItem, ListFeedItemsQuery, MarkAllSeenQuery, Submission } from "@/api/types";
import { Toaster } from "@/components/ui/sonner";
import { createFakeClient } from "@/test/fakeClient";
import { makeFeed, makeFeedItem, makeJob } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { findToast } from "@/test/toast";
import { FeedsPage } from "./FeedsPage";

const TV = makeFeed({ id: "tv", name: "TV" });
const ANIME = makeFeed({ id: "anime", name: "Anime" });
const NEW_SHOW = makeFeedItem({ info_hash: "h1", name: "New.Show.S01E01.mkv", seen: false });
const OLD_SHOW = makeFeedItem({ info_hash: "h2", name: "Old.Show.S01E01.mkv", seen: true });
const UNMATCHED = makeFeedItem({ info_hash: "h3", name: "Mystery.mkv", seen: true, match: null });

function setup(overrides: Partial<CharonClient> = {}, route = "/feeds") {
  const client = createFakeClient({
    listFeeds: async () => [TV, ANIME],
    feedSummary: async () => ({ unread: 1, feeds: { tv: 1 } }),
    listFeedItems: async () => ({ items: [NEW_SHOW, OLD_SHOW, UNMATCHED], next_cursor: null }),
    ...overrides,
  });
  return renderWithApp(
    <>
      <FeedsPage />
      <Toaster />
    </>,
    { client, route, path: "/feeds" },
  );
}

const row = (name: string) => screen.findByRole("listitem", { name });
const lastQuery = (client: { listFeedItems: { mock: { calls: [ListFeedItemsQuery][] } } }) =>
  client.listFeedItems.mock.calls.at(-1)![0];
const downloadButton = async (name: string) =>
  within(await row(name)).getByRole("button", { name: `Download ${name}` });

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function paste(text: string, target: EventTarget = document.body) {
  const event = new Event("paste", { bubbles: true, cancelable: true }) as ClipboardEvent;
  Object.defineProperty(event, "clipboardData", { value: { getData: () => text } });
  act(() => {
    target.dispatchEvent(event);
  });
}

describe("FeedsPage", () => {
  it("invites you to add a feed when there are none", async () => {
    await setup({ listFeeds: async () => [] });
    expect(await screen.findByText("No feeds yet")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add your first feed" }));
    expect(await screen.findByRole("dialog", { name: "Add a feed" })).toBeInTheDocument();
  });

  it("lists items with their match, new ones above a divider", async () => {
    await setup();
    const fresh = await row(NEW_SHOW.name);
    expect(within(fresh).getByLabelText("New")).toBeInTheDocument();
    expect(fresh).toHaveTextContent("New.Show.S01E01.mkvTV·");
    expect(within(await row(UNMATCHED.name)).getByText("No rule")).toBeInTheDocument();
    const items = screen.getAllByRole("listitem").map((li) => li.getAttribute("aria-label"));
    expect(items).toEqual([NEW_SHOW.name, OLD_SHOW.name, UNMATCHED.name]);
    expect(screen.getByRole("separator", { name: "Seen before" })).toBeInTheDocument();
  });

  it("shows unread counts and filters to one feed", async () => {
    const { client, router } = await setup();
    const sidebar = await screen.findByRole("navigation", { name: "Feeds" });
    expect(within(sidebar).getByRole("button", { name: "All feeds, 1 new" })).toBeInTheDocument();
    expect(within(sidebar).getByRole("button", { name: "Anime, healthy" })).toBeInTheDocument();
    await userEvent.click(within(sidebar).getByRole("button", { name: "TV, healthy, 1 new" }));
    await waitFor(() => expect(lastQuery(client).feedId).toBe("tv"));
    expect(router.state.location.search).toBe("?feed=tv");
  });

  it.each<[string, string]>([
    ["Matches a rule", "matched"],
    ["No rule", "unmatched"],
  ])("filters to %s", async (label, match) => {
    const { client, router } = await setup();
    await row(NEW_SHOW.name);
    await userEvent.click(screen.getByRole("radio", { name: label }));
    await waitFor(() => expect(lastQuery(client).match).toBe(match));
    expect(router.state.location.search).toBe(`?match=${match}`);
    await userEvent.click(screen.getByRole("radio", { name: "All" }));
    await waitFor(() => expect(lastQuery(client).match).toBe("all"));
  });

  it("searches names", async () => {
    const { client } = await setup();
    await row(NEW_SHOW.name);
    await userEvent.type(screen.getByLabelText("Search items"), "show");
    await waitFor(() => expect(lastQuery(client).q).toBe("show"));
  });

  it.each<[string, Parameters<CharonClient["listFeedItems"]>[0]["match"], string | null, string]>([
    ["nothing at all", "all", null, "Nothing here yet"],
    ["nothing for a filter", "matched", "matched", "No items match"],
  ])("says when there is %s", async (_label, _match, param, text) => {
    await setup(
      { listFeedItems: async () => ({ items: [], next_cursor: null }) },
      param ? `/feeds?match=${param}` : "/feeds",
    );
    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it("downloads an item and offers to open it", async () => {
    const { client, router } = await setup({
      downloadFeedItem: async () => ({ job: makeJob({ id: "j9" }), created: true }),
    });
    await userEvent.click(
      within(await row(NEW_SHOW.name)).getByRole("button", { name: `Download ${NEW_SHOW.name}` }),
    );
    const toast = await findToast("Download started");
    expect(client.downloadFeedItem).toHaveBeenCalledWith("h1", null);
    await userEvent.click(within(toast).getByRole("button", { name: "Open" }));
    expect(router.state.location.pathname).toBe("/downloads/j9");
  });

  it.each<[string, CharonClient["downloadFeedItem"], string, string]>([
    [
      "already in Charon",
      async () => ({ job: makeJob(), created: false }),
      "Already in Charon",
      NEW_SHOW.name,
    ],
    [
      "failing",
      async () => {
        throw new ApiError(502, {
          code: "downloader_unreachable",
          message: "NAS offline",
          hint: "Check the NAS.",
        });
      },
      "Couldn't start the download",
      "NAS offline Check the NAS.",
    ],
  ])("says when a download is %s", async (_label, downloadFeedItem, title, description) => {
    await setup({ downloadFeedItem });
    await userEvent.click(
      within(await row(NEW_SHOW.name)).getByRole("button", { name: `Download ${NEW_SHOW.name}` }),
    );
    expect(await findToast(title)).toHaveTextContent(description);
  });

  it("selects items and downloads them together", async () => {
    const { client } = await setup({
      downloadFeedItem: async (hash) => ({ job: makeJob({ id: hash }), created: hash !== "h2" }),
    });
    await userEvent.click(await screen.findByRole("checkbox", { name: `Select ${NEW_SHOW.name}` }));
    await userEvent.click(screen.getByRole("checkbox", { name: `Select ${OLD_SHOW.name}` }));
    const bar = screen.getByRole("toolbar", { name: "Selected items" });
    expect(bar).toHaveTextContent("2 selected");
    await userEvent.click(within(bar).getByRole("button", { name: "Download 2" }));
    expect(await findToast("Started 1 download")).toHaveTextContent("1 already in Charon");
    expect(client.downloadFeedItem.mock.calls.map(([hash]) => hash)).toEqual(["h1", "h2"]);
    await waitFor(() => expect(screen.queryByRole("toolbar")).not.toBeInTheDocument());
  });

  it("says how a bulk download went when some couldn't start", async () => {
    await setup({
      downloadFeedItem: async (hash) => {
        if (hash === "h2") throw new Error("NAS offline");
        return { job: makeJob(), created: true };
      },
    });
    await userEvent.click(await screen.findByRole("checkbox", { name: `Select ${NEW_SHOW.name}` }));
    await userEvent.click(screen.getByRole("checkbox", { name: `Select ${OLD_SHOW.name}` }));
    await userEvent.click(screen.getByRole("button", { name: "Download 2" }));
    expect(await findToast("Started 1 download")).toHaveTextContent(
      "1 couldn't start: NAS offline",
    );
    // The one that failed stays selected, ready to try again.
    await waitFor(() =>
      expect(screen.getByRole("toolbar", { name: "Selected items" })).toHaveTextContent(
        "1 selected",
      ),
    );
    expect(screen.getByRole("checkbox", { name: `Select ${OLD_SHOW.name}` })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: `Select ${NEW_SHOW.name}` })).not.toBeChecked();
  });

  it("says nothing started when every download of a bulk fails, keeping the selection", async () => {
    await setup({
      downloadFeedItem: async () => {
        throw new ApiError(502, { code: "downloader_unreachable", message: "NAS offline" });
      },
    });
    await userEvent.click(await screen.findByRole("checkbox", { name: `Select ${NEW_SHOW.name}` }));
    await userEvent.click(screen.getByRole("checkbox", { name: `Select ${OLD_SHOW.name}` }));
    await userEvent.click(screen.getByRole("button", { name: "Download 2" }));
    expect(await findToast("Couldn't start 2 downloads")).toHaveTextContent("NAS offline");
    expect(screen.queryByText(/Started 0/)).not.toBeInTheDocument();
    expect(screen.getByRole("toolbar", { name: "Selected items" })).toHaveTextContent("2 selected");
  });

  it("selects the feed you just subscribed to", async () => {
    const { router } = await setup({
      previewFeed: async () => ({
        title: "New feed",
        item_count: 0,
        skipped_count: 0,
        newest_published_at: null,
        items: [],
      }),
      createFeed: async () => makeFeed({ id: "new", name: "New feed" }),
    });
    await row(NEW_SHOW.name);
    await userEvent.click(screen.getByRole("button", { name: "Add feed" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Address" }), "https://t.example/rss");
    await screen.findByText("0 items with magnet links");
    await userEvent.click(screen.getByRole("button", { name: "Subscribe" }));
    await waitFor(() => expect(router.state.location.search).toBe("?feed=new"));
  });

  it.each<[string, Partial<CharonClient>, string, string]>([
    [
      "marking seen",
      { markAllFeedItemsSeen: async () => Promise.reject(new Error("down")) },
      "Mark all seen",
      "Couldn't mark items seen",
    ],
    [
      "refreshing",
      { refreshAllFeeds: async () => Promise.reject(new Error("down")) },
      "Refresh",
      "Couldn't refresh",
    ],
  ])("says when %s fails", async (_label, overrides, button, title) => {
    await setup(overrides);
    await row(NEW_SHOW.name);
    await userEvent.click(screen.getByRole("button", { name: new RegExp(button) }));
    expect(await findToast(title)).toHaveTextContent("down");
  });

  it("says when there was nothing new to mark", async () => {
    await setup({ markAllFeedItemsSeen: async () => 0 });
    await row(NEW_SHOW.name);
    await userEvent.click(screen.getByRole("button", { name: /Mark all seen/ }));
    expect(await findToast("Nothing new to mark")).toBeInTheDocument();
  });

  it("selects everything downloadable at once, and clears", async () => {
    const done = makeFeedItem({
      info_hash: "h4",
      name: "Done.mkv",
      job: { id: "j", status: "done", percent: 100, error_code: null },
    });
    await setup({
      listFeedItems: async () => ({ items: [NEW_SHOW, done], next_cursor: null }),
    });
    await row(NEW_SHOW.name);
    await userEvent.click(screen.getByRole("checkbox", { name: /Select everything/ }));
    expect(screen.getByRole("toolbar")).toHaveTextContent("1 selected");
    await userEvent.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  });

  it("expands an item to show what will happen to it", async () => {
    await setup();
    await userEvent.click(await row(UNMATCHED.name));
    expect(await row(UNMATCHED.name)).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Create rule from this" })).toHaveAttribute(
      "href",
      `/rules?new=1&sample=${encodeURIComponent(UNMATCHED.name)}`,
    );
  });

  it.each<[string, string, Partial<MarkAllSeenQuery>]>([
    ["/feeds", "everything", { feedId: null, match: "all" }],
    ["/feeds?feed=tv&match=matched", "only that view", { feedId: "tv", match: "matched" }],
  ])("marks everything seen from %s, meaning %s", async (route, _meaning, view) => {
    const { client } = await setup({ markAllFeedItemsSeen: async () => 1 }, route);
    await row(NEW_SHOW.name);
    await userEvent.click(screen.getByRole("button", { name: /Mark all seen/ }));
    expect(await findToast("Marked 1 as seen")).toBeInTheDocument();
    expect(client.markAllFeedItemsSeen).toHaveBeenCalledWith({
      upTo: NEW_SHOW.first_seen_at,
      q: "",
      ...view,
    });
  });

  it.each<[string, string, "refreshAllFeeds" | "refreshFeed"]>([
    ["/feeds", "Feeds are up to date", "refreshAllFeeds"],
    ["/feeds?feed=tv", "TV is up to date", "refreshFeed"],
  ])("refreshes from %s", async (route, title, method) => {
    const { client } = await setup(
      {
        refreshFeed: async (id) => makeFeed({ id, name: "TV" }),
        refreshAllFeeds: async () => [TV, ANIME],
      },
      route,
    );
    await row(NEW_SHOW.name);
    await userEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    expect(await findToast(title)).toBeInTheDocument();
    expect(client[method]).toHaveBeenCalledTimes(1);
  });

  it.each<[string, string]>([
    ["/feeds", "1 feed can't be read"],
    ["/feeds?feed=tv", "TV can't be read"],
  ])("says which feeds can't be read after refreshing from %s", async (route, title) => {
    const error = { code: "feed_http_error", message: "403", hint: null };
    const broken = makeFeed({ id: "tv", name: "TV", last_error: error });
    await setup(
      { refreshFeed: async () => broken, refreshAllFeeds: async () => [broken, ANIME] },
      route,
    );
    await row(NEW_SHOW.name);
    await userEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    expect(await findToast(title)).toBeInTheDocument();
  });

  it("explains a feed that can't be read, with a way to fix it", async () => {
    const broken = makeFeed({
      id: "tv",
      name: "TV",
      last_error: {
        code: "feed_http_error",
        message: "tracker answered 403",
        hint: "Check your passkey.",
      },
    });
    await setup({ listFeeds: async () => [broken, ANIME] });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("TV can't be read: tracker answered 403");
    expect(alert).toHaveTextContent("Check your passkey.");
    await userEvent.click(within(alert).getByRole("button", { name: "Fix" }));
    expect(await screen.findByRole("dialog", { name: "TV" })).toBeInTheDocument();
  });

  it("opens a feed's settings from the sidebar", async () => {
    await setup();
    await userEvent.click(await screen.findByRole("button", { name: "Settings for Anime" }));
    expect(await screen.findByRole("dialog", { name: "Anime" })).toBeInTheDocument();
  });

  it.each<[string, string]>([
    ["/feeds?add=1", ""],
    [`/feeds?add=${encodeURIComponent("https://t.example/rss")}`, "https://t.example/rss"],
  ])("opens Add a feed from %s", async (route, url) => {
    const { router } = await setup({}, route);
    const dialog = await screen.findByRole("dialog", { name: "Add a feed" });
    expect(within(dialog).getByRole("textbox", { name: "Address" })).toHaveValue(url);
    expect(router.state.location.search).toBe("");
  });

  it("opens Add a feed with an address pasted anywhere on the page", async () => {
    await setup();
    await row(NEW_SHOW.name);
    paste("  https://t.example/rss?passkey=x\n");
    const dialog = await screen.findByRole("dialog", { name: "Add a feed" });
    expect(within(dialog).getByRole("textbox", { name: "Address" })).toHaveValue(
      "https://t.example/rss?passkey=x",
    );
  });

  it("moves, selects, expands and downloads with the keyboard", async () => {
    const { client } = await setup({
      downloadFeedItem: async () => ({ job: makeJob(), created: true }),
    });
    await row(NEW_SHOW.name);
    fireEvent.keyDown(document.body, { key: "j" });
    expect(await row(NEW_SHOW.name)).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: "j" });
    expect(await row(OLD_SHOW.name)).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: "k" });
    expect(await row(NEW_SHOW.name)).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: "x" });
    expect(screen.getByRole("checkbox", { name: `Select ${NEW_SHOW.name}` })).toBeChecked();
    fireEvent.keyDown(document.activeElement!, { key: "Enter" });
    expect(await row(NEW_SHOW.name)).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(document.activeElement!, { key: "d" });
    await waitFor(() => expect(client.downloadFeedItem).toHaveBeenCalledWith("h1", undefined));
    fireEvent.keyDown(document.activeElement!, { key: "/" });
    expect(screen.getByLabelText("Search items")).toHaveFocus();
  });

  it("leaves keys alone while typing in the search box", async () => {
    await setup();
    await row(NEW_SHOW.name);
    await userEvent.type(screen.getByLabelText("Search items"), "jx");
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  });

  it("marks the new items it showed as seen when you leave", async () => {
    const { client, unmount } = await setup({}, "/feeds?feed=tv");
    await row(NEW_SHOW.name);
    unmount();
    await waitFor(() => expect(client.markFeedItemsSeen).toHaveBeenCalledWith(["h1"]));
  });

  it("marks only the view you leave when you switch feeds", async () => {
    const animeItem = makeFeedItem({ info_hash: "h9", name: "Anime.01.mkv", seen: false });
    const { client } = await setup({
      listFeedItems: async ({ feedId }) => ({
        items: feedId === "anime" ? [animeItem] : [NEW_SHOW, OLD_SHOW],
        next_cursor: null,
      }),
    });
    await row(NEW_SHOW.name);
    await userEvent.click(screen.getByRole("button", { name: /^Anime/ }));
    await row(animeItem.name);
    await waitFor(() => expect(client.markFeedItemsSeen).toHaveBeenCalledWith(["h1"]));
    expect(client.markFeedItemsSeen).toHaveBeenCalledTimes(1);
  });

  it.each<[string, () => void]>([
    [
      "the tab is hidden",
      () => {
        vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
        document.dispatchEvent(new Event("visibilitychange"));
      },
    ],
    ["the page closes", () => window.dispatchEvent(new Event("pagehide"))],
  ])("marks what it showed as seen when %s", async (_label, leave) => {
    const { client } = await setup();
    await row(NEW_SHOW.name);
    act(leave);
    await waitFor(() => expect(client.markFeedItemsSeen).toHaveBeenCalledWith(["h1"]));
  });

  it("says when what it showed couldn't be marked seen", async () => {
    await setup({ markFeedItemsSeen: async () => Promise.reject(new Error("down")) });
    await row(NEW_SHOW.name);
    act(() => {
      window.dispatchEvent(new Event("pagehide"));
    });
    expect(await findToast("Couldn't mark items as seen")).toHaveTextContent("down");
  });

  it("marks nothing just for opening the page, even under StrictMode's double mount", async () => {
    function ComeAndGo() {
      const [open, setOpen] = useState(true);
      return (
        <>
          <button onClick={() => setOpen((o) => !o)}>come and go</button>
          {open && (
            <StrictMode>
              <FeedsPage />
            </StrictMode>
          )}
        </>
      );
    }
    const client = createFakeClient({
      listFeeds: async () => [TV, ANIME],
      listFeedItems: async () => ({ items: [NEW_SHOW], next_cursor: null }),
    });
    await renderWithApp(<ComeAndGo />, { client, route: "/feeds", path: "/feeds" });
    await row(NEW_SHOW.name);
    const toggle = screen.getByRole("button", { name: "come and go" });
    await userEvent.click(toggle);
    await waitFor(() => expect(client.markFeedItemsSeen).toHaveBeenCalledTimes(1));
    // Back again, with the items already loaded: StrictMode mounts, unmounts and remounts.
    await userEvent.click(toggle);
    await row(NEW_SHOW.name);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(client.markFeedItemsSeen).toHaveBeenCalledTimes(1);
  });

  it("loads more, up to the newest 200", { timeout: 30000 }, async () => {
    const page = (n: number): FeedItem[] =>
      Array.from({ length: 50 }, (_, i) =>
        makeFeedItem({ info_hash: `p${n}-${i}`, name: `Item ${n}-${i}` }),
      );
    const listFeedItems = vi.fn(async ({ cursor }: ListFeedItemsQuery) => {
      const n = cursor ? Number(cursor) : 0;
      return { items: page(n), next_cursor: String(n + 1) };
    });
    await setup({ listFeedItems });
    for (let n = 1; n < 4; n++) {
      await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
      await screen.findByRole("listitem", { name: `Item ${n}-0` });
    }
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    expect(screen.getByText(/Showing the newest 200 items/)).toBeInTheDocument();
  });

  it.each<[string, Partial<CharonClient>]>([
    ["feeds", { listFeeds: async () => Promise.reject(new Error("Charon is down")) }],
    ["items", { listFeedItems: async () => Promise.reject(new Error("Charon is down")) }],
  ])("offers to retry when the %s can't be loaded", async (_label, overrides) => {
    await setup(overrides);
    expect(await screen.findByText("Charon is down")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("reports each of two quick downloads, keeping both busy until they finish", async () => {
    const pending = { h1: deferred<Submission>(), h2: deferred<Submission>() };
    await setup({ downloadFeedItem: (hash) => pending[hash as keyof typeof pending].promise });
    await userEvent.click(await downloadButton(NEW_SHOW.name));
    await userEvent.click(await downloadButton(OLD_SHOW.name));
    expect(await downloadButton(NEW_SHOW.name)).toBeDisabled();
    expect(await downloadButton(OLD_SHOW.name)).toBeDisabled();
    pending.h1.reject(
      new ApiError(502, { code: "downloader_unreachable", message: "NAS offline" }),
    );
    pending.h2.resolve({ job: makeJob({ id: "j2" }), created: true });
    expect(await findToast("Couldn't start the download")).toHaveTextContent("NAS offline");
    // Toasts outlive a test, so look for this item's own success toast.
    await waitFor(() =>
      expect(
        screen
          .getAllByText("Download started")
          .some((title) =>
            title.closest("[data-sonner-toast]")?.textContent?.includes(OLD_SHOW.name),
          ),
      ).toBe(true),
    );
    await waitFor(async () => expect(await downloadButton(NEW_SHOW.name)).toBeEnabled());
  });

  it("doesn't send a download again while it is on its way", async () => {
    const submission = deferred<Submission>();
    const { client } = await setup({ downloadFeedItem: () => submission.promise });
    await row(NEW_SHOW.name);
    fireEvent.keyDown(document.body, { key: "j" });
    fireEvent.keyDown(document.activeElement!, { key: "d" });
    await waitFor(async () => expect(await downloadButton(NEW_SHOW.name)).toBeDisabled());
    fireEvent.keyDown(document.activeElement!, { key: "d" });
    fireEvent.click(await downloadButton(NEW_SHOW.name));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(client.downloadFeedItem).toHaveBeenCalledTimes(1);
    submission.resolve({ job: makeJob(), created: true });
    await findToast("Download started");
  });

  it("acts on no row with d, x or Enter until you pick one", async () => {
    const { client } = await setup();
    await row(NEW_SHOW.name);
    for (const key of ["d", "x", "Enter"]) fireEvent.keyDown(document.body, { key });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(client.downloadFeedItem).not.toHaveBeenCalled();
    expect(screen.queryByRole("toolbar", { name: "Selected items" })).not.toBeInTheDocument();
    expect(await row(NEW_SHOW.name)).toHaveAttribute("aria-expanded", "false");
    // The first row is still where Tab lands.
    expect(await row(NEW_SHOW.name)).toHaveAttribute("tabindex", "0");
  });

  it("goes back to all feeds when the feed you're viewing is unsubscribed", async () => {
    let feeds = [TV, ANIME];
    const { client, router } = await setup(
      {
        listFeeds: async () => feeds,
        deleteFeed: async (id) => {
          feeds = feeds.filter((feed) => feed.id !== id);
        },
      },
      "/feeds?feed=tv",
    );
    await row(NEW_SHOW.name);
    await userEvent.click(screen.getByRole("button", { name: "Settings for TV" }));
    await userEvent.click(await screen.findByRole("button", { name: /Unsubscribe/ }));
    await userEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Unsubscribe" }),
    );
    await waitFor(() => expect(router.state.location.search).toBe(""));
    await waitFor(() => expect(lastQuery(client).feedId).toBeNull());
  });

  it.each<[string, string, (() => Promise<void>) | null]>([
    [
      "a magnet whose tracker is an http address",
      "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&tr=http://t.example:6969/announce",
      null,
    ],
    ["text that only mentions an address", "see https://t.example/rss for more", null],
    [
      "an address pasted while a settings sheet is open",
      "https://t.example/rss?passkey=new",
      async () => {
        await userEvent.click(screen.getByRole("button", { name: "Settings for TV" }));
        await screen.findByRole("dialog", { name: "TV" });
      },
    ],
  ])("doesn't take %s for a new feed", async (_label, text, before) => {
    const { client } = await setup();
    await row(NEW_SHOW.name);
    await before?.();
    paste(text);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole("dialog", { name: "Add a feed" })).not.toBeInTheDocument();
    expect(client.previewFeed).not.toHaveBeenCalled();
  });

  it("leaves a paste alone that something else already handled", async () => {
    await setup();
    await row(NEW_SHOW.name);
    const handled = (event: Event) => event.preventDefault();
    document.body.addEventListener("paste", handled);
    try {
      paste("https://t.example/rss");
    } finally {
      document.body.removeEventListener("paste", handled);
    }
    expect(screen.queryByRole("dialog", { name: "Add a feed" })).not.toBeInTheDocument();
  });

  it("leaves keys alone while a settings sheet's picker is open", async () => {
    const { client } = await setup({
      downloadFeedItem: async () => ({ job: makeJob(), created: true }),
    });
    await row(NEW_SHOW.name);
    fireEvent.keyDown(document.body, { key: "j" }); // a row is picked, so "d" would act
    await userEvent.click(screen.getByRole("button", { name: "Settings for TV" }));
    await screen.findByRole("dialog", { name: "TV" });
    await userEvent.click(screen.getByRole("combobox", { name: "Check every" }));
    const option = await screen.findByRole("option", { name: "15 min" });
    await waitFor(() => expect(option).toHaveFocus());
    for (const key of ["j", "d", "x"]) fireEvent.keyDown(option, { key });
    await new Promise((resolve) => setTimeout(resolve, 50)); // a download would be sent by now
    expect(client.downloadFeedItem).not.toHaveBeenCalled();
    expect(screen.queryByRole("toolbar", { name: "Selected items" })).not.toBeInTheDocument();
  });
});
