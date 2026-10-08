import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@/api/errors";
import type { CharonClient } from "@/api/client";
import type { TitleSearch } from "@/api/types";
import { createFakeClient } from "@/test/fakeClient";
import { CLIENT, makeTitle, TMDB } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { TitleLookup } from "./TitleLookup";

const APOTHECARY = makeTitle();
const MOVIE = makeTitle({
  id: "693134",
  kind: "movie",
  title: "Dune: Part Two",
  original_title: "Dune: Part Two",
  year: 2024,
  overview: "",
  url: "https://www.themoviedb.org/movie/693134",
});
const SAMPLE = "Kusuriya.no.Hitorigoto.S02E12.1080p.mkv";

const found = (results = [APOTHECARY, MOVIE], memory: Partial<TitleSearch> = {}): TitleSearch => ({
  attribution: TMDB,
  results,
  stale: false,
  age_seconds: 0,
  ...memory,
});
const HOURS = 3600;
const NOT_CONFIGURED = new ApiError(409, {
  code: "metadata_not_configured",
  message: "no key is set for metadata provider 'tmdb'",
  hint: "Title lookup needs a TMDB token.",
});

async function open(sample = SAMPLE, overrides: Partial<CharonClient> = {}) {
  const onPick = vi.fn();
  const client = createFakeClient({
    metadataProviders: async () => [TMDB],
    searchTitles: async () => found(),
    ...overrides,
  });
  await renderWithApp(<TitleLookup sample={sample} onPick={onPick} />, { client });
  await userEvent.click(await screen.findByRole("button", { name: "Look up official title" }));
  return { client, onPick, dialog: await screen.findByRole("dialog") };
}

describe("TitleLookup", () => {
  it("offers nothing when no provider is set up", async () => {
    const client = createFakeClient();
    await renderWithApp(<TitleLookup sample={SAMPLE} onPick={() => {}} />, { client });
    await waitFor(() => expect(client.metadataProviders).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /look up/i })).not.toBeInTheDocument();
  });

  it("searches for the title guessed from the sample name, and credits the provider", async () => {
    const { client, dialog } = await open();
    expect(within(dialog).getByLabelText("Title to look up")).toHaveValue("Kusuriya no Hitorigoto");
    expect(within(dialog).getByText("Kusuriya.no.Hitorigoto")).toBeInTheDocument();
    expect(await within(dialog).findByText("The Apothecary Diaries")).toBeInTheDocument();
    expect(client.searchTitles).toHaveBeenCalledWith({
      q: "Kusuriya no Hitorigoto",
      provider: "tmdb",
      kind: "any",
    });
    expect(within(dialog).getByText("薬屋のひとりごと")).toBeInTheDocument();
    expect(within(dialog).getByText("→ The.Apothecary.Diaries")).toBeInTheDocument();
    const [details] = within(dialog).getAllByRole("link", { name: /View on TMDB/ });
    expect(details).toHaveAttribute("href", APOTHECARY.url);
    const logo = within(dialog).getByRole("img", { name: "TMDB" });
    expect(logo.closest("a")).toHaveAttribute("href", "https://www.themoviedb.org");
  });

  it("hands back a step for the picked title, and closes", async () => {
    const { onPick, dialog } = await open();
    await userEvent.click(
      await within(dialog).findByRole("button", { name: "Use Dune: Part Two" }),
    );
    expect(onPick).toHaveBeenCalledWith(
      { op: "replace", find: "Kusuriya.no.Hitorigoto", replace: "Dune.Part.Two" },
      MOVIE,
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("adds the year when asked to", async () => {
    const { onPick, dialog } = await open();
    await userEvent.click(within(dialog).getByLabelText("Include year"));
    expect(await within(dialog).findByText("→ The.Apothecary.Diaries.(2023)")).toBeInTheDocument();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Use The Apothecary Diaries" }),
    );
    expect(onPick.mock.calls[0]![0].replace).toBe("The.Apothecary.Diaries.(2023)");
  });

  it.each([
    ["TV", "tv"],
    ["Movies", "movie"],
  ])("narrows the search to %s", async (label, kind) => {
    const { client, dialog } = await open();
    await within(dialog).findByText("The Apothecary Diaries");
    await userEvent.click(within(dialog).getByRole("radio", { name: label }));
    await waitFor(() =>
      expect(client.searchTitles).toHaveBeenLastCalledWith({
        q: "Kusuriya no Hitorigoto",
        provider: "tmdb",
        kind,
      }),
    );
  });

  it("without a sample name, replaces what was searched for", async () => {
    const { onPick, dialog } = await open("");
    const input = within(dialog).getByLabelText("Title to look up");
    expect(input).toHaveValue("");
    expect(within(dialog).getByText("Type a title to look it up.")).toBeInTheDocument();
    await userEvent.type(input, "Kusuriya no Hitorigoto");
    await userEvent.click(
      await within(dialog).findByRole("button", { name: "Use The Apothecary Diaries" }),
    );
    expect(onPick.mock.calls[0]![0]).toEqual({
      op: "replace",
      find: "Kusuriya no Hitorigoto",
      replace: "The Apothecary Diaries",
    });
  });

  it("waits for a pause in typing before searching", async () => {
    const { client, dialog } = await open("");
    await userEvent.type(within(dialog).getByLabelText("Title to look up"), "Frieren");
    await waitFor(() => expect(client.searchTitles).toHaveBeenCalledTimes(1));
    expect(client.searchTitles).toHaveBeenCalledWith({
      q: "Frieren",
      provider: "tmdb",
      kind: "any",
    });
  });

  it.each<[string, Partial<CharonClient>, string, string | null]>([
    [
      "Charon holding back for the provider",
      {
        searchTitles: async () =>
          Promise.reject(
            new ApiError(429, {
              code: "metadata_rate_limited",
              message: "too many searches right now; try again shortly",
              hint: "Wait a few seconds, then search again.",
            }),
          ),
      },
      "too many searches right now; try again shortly",
      "Wait a few seconds, then search again.",
    ],
    [
      "no results",
      { searchTitles: async () => found([]) },
      "No movies or shows match “Kusuriya no Hitorigoto”. Try the title in another language.",
      null,
    ],
  ])("says so for %s", async (_label, overrides, message, hint) => {
    const { dialog } = await open(SAMPLE, overrides);
    expect(await within(dialog).findByText(message, { exact: false })).toBeInTheDocument();
    if (hint) expect(within(dialog).getByText(hint)).toBeInTheDocument();
  });

  it("doesn't submit the rule form when the search is submitted (e.g. Enter)", async () => {
    const onSubmit = vi.fn((event: Event) => event.preventDefault());
    const client = createFakeClient({
      metadataProviders: async () => [TMDB],
      searchTitles: async () => found(),
    });
    await renderWithApp(
      <form onSubmit={(event) => onSubmit(event.nativeEvent)}>
        <TitleLookup sample={SAMPLE} onPick={() => {}} />
      </form>,
      { client },
    );
    await userEvent.click(await screen.findByRole("button", { name: "Look up official title" }));
    const search = screen.getByLabelText("Title to look up").closest("form")!;
    // Submitted directly: jsdom doesn't do the implicit submission a browser does on Enter.
    expect(fireEvent.submit(search)).toBe(false);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  describe("from Charon's memory", () => {
    it.each<[string, Partial<TitleSearch>, string | null]>([
      ["a fresh answer says nothing", { age_seconds: 5 }, null],
      ["a remembered one says how old", { age_seconds: 3 * HOURS }, "Remembered from 3h ago."],
      [
        "one standing in warns",
        { age_seconds: 26 * HOURS, stale: true },
        "TMDB couldn't be asked just now: these results are from 1d ago.",
      ],
    ])("%s", async (_label, memory, message) => {
      const { dialog } = await open(SAMPLE, { searchTitles: async () => found(undefined, memory) });
      await within(dialog).findByText("The Apothecary Diaries");
      const ask = within(dialog).queryByRole("button", { name: "Ask again" });
      if (message === null) {
        expect(ask).not.toBeInTheDocument();
      } else {
        expect(within(dialog).getByText(message, { exact: false })).toBeInTheDocument();
        expect(ask).toBeInTheDocument();
      }
    });

    it("asks the provider again on request, and shows the new answer", async () => {
      const searchTitles = vi
        .fn<CharonClient["searchTitles"]>()
        .mockResolvedValueOnce(found([APOTHECARY], { age_seconds: 26 * HOURS, stale: true }))
        .mockResolvedValueOnce(found([MOVIE]));
      const { client, dialog } = await open(SAMPLE, { searchTitles });
      await userEvent.click(await within(dialog).findByRole("button", { name: "Ask again" }));
      expect(await within(dialog).findByText("Dune: Part Two")).toBeInTheDocument();
      expect(client.searchTitles).toHaveBeenLastCalledWith({
        q: "Kusuriya no Hitorigoto",
        provider: "tmdb",
        kind: "any",
        refresh: true,
      });
      expect(within(dialog).queryByText(/couldn't be asked/)).not.toBeInTheDocument();
    });

    it("keeps the remembered answer, and says why, if asking again fails", async () => {
      const searchTitles = vi
        .fn<CharonClient["searchTitles"]>()
        .mockResolvedValueOnce(found([APOTHECARY], { age_seconds: 3 * HOURS }))
        .mockRejectedValueOnce(new Error("TMDB took too long to answer"));
      const { dialog } = await open(SAMPLE, { searchTitles });
      await userEvent.click(await within(dialog).findByRole("button", { name: "Ask again" }));
      expect(await within(dialog).findByRole("alert")).toHaveTextContent("took too long");
      expect(within(dialog).getByText("The Apothecary Diaries")).toBeInTheDocument();
    });
  });

  describe("before the provider has a key", () => {
    const UNCONFIGURED = { ...TMDB, configured: false };

    it("lets an admin save one right there, then search", async () => {
      const metadataProviders = vi
        .fn<CharonClient["metadataProviders"]>()
        .mockResolvedValueOnce([UNCONFIGURED])
        .mockResolvedValue([TMDB]);
      const saveProviderKey = vi.fn<CharonClient["saveProviderKey"]>(async (provider) => ({
        provider,
        configured: true,
        source: "settings",
        hint: "abcd",
      }));
      const { client, dialog } = await open(SAMPLE, { metadataProviders, saveProviderKey });
      expect(within(dialog).getByText(/needs a TMDB token first/)).toBeInTheDocument();
      expect(client.searchTitles).not.toHaveBeenCalled();
      await userEvent.type(
        within(dialog).getByLabelText("TMDB API Read Access Token"),
        "  eyJ.token.abcd ",
      );
      await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
      expect(saveProviderKey).toHaveBeenCalledWith("tmdb", "eyJ.token.abcd");
      expect(await within(dialog).findByLabelText("Title to look up")).toBeInTheDocument();
      expect(await within(dialog).findByText("The Apothecary Diaries")).toBeInTheDocument();
    });

    it("tells anyone else to ask an admin", async () => {
      const client = createFakeClient({ metadataProviders: async () => [UNCONFIGURED] });
      await renderWithApp(<TitleLookup sample={SAMPLE} onPick={() => {}} />, {
        client,
        principal: CLIENT,
      });
      await userEvent.click(await screen.findByRole("button", { name: "Look up official title" }));
      const dialog = await screen.findByRole("dialog");
      expect(within(dialog).getByText(/Ask an admin to add one in Settings/)).toBeInTheDocument();
      expect(within(dialog).queryByRole("textbox")).not.toBeInTheDocument();
    });

    it("offers to set one up if the key went away while the dialog was open", async () => {
      const { dialog } = await open(SAMPLE, {
        searchTitles: async () => Promise.reject(NOT_CONFIGURED),
      });
      expect(await within(dialog).findByText(/needs a TMDB token first/)).toBeInTheDocument();
      expect(within(dialog).getByLabelText("TMDB API Read Access Token")).toBeInTheDocument();
    });
  });
});
