import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CharonClient } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { ProviderKey } from "@/api/types";
import { Toaster } from "@/components/ui/sonner";
import { createFakeClient } from "@/test/fakeClient";
import { TMDB } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { findToast } from "@/test/toast";
import { ProviderKeyForm } from "./ProviderKeyForm";
import { SettingsPage } from "./SettingsPage";

const NONE: ProviderKey = { provider: "tmdb", configured: false, source: null, hint: null };
const SAVED: ProviderKey = { provider: "tmdb", configured: true, source: "settings", hint: "abcd" };
const FROM_ENV: ProviderKey = { ...SAVED, source: "environment", hint: "7890" };

async function renderPage(overrides: Partial<CharonClient> = {}) {
  const client = createFakeClient({ metadataProviders: async () => [TMDB], ...overrides });
  await renderWithApp(
    <>
      <SettingsPage />
      <Toaster />
    </>,
    { client },
  );
  return { client, section: await screen.findByRole("region", { name: "TMDB title lookup" }) };
}

describe("SettingsPage", () => {
  it("saves a token when none is set", async () => {
    const providerKey = vi
      .fn<CharonClient["providerKey"]>()
      .mockResolvedValueOnce(NONE)
      .mockResolvedValue(SAVED);
    const { client, section } = await renderPage({
      providerKey,
      saveProviderKey: async () => SAVED,
    });
    const input = await within(section).findByLabelText("TMDB API Read Access Token");
    expect(input).toHaveAttribute("type", "password");
    await userEvent.type(input, "  eyJ.token.abcd  ");
    await userEvent.click(within(section).getByRole("button", { name: "Save" }));
    expect(client.saveProviderKey).toHaveBeenCalledWith("tmdb", "eyJ.token.abcd");
    await findToast("TMDB api read access token saved");
    expect(
      await within(section).findByText("saved in Charon", { exact: false }),
    ).toBeInTheDocument();
    expect(within(section).getByText("…abcd")).toBeInTheDocument();
  });

  it("explains a token that can't be right, without saving it", async () => {
    const { section } = await renderPage({
      providerKey: async () => NONE,
      saveProviderKey: async () =>
        Promise.reject(
          new ApiError(422, {
            code: "metadata_key_wrong_kind",
            message: "that is TMDB's short API Key; paste the API Read Access Token instead",
            hint: "Copy the long one.",
          }),
        ),
    });
    await userEvent.type(
      await within(section).findByLabelText("TMDB API Read Access Token"),
      "0123456789abcdef0123456789abcdef",
    );
    await userEvent.click(within(section).getByRole("button", { name: "Save" }));
    const alert = await within(section).findByRole("alert");
    expect(alert).toHaveTextContent("short API Key");
    expect(alert).toHaveTextContent("Copy the long one.");
  });

  it("says a token from the environment can be replaced here, but not removed", async () => {
    const { client, section } = await renderPage({
      providerKey: async () => FROM_ENV,
      saveProviderKey: async () => SAVED,
    });
    expect(
      await within(section).findByText("from CHARON_TMDB_TOKEN", { exact: false }),
    ).toBeInTheDocument();
    expect(within(section).getByText("One saved here takes its place.")).toBeInTheDocument();
    expect(within(section).queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();

    await userEvent.click(within(section).getByRole("button", { name: "Replace" }));
    await userEvent.click(within(section).getByRole("button", { name: "Cancel" }));
    expect(within(section).getByRole("button", { name: "Replace" })).toBeInTheDocument();
    expect(client.saveProviderKey).not.toHaveBeenCalled();
  });

  it.each<[string, ProviderKey, string]>([
    [
      "the environment's applies again",
      FROM_ENV,
      "Charon uses the one from CHARON_TMDB_TOKEN again.",
    ],
    ["lookups stop", NONE, "Title lookup is off until a new one is saved."],
  ])("removes a saved token after confirming: %s", async (_label, after, description) => {
    const { client, section } = await renderPage({
      providerKey: async () => SAVED,
      removeProviderKey: async () => after,
    });
    await userEvent.click(await within(section).findByRole("button", { name: "Remove" }));
    const confirm = await screen.findByRole("alertdialog");
    await userEvent.click(within(confirm).getByRole("button", { name: "Remove" }));
    expect(client.removeProviderKey).toHaveBeenCalledWith("tmdb");
    const toast = await findToast("API Read Access Token removed");
    expect(toast).toHaveTextContent(description);
  });

  it("says when removing failed", async () => {
    const { section } = await renderPage({
      providerKey: async () => SAVED,
      removeProviderKey: async () => Promise.reject(new Error("offline")),
    });
    await userEvent.click(await within(section).findByRole("button", { name: "Remove" }));
    await userEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Remove" }),
    );
    expect(await findToast("Couldn't remove it")).toHaveTextContent("offline");
  });

  it("retries loading the token's status", async () => {
    const providerKey = vi
      .fn<CharonClient["providerKey"]>()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(SAVED);
    const { section } = await renderPage({ providerKey });
    await userEvent.click(await within(section).findByRole("button", { name: "Try again" }));
    expect(await within(section).findByText("…abcd")).toBeInTheDocument();
  });

  it.each<[string, Partial<CharonClient>, string]>([
    ["cleared", {}, "Remembered searches cleared"],
    [
      "failing",
      { clearTitleCache: async () => Promise.reject(new Error("offline")) },
      "Couldn't clear them",
    ],
  ])("clears remembered searches: %s", async (_label, overrides, title) => {
    const { client } = await renderPage({ providerKey: async () => SAVED, ...overrides });
    await userEvent.click(screen.getByRole("button", { name: "Clear remembered searches" }));
    await findToast(title);
    expect(client.clearTitleCache).toHaveBeenCalled();
  });

  it("retries loading the providers", async () => {
    const metadataProviders = vi
      .fn<CharonClient["metadataProviders"]>()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue([TMDB]);
    await renderWithApp(<SettingsPage />, { client: createFakeClient({ metadataProviders }) });
    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("region", { name: "TMDB title lookup" })).toBeInTheDocument();
  });
});

describe("ProviderKeyForm", () => {
  it("doesn't submit a form around it (e.g. the rule editor) when saved", async () => {
    const outer = vi.fn((event: Event) => event.preventDefault());
    const client = createFakeClient({ saveProviderKey: async () => SAVED });
    await renderWithApp(
      <form onSubmit={(event) => outer(event.nativeEvent)}>
        <ProviderKeyForm provider={TMDB} />
      </form>,
      { client },
    );
    const input = await screen.findByLabelText("TMDB API Read Access Token");
    await userEvent.type(input, "eyJ.token.abcd");
    // Submitted directly: jsdom doesn't do the implicit submission a browser does on Enter.
    expect(fireEvent.submit(input.closest("form")!)).toBe(false);
    await waitFor(() => expect(client.saveProviderKey).toHaveBeenCalled());
    expect(outer).not.toHaveBeenCalled();
  });

  it("describes the key of a provider it has no words for", async () => {
    await renderWithApp(<ProviderKeyForm provider={{ ...TMDB, id: "other", name: "Other" }} />);
    expect(await screen.findByLabelText("Other API key")).toBeInTheDocument();
    expect(screen.getByText("The key Other gave you.")).toBeInTheDocument();
  });
});
