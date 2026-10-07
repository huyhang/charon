import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FeedItem } from "@/api/types";
import { createFakeClient } from "@/test/fakeClient";
import { makeFeedItem, makeRule } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { FeedItemRow } from "./FeedItemRow";

async function setup(item: FeedItem, { expanded = false, pending = false } = {}) {
  const handlers = {
    onToggleExpanded: vi.fn(),
    onToggleSelected: vi.fn(),
    onDownload: vi.fn(),
    onFocus: vi.fn(),
  };
  const client = createFakeClient({
    listRules: async () => [
      makeRule({ id: "tv", name: "TV" }),
      makeRule({ id: "mv", name: "Movies" }),
    ],
  });
  const result = await renderWithApp(
    <ul>
      <FeedItemRow
        item={item}
        tabStop
        expanded={expanded}
        selected={false}
        pending={pending}
        {...handlers}
      />
    </ul>,
    { client },
  );
  return { ...result, ...handlers };
}

const job = (status: "downloading" | "done" | "cancelled", percent = 0) => ({
  id: "j1",
  status,
  percent,
  error_code: null,
});

describe("FeedItemRow", () => {
  it("summarizes the item", async () => {
    await setup(makeFeedItem({ auto_downloaded: true, published_estimated: true }));
    const row = screen.getByRole("listitem");
    expect(row).toHaveTextContent("TV");
    expect(row).toHaveTextContent("≈");
    expect(row).toHaveTextContent("1.4 GB");
    expect(within(row).getByText("Auto")).toBeInTheDocument();
    expect(within(row).getByLabelText("New")).toBeInTheDocument();
  });

  it("toggles details on click, Space, and selection on its checkbox", async () => {
    const { onToggleExpanded, onToggleSelected } = await setup(makeFeedItem());
    await userEvent.click(screen.getByRole("listitem"));
    screen.getByRole("listitem").focus();
    await userEvent.keyboard(" ");
    expect(onToggleExpanded).toHaveBeenCalledTimes(2);
    await userEvent.click(screen.getByRole("checkbox"));
    expect(onToggleSelected).toHaveBeenCalledTimes(1);
    expect(onToggleExpanded).toHaveBeenCalledTimes(2);
  });

  it("shows the rename and folder when expanded", async () => {
    await setup(makeFeedItem(), { expanded: true });
    const row = screen.getByRole("listitem");
    expect(row).toHaveTextContent("Filed by TV");
    expect(row).toHaveTextContent("/library/tv");
    expect(row).toHaveTextContent("Listed as “Some Show S01E02 1080p”");
  });

  it.each<[string, Partial<FeedItem>, RegExp]>([
    [
      "a broken rule",
      {
        match: null,
        match_error: {
          code: "unsafe_name",
          message: "renamed to a/b",
          hint: "Fix the rule's steps.",
        },
      },
      /renamed to a\/bFix the rule's steps\./,
    ],
    [
      "a failed auto-download",
      { auto_error: "NAS offline" },
      /Auto-download couldn't start it: NAS offline/,
    ],
    ["a missing date", { published_estimated: true }, /the feed gave no date/],
  ])("explains %s when expanded", async (_label, overrides, text) => {
    await setup(makeFeedItem(overrides), { expanded: true });
    expect(screen.getByRole("listitem")).toHaveTextContent(text);
  });

  it("offers to create a rule for an unmatched item", async () => {
    await setup(makeFeedItem({ match: null, name: "Mystery.mkv" }), { expanded: true });
    expect(screen.getByRole("link", { name: "Create rule from this" })).toHaveAttribute(
      "href",
      "/rules?new=1&sample=Mystery.mkv",
    );
  });

  it("downloads with the matching rule, or a chosen one", async () => {
    const { onDownload, onToggleExpanded } = await setup(makeFeedItem());
    await userEvent.click(
      screen.getByRole("button", { name: "Download Some.Show.S01E02.1080p.mkv" }),
    );
    expect(onDownload).toHaveBeenLastCalledWith(null);
    await userEvent.click(screen.getByRole("button", { name: /with a rule/ }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Movies" }));
    expect(onDownload).toHaveBeenLastCalledWith("mv");
    expect(onToggleExpanded).not.toHaveBeenCalled();
  });

  it("says when there are no rules to choose from", async () => {
    await renderWithApp(
      <ul>
        <FeedItemRow
          item={makeFeedItem()}
          tabStop={false}
          expanded={false}
          selected
          pending={false}
          onToggleExpanded={() => {}}
          onToggleSelected={() => {}}
          onDownload={() => {}}
          onFocus={() => {}}
        />
      </ul>,
    );
    await userEvent.click(screen.getByRole("button", { name: /with a rule/ }));
    expect(await screen.findByRole("menuitem", { name: "No rules yet" })).toBeInTheDocument();
  });

  it("is busy while downloading", async () => {
    await setup(makeFeedItem(), { pending: true });
    expect(
      screen.getByRole("button", { name: "Download Some.Show.S01E02.1080p.mkv" }),
    ).toBeDisabled();
  });

  it.each<[string, ReturnType<typeof job>, string]>([
    ["downloading", job("downloading", 42), "42%"],
    ["done", job("done", 100), "Done"],
  ])(
    "shows a torrent already in Charon as %s, with a link to it",
    async (_label, itemJob, badge) => {
      await setup(makeFeedItem({ job: itemJob }));
      expect(screen.getByText(badge)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /^Download/ })).not.toBeInTheDocument();
      expect(screen.getByRole("link", { name: /Open the download/ })).toHaveAttribute(
        "href",
        "/downloads/j1",
      );
    },
  );

  it("offers to download again a torrent whose download was cancelled", async () => {
    await setup(makeFeedItem({ job: job("cancelled") }));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Download Some.Show.S01E02.1080p.mkv" }),
      ).toBeEnabled(),
    );
  });
});
