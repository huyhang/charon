import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Principal } from "@/api/types";
import { memoryStore } from "@/lib/storage";
import { createFakeClient } from "@/test/fakeClient";
import { ADMIN, CLIENT } from "@/test/factories";
import { App } from "./App";

const ANONYMOUS: Principal = {
  name: "anonymous",
  role: "admin",
  key_id: null,
  auth_enabled: false,
};
const MAGNET = "magnet:?xt=urn:btih:abc&dn=The.Bear.S03E01.mkv";

/** The shell as users meet it: the whole app, signed in as `principal`, opened at `url`. */
async function renderShell(url = "/downloads", principal: Principal = ADMIN, unread = 0) {
  window.history.replaceState(null, "", url);
  const client = createFakeClient({
    me: async () => principal,
    feedSummary: async () => ({ unread, feeds: {} }),
  });
  render(<App client={client} keys={memoryStore("dev-key")} themeStore={memoryStore()} />);
  await screen.findByRole("navigation", { name: "Main" });
  return client;
}

const links = (nav: string) =>
  within(screen.getByRole("navigation", { name: nav }))
    .getAllByRole("link")
    .map((link) => link.textContent);

function pasteOnPage(text: string) {
  const event = new Event("paste", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "clipboardData", { value: { getData: () => text } });
  document.body.dispatchEvent(event);
}

describe("AppShell", () => {
  it.each<[string, Principal, string[]]>([
    ["admin", ADMIN, ["Downloads", "Feeds", "Rules", "API keys", "Settings"]],
    ["client", CLIENT, ["Downloads", "Feeds", "Rules"]],
    ["auth disabled", ANONYMOUS, ["Downloads", "Feeds", "Rules", "Settings"]],
  ])("%s sees these pages in both navigations", async (_label, principal, expected) => {
    await renderShell("/downloads", principal);
    expect(links("Main")).toEqual(expected);
    expect(links("Main mobile")).toEqual(expected);
  });

  it("shows how many feed items are new, in both navigations", async () => {
    await renderShell("/downloads", ADMIN, 4);
    for (const nav of ["Main", "Main mobile"]) {
      const feeds = within(screen.getByRole("navigation", { name: nav })).getByRole("link", {
        name: /Feeds/,
      });
      await waitFor(() => expect(within(feeds).getByLabelText("4 new")).toBeInTheDocument());
    }
  });

  it("opens the feed inbox", async () => {
    await renderShell("/downloads");
    const main = within(screen.getByRole("navigation", { name: "Main" }));
    await userEvent.click(main.getByRole("link", { name: "Feeds" }));
    expect(await screen.findByRole("heading", { name: "Feeds" })).toBeInTheDocument();
  });

  it("marks the current page and moves between pages", async () => {
    await renderShell("/downloads");
    const main = within(screen.getByRole("navigation", { name: "Main" }));
    expect(main.getByRole("link", { name: "Downloads" })).toHaveAttribute("aria-current", "page");
    await userEvent.click(main.getByRole("link", { name: "Rules" }));
    expect(await screen.findByRole("heading", { name: "Rules" })).toBeInTheDocument();
    expect(main.getByRole("link", { name: "Rules" })).toHaveAttribute("aria-current", "page");
    expect(main.getByRole("link", { name: "Downloads" })).not.toHaveAttribute("aria-current");
  });

  it.each<[string, RegExp]>([
    ["the sidebar search", /^Search or jump to…/],
    ["the phone header search", /^Search$/],
  ])("opens the command palette from %s", async (_label, button) => {
    await renderShell();
    await userEvent.click(screen.getByRole("button", { name: button }));
    expect(await screen.findByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
  });

  it("opens the command palette with the keyboard", async () => {
    await renderShell();
    await userEvent.keyboard("{Control>}k{/Control}");
    expect(await screen.findByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
  });

  it("takes a magnet pasted on any page to the downloads page, ready to submit", async () => {
    await renderShell("/rules");
    await screen.findByRole("heading", { name: "Rules" });
    pasteOnPage(`have a look at ${MAGNET} please`);
    expect(await screen.findByRole("heading", { name: "Downloads" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Magnet link")).toHaveValue(MAGNET));
    expect(window.location.pathname).toBe("/downloads");
  });

  it("shows connection status and the account menu in both layouts", async () => {
    await renderShell();
    await waitFor(() =>
      expect(screen.getAllByRole("status").map((status) => status.title)).toEqual([
        "Download Station connected",
        "Download Station connected",
      ]),
    );
    expect(screen.getAllByRole("button", { name: "Account and settings" })).toHaveLength(2);
    expect(screen.getAllByText("Charon").length).toBeGreaterThan(0);
  });
});
