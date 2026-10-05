import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CharonClient } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { Principal } from "@/api/types";
import { Toaster } from "@/components/ui/sonner";
import { createFakeClient } from "@/test/fakeClient";
import { ADMIN, makeKey } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { KeysPage, sortKeys } from "./KeysPage";

const PHONE = makeKey({ id: "key-1", name: "phone" });
const SIGNED_IN_AS_PHONE: Principal = { ...ADMIN, name: "phone", key_id: "key-1" };

/** The toast with this title. Sonner briefly renders a second copy while it animates in. */
async function findToast(title: string): Promise<HTMLElement> {
  const [toastTitle] = await screen.findAllByText(title);
  return toastTitle!.closest("[data-sonner-toast]") as HTMLElement;
}

async function renderKeys(overrides: Partial<CharonClient>, principal: Principal = ADMIN) {
  const client = createFakeClient({ listApiKeys: async () => [PHONE], ...overrides });
  await renderWithApp(
    <>
      <KeysPage />
      <Toaster />
    </>,
    { client, principal },
  );
  return client;
}

describe("sortKeys", () => {
  const key = (id: string, created: string, revoked: string | null = null) =>
    makeKey({ id, created_at: `2026-${created}T00:00:00Z`, revoked_at: revoked });
  it.each([
    [
      [key("old", "01-01"), key("revoked", "09-01", "2026-09-02"), key("new", "06-01")],
      ["new", "old", "revoked"],
    ],
    [
      [key("r1", "01-01", "x"), key("r2", "02-01", "x")],
      ["r2", "r1"],
    ],
    [[], []],
  ])("case %#: active keys first, newest first", (keys, expected) => {
    expect(sortKeys(keys).map((k) => k.id)).toEqual(expected);
  });
});

describe("KeysPage", () => {
  it("issues a key and shows the secret once", async () => {
    const issued = { ...makeKey({ id: "k2", name: "laptop" }), key: "chk_secret123" };
    const client = createFakeClient({ issueApiKey: async () => issued });
    await renderWithApp(<KeysPage />, { client });
    await userEvent.click(await screen.findByRole("button", { name: /issue your first key/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Name"), "laptop");
    await userEvent.click(within(dialog).getByRole("radio", { name: "Admin" }));
    await userEvent.click(within(dialog).getByRole("button", { name: /issue key/i }));
    expect(await screen.findByTestId("issued-key")).toHaveTextContent("chk_secret123");
    expect(client.issueApiKey).toHaveBeenCalledWith("laptop", "admin");
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.queryByText("chk_secret123")).not.toBeInTheDocument());
  });

  it("revokes after confirming, warning about the current key", async () => {
    const key = makeKey({ id: "key-1", name: "phone" });
    const client = createFakeClient({
      listApiKeys: async () => [key],
      revokeApiKey: async () => ({ ...key, revoked_at: "2026-10-04T12:00:00Z" }),
    });
    await renderWithApp(<KeysPage />, {
      client,
      principal: { name: "phone", role: "admin", key_id: "key-1", auth_enabled: true },
    });
    expect(await screen.findByText("this browser")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Revoke" }));
    expect(await screen.findByText(/You'll be signed out/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Revoke key" }));
    await waitFor(() => expect(client.revokeApiKey).toHaveBeenCalledWith("key-1"));
  });

  it("does not offer revoking a revoked key", async () => {
    const client = createFakeClient({
      listApiKeys: async () => [makeKey({ revoked_at: "2026-10-01T00:00:00Z" })],
    });
    await renderWithApp(<KeysPage />, { client });
    expect(await screen.findByText(/revoked/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revoke" })).not.toBeInTheDocument();
  });

  it.each<[string, Principal, string]>([
    ["the key this browser uses", SIGNED_IN_AS_PHONE, "You'll be signed out immediately."],
    ["another key", ADMIN, "rejected from its very next request"],
  ])("warns what revoking %s does", async (_label, principal, warning) => {
    await renderKeys({}, principal);
    await userEvent.click(await screen.findByRole("button", { name: "Revoke" }));
    expect(await screen.findByRole("alertdialog", { name: 'Revoke "phone"?' })).toHaveTextContent(
      warning,
    );
  });

  it.each<[string, Partial<CharonClient>, string, string]>([
    [
      "confirms a revocation",
      { revokeApiKey: async () => ({ ...PHONE, revoked_at: "2026-10-04T12:00:00Z" }) },
      "Key revoked",
      "phone can no longer sign in.",
    ],
    [
      "explains a failed revocation",
      {
        revokeApiKey: async () =>
          Promise.reject(new ApiError(404, { code: "key_not_found", message: "no such key" })),
      },
      "Couldn't revoke the key",
      "no such key",
    ],
  ])("%s", async (_label, overrides, title, description) => {
    const client = await renderKeys(overrides);
    await userEvent.click(await screen.findByRole("button", { name: "Revoke" }));
    await userEvent.click(await screen.findByRole("button", { name: "Revoke key" }));
    expect(await findToast(title)).toHaveTextContent(description);
    expect(client.revokeApiKey).toHaveBeenCalledWith("key-1");
  });

  it("keeps the key when the confirmation is dismissed", async () => {
    const client = await renderKeys({});
    await userEvent.click(await screen.findByRole("button", { name: "Revoke" }));
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(client.revokeApiKey).not.toHaveBeenCalled();
  });

  it("explains keys that can't be loaded, and tries again", async () => {
    const listApiKeys = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(409, { code: "auth_disabled", message: "auth is off" }))
      .mockResolvedValue([PHONE]);
    await renderKeys({ listApiKeys });
    expect(await screen.findByRole("alert")).toHaveTextContent("auth is off");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("phone")).toBeInTheDocument();
  });

  it("issues another key from the header", async () => {
    await renderKeys({});
    await screen.findByText("phone");
    await userEvent.click(screen.getByRole("button", { name: "Issue key" }));
    expect(await screen.findByRole("dialog", { name: "Issue an API key" })).toBeInTheDocument();
  });

  it.each<[string, "admin" | "client"]>([
    ["sonarr", "client"],
    ["ops", "admin"],
  ])("shows %s's role", async (name, role) => {
    await renderKeys({ listApiKeys: async () => [makeKey({ name, role })] });
    const row = (await screen.findByText(name)).closest("li") as HTMLElement;
    expect(within(row).getByText(role)).toBeInTheDocument();
  });
});
