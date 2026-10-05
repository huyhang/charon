import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import type { Principal } from "@/api/types";
import { createFakeClient } from "@/test/fakeClient";
import { ADMIN, CLIENT, makeJob } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { useTheme } from "@/theme/ThemeProvider";
import { CommandPalette, useCommandPaletteShortcut } from "./CommandPalette";

const ANONYMOUS: Principal = {
  name: "anonymous",
  role: "admin",
  key_id: null,
  auth_enabled: false,
};

/** The palette as the shell uses it: toggled by the shortcut, with the theme on show. */
function Harness() {
  const [open, setOpen] = useState(false);
  useCommandPaletteShortcut(() => setOpen((value) => !value));
  const { theme } = useTheme();
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open palette
      </button>
      <output aria-label="theme">{theme}</output>
      <CommandPalette open={open} onOpenChange={setOpen} />
    </>
  );
}

async function openPalette(options: Parameters<typeof renderWithApp>[1] = {}) {
  const app = await renderWithApp(<Harness />, options);
  await userEvent.click(screen.getByRole("button", { name: "open palette" }));
  await screen.findByRole("dialog", { name: "Command palette" });
  return app;
}

const location = (router: Awaited<ReturnType<typeof renderWithApp>>["router"]) =>
  `${router.state.location.pathname}${router.state.location.search}`;

describe("CommandPalette", () => {
  afterEach(() => document.documentElement.classList.remove("dark"));

  it.each<[string, string]>([
    ["Add a magnet link", "/downloads?add=1"],
    ["New rule", "/rules?new=1"],
    ["Downloads", "/downloads"],
    ["Rules", "/rules"],
    ["API keys", "/keys"],
  ])("%s goes to %s and closes", async (option, destination) => {
    const { router } = await openPalette();
    await userEvent.click(screen.getByRole("option", { name: option }));
    await waitFor(() => expect(location(router)).toBe(destination));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("lists recent downloads only once opened, and opens one", async () => {
    const client = createFakeClient({
      listDownloads: async () => ({
        items: [
          makeJob({ id: "j1", name: "Show.S01E01.mkv", status: "downloading" }),
          makeJob({ id: "j2", name: null, magnet: "magnet:?xt=urn:btih:abc", status: "failed" }),
        ],
        next_cursor: null,
      }),
    });
    const app = await renderWithApp(<Harness />, { client });
    expect(client.listDownloads).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "open palette" }));
    const show = await screen.findByRole("option", { name: /^Show\.S01E01\.mkv/ });
    expect(show).toHaveTextContent("Show.S01E01.mkvDownloading");
    expect(screen.getByRole("option", { name: /^Unnamed download/ })).toHaveTextContent("Failed");
    expect(client.listDownloads).toHaveBeenCalledWith({ limit: 8 });
    await userEvent.click(show);
    await waitFor(() => expect(location(app.router)).toBe("/downloads/j1"));
  });

  it("hides the recent group when there are no downloads", async () => {
    await openPalette();
    expect(screen.queryByText("Recent downloads")).not.toBeInTheDocument();
  });

  it.each<[string, string, boolean]>([
    ["Dark theme", "dark", true],
    ["Light theme", "light", false],
    ["System theme", "system", false],
  ])("%s switches the theme", async (option, theme, dark) => {
    await openPalette();
    await userEvent.click(screen.getByRole("option", { name: option }));
    expect(screen.getByLabelText("theme")).toHaveTextContent(theme);
    expect(document.documentElement.classList.contains("dark")).toBe(dark);
  });

  it.each<[string, Principal, boolean, boolean]>([
    ["admin", ADMIN, true, true],
    ["client", CLIENT, false, true],
    ["auth disabled", ANONYMOUS, false, false],
  ])("%s: API keys=%s, sign out=%s", async (_label, principal, keys, signOut) => {
    await openPalette({ principal });
    expect(screen.queryByRole("option", { name: "API keys" }) !== null).toBe(keys);
    expect(screen.queryByRole("option", { name: "Sign out" }) !== null).toBe(signOut);
  });

  it("signs out", async () => {
    await openPalette();
    await userEvent.click(screen.getByRole("option", { name: "Sign out" }));
    await waitFor(() => expect(screen.queryByTestId("signed-in")).not.toBeInTheDocument());
  });

  it.each<[string, string[], boolean]>([
    ["rul", ["New rule", "Rules"], false],
    ["zzz", [], true],
  ])("typing %j narrows the options", async (query, expected, empty) => {
    await openPalette();
    await userEvent.type(screen.getByPlaceholderText("Type a command or search…"), query);
    await waitFor(() =>
      expect(screen.queryAllByRole("option").map((option) => option.textContent?.trim())).toEqual(
        expected,
      ),
    );
    expect(screen.queryByText("No results.") !== null).toBe(empty);
  });

  it.each<[string, string, boolean]>([
    ["Ctrl+K opens it", "{Control>}k{/Control}", true],
    ["Cmd+K opens it", "{Meta>}k{/Meta}", true],
    ["K alone does nothing", "k", false],
  ])("%s", async (_label, keys, opens) => {
    await renderWithApp(<Harness />);
    await userEvent.keyboard(keys);
    expect(screen.queryByRole("dialog") !== null).toBe(opens);
  });

  it("the shortcut closes it again", async () => {
    await openPalette();
    await userEvent.keyboard("{Control>}k{/Control}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
