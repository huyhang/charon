import { expect, test } from "@playwright/test";
import { completeFakeTask, magnet, signIn, token } from "./helpers";

test("rejects a wrong key, then signs in and out", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("API key").fill("not-a-key");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("alert")).toBeVisible();

  await signIn(page);
  await page.getByRole("button", { name: "Account and settings" }).first().click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page.getByLabel("API key")).toBeVisible();
});

test("a rule built in the editor renames and files a download", async ({ page, request }) => {
  const run = token();
  await signIn(page);

  await page.getByRole("link", { name: "Rules" }).first().click();
  await page.getByRole("button", { name: "New rule" }).click();
  const editor = page.getByRole("dialog", { name: "New rule" });
  await editor.getByLabel("Name", { exact: true }).fill(`e2e ${run}`);
  await editor.getByLabel("Pattern", { exact: true }).fill(`E2E.${run}.*`);
  await editor.getByRole("button", { name: /add step/i }).click();
  await editor.getByLabel("Step 1 find").fill("XYZ");
  await editor.getByLabel("Step 1 replace").fill("ABC");
  const destination = editor.getByLabel("Destination", { exact: true });
  const root = (await destination.inputValue()).replace(/\/$/, "");
  await destination.fill(`${root}/e2e-${run}`);
  await expect(editor.getByText(/will be created/)).toBeVisible();

  await editor.getByLabel("Sample name").fill(`E2E.${run}.XYZ.mkv`);
  await expect(editor.getByLabel("New name")).toHaveText(`E2E.${run}.ABC.mkv`);
  await editor.getByRole("button", { name: "Create rule" }).click();
  await expect(
    page.getByRole("list", { name: /priority order/ }).getByText(`e2e ${run}`),
  ).toBeVisible();

  const name = `E2E.${run}.XYZ.mkv`;
  await page.getByRole("link", { name: "Downloads" }).first().click();
  await page.getByLabel("Magnet link").fill(magnet(name));
  await expect(page.getByText(`Matches rule e2e ${run}`)).toBeVisible();
  await page.getByRole("button", { name: "Download", exact: true }).click();

  const card = page.getByRole("button", { name });
  await expect(card).toBeVisible();
  await completeFakeTask(request, name);
  await expect(card.getByText("Done")).toBeVisible();
  await expect(card.getByText(`${root}/e2e-${run}/E2E.${run}.ABC.mkv`)).toBeVisible();

  await card.click();
  await expect(page.getByRole("dialog", { name })).toContainText(`e2e ${run}`);
});

test("cancels a download after confirming", async ({ page }) => {
  const name = `Cancel.${token()}.mkv`;
  await signIn(page);
  await page.getByLabel("Magnet link").fill(magnet(name));
  await page.getByRole("button", { name: "Download", exact: true }).click();
  const card = page.getByRole("button", { name });
  await card.getByRole("button", { name: "Cancel" }).click();
  await page.getByRole("button", { name: "Cancel download" }).click();
  await expect(card.getByText("Cancelled", { exact: true })).toBeVisible();
});

test("issues a key that can sign in, then revokes it", async ({ page, browser }) => {
  const name = `e2e-${token()}`;
  await signIn(page);
  await page.getByRole("link", { name: "API keys" }).first().click();
  await page
    .getByRole("button", { name: /issue key/i })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name", { exact: true }).fill(name);
  await dialog.getByRole("button", { name: /issue key/i }).click();
  const secret = (await page.getByTestId("issued-key").textContent())!.trim();
  await page.getByRole("button", { name: "Done" }).click();

  const other = await browser.newPage();
  await signIn(other, secret);
  await expect(other.getByRole("link", { name: "API keys" })).toHaveCount(0);

  const row = page.getByRole("listitem").filter({ hasText: name });
  await row.getByRole("button", { name: "Revoke" }).click();
  await page.getByRole("button", { name: "Revoke key" }).click();
  await expect(row.getByText(/^revoked /)).toBeVisible();

  await other.reload();
  await expect(other.getByLabel("API key")).toBeVisible();
});

test("the command palette navigates", async ({ page }) => {
  await signIn(page);
  await page.keyboard.press("Control+k");
  await page.getByPlaceholder("Type a command or search…").fill("rules");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Rules" })).toBeVisible();
});
