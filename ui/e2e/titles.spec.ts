import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

// The dev stack (`make ui-dev`) points Charon at the fake TMDB, which knows these titles.
test("looks up a release's official title on TMDB and renames it in the rule", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Rules" }).first().click();
  await page.getByRole("button", { name: "New rule" }).click();
  const editor = page.getByRole("dialog", { name: "New rule" });
  await editor.getByLabel("Pattern", { exact: true }).fill("Kusuriya.no.Hitorigoto.*");
  await editor.getByLabel("Sample name").fill("Kusuriya.no.Hitorigoto.S02E12.1080p.mkv");

  await editor.getByRole("button", { name: "Look up official title" }).click();
  const lookup = page.getByRole("dialog", { name: "Look up the official title" });
  await expect(lookup.getByLabel("Title to look up")).toHaveValue("Kusuriya no Hitorigoto");
  await expect(lookup.getByRole("img", { name: "TMDB" })).toBeVisible();
  await lookup.getByLabel("Include year").click();
  await expect(lookup.getByText("→ The.Apothecary.Diaries.(2023)")).toBeVisible();
  await lookup.getByRole("button", { name: "Use The Apothecary Diaries" }).click();

  await expect(lookup).toBeHidden();
  await expect(editor.getByLabel("Name", { exact: true })).toHaveValue("The Apothecary Diaries");
  await expect(editor.getByLabel("Step 1 replace")).toHaveValue("The.Apothecary.Diaries.(2023)");
  await expect(editor.getByLabel("New name")).toHaveText(
    "The.Apothecary.Diaries.(2023).S02E12.1080p.mkv",
  );
  await editor.getByRole("button", { name: "Cancel" }).click();
});

test("About credits TMDB with its notice", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: "Account and settings" }).first().click();
  await page.getByRole("menuitem", { name: "About Charon" }).click();
  const about = page.getByRole("dialog", { name: "About Charon" });
  await expect(
    about.getByText("This product uses TMDB and the TMDB APIs but is not endorsed"),
  ).toBeVisible();
  await expect(about.getByRole("img", { name: "TMDB" })).toBeVisible();
});
