import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import type { CharonClient } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { Role } from "@/api/types";
import { Toaster } from "@/components/ui/sonner";
import { createFakeClient } from "@/test/fakeClient";
import { makeKey } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { IssueKeyDialog } from "./IssueKeyDialog";

const ISSUED = { ...makeKey({ id: "k2", name: "laptop" }), key: "chk_secret123" };

/** Owns the open state the way KeysPage does, so closing and reopening behave as in the app. */
function Harness() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Reopen
      </button>
      <IssueKeyDialog open={open} onOpenChange={setOpen} />
      <Toaster />
    </>
  );
}

async function renderDialog(overrides: Partial<CharonClient> = {}) {
  const client = createFakeClient({ issueApiKey: async () => ISSUED, ...overrides });
  await renderWithApp(<Harness />, { client });
  return { client, dialog: await screen.findByRole("dialog") };
}

async function issue(name = "laptop") {
  const dialog = screen.getByRole("dialog");
  await userEvent.type(within(dialog).getByLabelText("Name"), name);
  await userEvent.click(within(dialog).getByRole("button", { name: /issue key/i }));
  return screen.findByTestId("issued-key");
}

/** The toast with this title. Sonner briefly renders a second copy while it animates in. */
async function findToast(title: string): Promise<HTMLElement> {
  const [toastTitle] = await screen.findAllByText(title);
  return toastTitle!.closest("[data-sonner-toast]") as HTMLElement;
}

function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
}

describe("IssueKeyDialog", () => {
  it.each<[Role, string]>([
    ["client", "Can add downloads and manage rules."],
    ["admin", "Can also issue and revoke keys."],
  ])("issues a trimmed %s key and explains the role", async (role, hint) => {
    const { client, dialog } = await renderDialog();
    await userEvent.click(
      within(dialog).getByRole("radio", { name: role === "admin" ? "Admin" : "Client" }),
    );
    expect(dialog).toHaveTextContent(hint);
    expect(await issue("  laptop  ")).toHaveTextContent("chk_secret123");
    expect(client.issueApiKey).toHaveBeenCalledWith("laptop", role);
    expect(screen.getByRole("dialog", { name: "Key for laptop" })).toBeInTheDocument();
  });

  it.each([[""], ["   "]])("won't issue a key named %j", async (name) => {
    const { dialog } = await renderDialog();
    if (name) await userEvent.type(within(dialog).getByLabelText("Name"), name);
    expect(within(dialog).getByRole("button", { name: /issue key/i })).toBeDisabled();
  });

  it("is busy while the key is issued", async () => {
    const { dialog } = await renderDialog({ issueApiKey: () => new Promise(() => {}) });
    await userEvent.type(within(dialog).getByLabelText("Name"), "laptop");
    await userEvent.click(within(dialog).getByRole("button", { name: /issue key/i }));
    expect(within(dialog).getByRole("button", { name: /issue key/i })).toBeDisabled();
  });

  it("shows why Charon refused, next to the name", async () => {
    await renderDialog({
      issueApiKey: async () =>
        Promise.reject(
          new ApiError(409, { code: "auth_disabled", message: "set CHARON_ADMIN_API_KEY" }),
        ),
    });
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Name"), "laptop");
    await userEvent.click(within(dialog).getByRole("button", { name: /issue key/i }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("set CHARON_ADMIN_API_KEY");
    expect(within(dialog).getByRole("alert")).toHaveAttribute("id", "key-name-error");
    // Screen readers announce the error with the field.
    const name = within(dialog).getByLabelText("Name");
    expect(name).toBeInvalid();
    expect(name).toHaveAccessibleDescription("set CHARON_ADMIN_API_KEY");
  });

  it("copies the new key", async () => {
    const writeText = vi.fn(async () => {});
    stubClipboard(writeText);
    await renderDialog();
    await issue();
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith("chk_secret123");
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("says so when the key can't be copied", async () => {
    stubClipboard(async () => Promise.reject(new Error("Write permission denied")));
    await renderDialog();
    await issue();
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(await findToast("Couldn't copy")).toHaveTextContent("Write permission denied");
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
  });

  it.each<[string, boolean, boolean]>([
    ["before a key is issued, a click outside closes it", false, false],
    ["while the key is shown, a click outside keeps it open", true, true],
  ])("%s", async (_label, issueFirst, staysOpen) => {
    const { dialog } = await renderDialog();
    if (issueFirst) await issue();
    // The overlay behind the dialog; Radix makes the rest of the page ignore the pointer.
    const overlay = dialog.previousElementSibling as HTMLElement;
    await userEvent.setup({ pointerEventsCheck: 0 }).click(overlay);
    if (staysOpen) {
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(screen.getByTestId("issued-key")).toBeInTheDocument();
    } else {
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    }
  });

  it("forgets the key once done, so reopening starts over", async () => {
    await renderDialog();
    await issue();
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Reopen" }));
    const dialog = await screen.findByRole("dialog", { name: "Issue an API key" });
    expect(within(dialog).queryByText("chk_secret123")).not.toBeInTheDocument();
  });
});
