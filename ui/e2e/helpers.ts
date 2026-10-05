import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const ADMIN_KEY = process.env.CHARON_E2E_API_KEY ?? "dev-key";

export function token(): string {
  return Math.random().toString(36).slice(2, 10);
}

export function magnet(name: string): string {
  return `magnet:?xt=urn:btih:${token()}${token()}&dn=${encodeURIComponent(name)}`;
}

export async function signIn(page: Page, key = ADMIN_KEY): Promise<void> {
  await page.goto("/");
  await page.getByLabel("API key").fill(key);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("heading", { name: "Downloads" })).toBeVisible();
}

/** Finishes the fake download for `name` now, through the dev proxy to the fake. */
export async function completeFakeTask(request: APIRequestContext, name: string): Promise<void> {
  await expect
    .poll(async () => {
      const tasks: { id: string; title: string }[] = await (
        await request.get("/_fake/_control/tasks")
      ).json();
      const task = tasks.find((t) => t.title === name);
      if (!task) return false;
      return (await request.post(`/_fake/_control/tasks/${task.id}/complete`)).ok();
    })
    .toBe(true);
}
