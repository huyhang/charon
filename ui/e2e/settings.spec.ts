import { expect, test, type Page } from "@playwright/test";
import { signIn, token } from "./helpers";

// The dev stack (`make ui-dev`) gives Charon the fake TMDB's token through CHARON_TMDB_TOKEN.

async function lookUp(page: Page, title: string) {
  await page.getByRole("link", { name: "Rules" }).first().click();
  await page.getByRole("button", { name: "New rule" }).click();
  const editor = page.getByRole("dialog", { name: "New rule" });
  await editor.getByRole("button", { name: "Look up official title" }).click();
  const lookup = page.getByRole("dialog", { name: "Look up the official title" });
  await lookup.getByLabel("Title to look up").fill(title);
  return { editor, lookup };
}

test("a token saved in Settings is used until it is removed", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Settings" }).first().click();
  const tmdb = page.getByRole("region", { name: "TMDB title lookup" });
  await expect(tmdb.getByText("from CHARON_TMDB_TOKEN")).toBeVisible();

  await tmdb.getByRole("button", { name: "Replace" }).click();
  await tmdb.getByLabel("TMDB API Read Access Token").fill(`not-the-fakes-token-${token()}`);
  await tmdb.getByRole("button", { name: "Save" }).click();
  await expect(tmdb.getByText("saved in Charon")).toBeVisible();

  try {
    // Nothing remembered for a new title, so TMDB is asked, and refuses the token.
    const title = `Andor ${token()}`;
    const { editor, lookup } = await lookUp(page, title);
    await expect(lookup.getByText("TMDB rejected Charon's token")).toBeVisible();
    await lookup.getByRole("button", { name: "Close" }).click();
    await editor.getByRole("button", { name: "Cancel" }).click();
  } finally {
    await page.getByRole("link", { name: "Settings" }).first().click();
    await tmdb.getByRole("button", { name: "Remove" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Remove" }).click();
  }
  await expect(tmdb.getByText("from CHARON_TMDB_TOKEN")).toBeVisible();

  const { lookup } = await lookUp(page, "Frieren");
  await expect(lookup.getByRole("button", { name: /Use Frieren/ })).toBeVisible();
});
