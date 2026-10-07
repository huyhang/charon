import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { ADMIN_KEY, completeFakeTask, signIn, token } from "./helpers";

// Charon fetches feeds itself, so it needs the fake's own address, not the dev proxy's.
const FAKE_DS_URL = process.env.FAKE_DS_URL ?? "http://127.0.0.1:5000";
// Each run subscribes to its own address for the fake's TV feed (the fake ignores the query):
// Charon refuses a second subscription to one address, and `make ui-seed` has the plain one.
const tvFeed = (run: string) => `${FAKE_DS_URL}/feeds/tv.xml?e2e=${run}`;
const ADMIN = { "X-API-Key": ADMIN_KEY };

async function fake(request: APIRequestContext, path: string, data?: object) {
  expect((await request.post(`/_fake/_control/feeds/tv/${path}`, { data })).ok()).toBe(true);
}

async function subscribe(request: APIRequestContext, name: string, run: string): Promise<void> {
  const response = await request.post("/api/v1/feeds", {
    data: { name, url: tvFeed(run) },
    headers: ADMIN,
  });
  expect(response.ok()).toBe(true);
}

/** Removes what a test made, by name, so runs don't pile up in the dev database. */
async function removeNamed(request: APIRequestContext, kind: "feeds" | "rules", name: string) {
  const all: { id: string; name: string }[] = await (
    await request.get(`/api/v1/${kind}`, { headers: ADMIN })
  ).json();
  for (const { id } of all.filter((thing) => thing.name === name)) {
    await request.delete(`/api/v1/${kind}/${id}`, { headers: ADMIN });
  }
}

/** Fetches every enabled feed again, e.g. so the sample feeds forget a failure a test caused. */
async function refreshFeeds(request: APIRequestContext) {
  expect((await request.post("/api/v1/feeds/refresh", { headers: ADMIN })).ok()).toBe(true);
}

test("subscribes to a feed, then files a new item with a rule made from it", async ({
  page,
  request,
}) => {
  const run = token();
  // No sample rule matches this name (`make ui-seed` adds one for SxxEyy names).
  const name = `E2E.${run}.Feed.Special.1080p.mkv`;
  try {
    await subscribeAndFile(page, request, run, name);
  } finally {
    await removeNamed(request, "feeds", `e2e ${run}`);
    await removeNamed(request, "rules", `E2E ${run} Feed Special`);
  }
});

async function subscribeAndFile(page: Page, request: APIRequestContext, run: string, name: string) {
  await signIn(page);
  await page.getByRole("link", { name: /Feeds/ }).first().click();

  await page.getByRole("button", { name: /Add (your first )?feed/ }).click();
  const dialog = page.getByRole("dialog", { name: "Add a feed" });
  await dialog.getByRole("textbox", { name: "Address" }).fill(tvFeed(run));
  await expect(dialog.getByText("Fake Tracker · TV").first()).toBeVisible();
  await dialog.getByRole("textbox", { name: "Name" }).fill(`e2e ${run}`);
  await dialog.getByRole("button", { name: "Subscribe" }).click();
  await expect(page.getByRole("button", { name: new RegExp(`^e2e ${run}`) })).toBeVisible();

  await fake(request, "publish", { name });
  await page.getByRole("button", { name: /Refresh/ }).click();
  const row = page.getByRole("listitem", { name, exact: true });
  await expect(row.getByText("No rule")).toBeVisible();

  await row.click();
  await row.getByRole("link", { name: "Create rule from this" }).click();
  const editor = page.getByRole("dialog", { name: "New rule" });
  await expect(editor.getByLabel("Pattern", { exact: true })).toHaveValue(
    `E2E.${run}.Feed.Special.*`,
  );
  await expect(editor.getByLabel("Sample name")).toHaveValue(name);
  const destination = editor.getByLabel("Destination", { exact: true });
  const root = (await destination.inputValue()).replace(/\/$/, "");
  await destination.fill(`${root}/e2e-${run}`);
  await editor.getByRole("button", { name: "Create rule" }).click();

  await page.getByRole("link", { name: /Feeds/ }).first().click();
  await expect(row.getByText(`E2E ${run} Feed Special`)).toBeVisible();
  await row.getByRole("button", { name: `Download ${name}`, exact: true }).click();
  await expect(page.getByText("Download started").first()).toBeVisible();
  await completeFakeTask(request, name);
  await expect(row.getByText("Done")).toBeVisible();

  await page.getByRole("button", { name: `Settings for e2e ${run}` }).click();
  await page.getByRole("button", { name: "Unsubscribe" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Unsubscribe" }).click();
  await expect(page.getByRole("button", { name: new RegExp(`^e2e ${run}`) })).toHaveCount(0);
}

test("a feed that stops working says why, until it works again", async ({ page, request }) => {
  const run = token();
  await signIn(page);
  await subscribe(request, `broken ${run}`, run);
  await fake(request, "break", { mode: "http_error" });
  try {
    await page.goto("/feeds");
    await page.getByRole("button", { name: new RegExp(`^broken ${run}`) }).click();
    await page.getByRole("button", { name: /Refresh/ }).click();
    const alert = page.getByRole("alert").filter({ hasText: `broken ${run}` });
    await expect(alert).toContainText("503 Service Unavailable");
    await fake(request, "heal");
    await page.getByRole("button", { name: /Refresh/ }).click();
    await expect(alert).toHaveCount(0);
  } finally {
    await fake(request, "heal");
    await removeNamed(request, "feeds", `broken ${run}`);
    // The sample feeds read the same fake feed and may have been checked while it was broken.
    await refreshFeeds(request);
  }
});

test("on a phone, an item's name gets the row's whole width", async ({ page, request }) => {
  const run = token();
  await subscribe(request, `phone ${run}`, run);
  try {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page);
    await page.goto("/feeds");
    const row = page.getByRole("listitem").first();
    const rowBox = await row.boundingBox();
    const nameBox = await row.getByRole("heading", { level: 3 }).boundingBox();
    expect(nameBox!.width).toBeGreaterThan(rowBox!.width * 0.7);
  } finally {
    await removeNamed(request, "feeds", `phone ${run}`);
  }
});

// Real feeds have long release names, titles and rule names; none should push past the dialog.
const LONG = {
  name: "Injected.By.This.Test.An.Extraordinarily.Long.Release.Name.S01E01.2160p.WEB-DL.DDP5.1.Atmos.DV.HDR10Plus.H.265-GROUP.mkv",
  title: `Tracker${"X".repeat(120)}`,
  rule: "A rule with a really quite remarkably long descriptive name for TV",
};

for (const [device, viewport] of [
  ["a desktop", { width: 1400, height: 900 }],
  ["a phone", { width: 390, height: 844 }],
] as const) {
  test(`on ${device}, a new feed's preview keeps long names inside the dialog`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.route("**/api/v1/feeds/preview", async (route) => {
      const response = await route.fetch();
      const preview = await response.json();
      preview.title = LONG.title;
      preview.items[0].name = LONG.name;
      preview.items.find((item: { match: unknown }) => item.match).match.rule_name = LONG.rule;
      await route.fulfill({ response, json: preview });
    });
    await signIn(page);
    await page.goto("/feeds");
    await page
      .getByRole("button", { name: /Add (your first )?feed/ })
      .first()
      .click();
    const dialog = page.getByRole("dialog", { name: "Add a feed" });
    await dialog.getByRole("textbox", { name: "Address" }).fill(tvFeed(token()));
    await expect(dialog.getByText(LONG.name)).toBeVisible();
    const outside = await dialog.evaluate((box) => {
      const edge = box.getBoundingClientRect().right;
      const spills = (el: Element) =>
        !["INPUT", "TEXTAREA"].includes(el.tagName) &&
        el.scrollWidth > el.clientWidth + 1 &&
        getComputedStyle(el).overflowX === "visible";
      return [...box.querySelectorAll("*")]
        .filter((el) => el.getBoundingClientRect().right > edge + 0.5 || spills(el))
        .map((el) => el.textContent?.slice(0, 40));
    });
    expect(outside).toEqual([]);
  });
}
