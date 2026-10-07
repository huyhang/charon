import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { queryKeys } from "@/api/queries";
import { Toaster } from "@/components/ui/sonner";
import { createFakeClient, type FakeClient } from "@/test/fakeClient";
import { makeFeed } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import SimulatorPanel from "./SimulatorPanel";
import type { FakeFeed, FakeTask, SimulatorClient } from "./simulatorClient";

function task(id: string, title: string, status: string, downloaded = "0"): FakeTask {
  return {
    id,
    title,
    size: "100",
    status,
    status_extra: null,
    additional: { transfer: { size_downloaded: downloaded, speed_download: 0 } },
  };
}

const TASKS = [
  task("dbid_1", "Show.S01E01.mkv", "downloading", "40"),
  task("dbid_2", "Movie.2024.mkv", "finished", "100"),
  task("dbid_3", "Broken.mkv", "error"),
];

function fakeSimulator(overrides: Partial<SimulatorClient> = {}) {
  return {
    listTasks: vi.fn(async () => TASKS),
    complete: vi.fn(async () => {}),
    fail: vi.fn(async () => {}),
    expireSessions: vi.fn(async () => {}),
    reset: vi.fn(async () => {}),
    listFeeds: vi.fn(async (): Promise<FakeFeed[]> => []),
    publish: vi.fn(async () => {}),
    breakFeed: vi.fn(async () => {}),
    healFeed: vi.fn(async () => {}),
    ...overrides,
  };
}

async function openPanel(simulator?: SimulatorClient, client?: FakeClient) {
  const result = await renderWithApp(
    <>
      <SimulatorPanel simulator={simulator} />
      <Toaster />
    </>,
    { client },
  );
  await userEvent.click(screen.getByRole("button", { name: "Simulator" }));
  return { ...result, panel: await screen.findByRole("dialog") };
}

/** The toast with this title. Sonner briefly renders a second copy while it animates in. */
async function findToast(title: string): Promise<HTMLElement> {
  const [toastTitle] = await screen.findAllByText(title);
  return toastTitle!.closest("[data-sonner-toast]") as HTMLElement;
}

/** The row of the task with this title. */
async function row(panel: HTMLElement, title: string): Promise<HTMLElement> {
  return (await within(panel).findByText(title)).closest("li") as HTMLElement;
}

describe("SimulatorPanel", () => {
  it("doesn't ask the fake for tasks until opened", async () => {
    const simulator = fakeSimulator();
    await renderWithApp(<SimulatorPanel simulator={simulator} />);
    expect(simulator.listTasks).not.toHaveBeenCalled();
  });

  it.each<[string, string, boolean]>([
    ["Show.S01E01.mkv", "downloading", true],
    ["Movie.2024.mkv", "finished", false],
    ["Broken.mkv", "error", false],
  ])("lists %s as %s, with controls only while downloading", async (title, status, controls) => {
    const { panel } = await openPanel(fakeSimulator());
    const item = await row(panel, title);
    expect(within(item).getByText(status)).toBeInTheDocument();
    expect(within(item).queryByRole("button", { name: "Complete" }) !== null).toBe(controls);
    expect(within(item).queryByRole("button", { name: "Fail" }) !== null).toBe(controls);
  });

  it.each<[string, keyof SimulatorClient, unknown[], string]>([
    ["Complete", "complete", ["dbid_1"], "Completed Show.S01E01.mkv"],
    ["Fail", "fail", ["dbid_1", "broken_link"], "Failed Show.S01E01.mkv"],
  ])("%s steers a downloading task", async (button, method, args, message) => {
    const simulator = fakeSimulator();
    const { panel } = await openPanel(simulator);
    const item = await row(panel, "Show.S01E01.mkv");
    await userEvent.click(within(item).getByRole("button", { name: button }));
    expect(await findToast(message)).toBeInTheDocument();
    expect(simulator[method]).toHaveBeenCalledWith(...args);
  });

  it.each<[string, keyof SimulatorClient, string]>([
    ["Expire sessions", "expireSessions", "Download Station sessions expired"],
    ["Reset fake", "reset", "Fake Download Station reset"],
  ])("%s", async (button, method, message) => {
    const simulator = fakeSimulator();
    const { panel } = await openPanel(simulator);
    await userEvent.click(within(panel).getByRole("button", { name: button }));
    expect(await findToast(message)).toBeInTheDocument();
    expect(simulator[method]).toHaveBeenCalledTimes(1);
  });

  it("refreshes the downloads soon after steering the fake", async () => {
    const { panel, queryClient } = await openPanel(fakeSimulator());
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    await userEvent.click(within(panel).getByRole("button", { name: "Reset fake" }));
    await waitFor(
      () => expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.downloads }),
      { timeout: 3000 },
    );
  });

  it("explains an action the fake refused", async () => {
    const simulator = fakeSimulator({
      reset: async () => Promise.reject(new Error("Fake Download Station answered 500")),
    });
    const { panel } = await openPanel(simulator);
    await userEvent.click(within(panel).getByRole("button", { name: "Reset fake" }));
    expect(await findToast("Simulator action failed")).toHaveTextContent(
      "Fake Download Station answered 500",
    );
  });

  it.each<[string, Partial<SimulatorClient>, string]>([
    ["no tasks", { listTasks: async () => [] }, "No tasks. Add a magnet to create one."],
    [
      "an unreachable fake",
      { listTasks: async () => Promise.reject(new Error("Failed to fetch")) },
      "Can't reach the fake: Failed to fetch",
    ],
  ])("explains %s", async (_label, overrides, text) => {
    const { panel } = await openPanel(fakeSimulator(overrides));
    expect(await within(panel).findByText(text)).toBeInTheDocument();
  });

  describe("fake feeds", () => {
    const FEEDS: FakeFeed[] = [
      { slug: "tv", title: "Fake Tracker · TV", path: "/feeds/tv.xml", mode: "ok", items: [] },
      {
        slug: "anime",
        title: "Fake Tracker · Anime",
        path: "/feeds/anime.xml",
        mode: "http_error",
        items: [],
      },
    ];
    const subscribed = () =>
      createFakeClient({
        listFeeds: async () => [makeFeed({ id: "a" }), makeFeed({ id: "b" })],
        refreshFeed: async (id) => makeFeed({ id }),
      });
    const feedRow = async (panel: HTMLElement, title: string) => {
      const section = await within(panel).findByRole("region", { name: "Fake feeds" });
      return within(section).getByText(title).closest("li") as HTMLElement;
    };

    it.each<[string, string, keyof SimulatorClient, unknown[], string]>([
      ["Fake Tracker · TV", "Publish", "publish", ["tv"], "Published to Fake Tracker · TV"],
      [
        "Fake Tracker · TV",
        "Fail (503)",
        "breakFeed",
        ["tv", "http_error"],
        "Fake Tracker · TV now fails",
      ],
      [
        "Fake Tracker · TV",
        "Not RSS",
        "breakFeed",
        ["tv", "bad_xml"],
        "Fake Tracker · TV now serves HTML",
      ],
      ["Fake Tracker · Anime", "Heal", "healFeed", ["anime"], "Fake Tracker · Anime healed"],
    ])("%s: %s, then Charon refreshes its feeds", async (title, button, method, args, message) => {
      const simulator = fakeSimulator({ listFeeds: vi.fn(async () => FEEDS) });
      const client = subscribed();
      const { panel } = await openPanel(simulator, client);
      await userEvent.click(
        within(await feedRow(panel, title)).getByRole("button", { name: button }),
      );
      expect(await findToast(message)).toHaveTextContent("Charon refreshed 2 feed(s)");
      expect(simulator[method]).toHaveBeenCalledWith(...args);
      expect(client.refreshFeed).toHaveBeenCalledTimes(2);
    });

    it("explains an action the fake refused", async () => {
      const simulator = fakeSimulator({
        listFeeds: vi.fn(async () => FEEDS),
        publish: async () => Promise.reject(new Error("Fake answered 404")),
      });
      const { panel } = await openPanel(simulator, subscribed());
      await userEvent.click(
        within(await feedRow(panel, "Fake Tracker · TV")).getByRole("button", { name: "Publish" }),
      );
      expect(await findToast("Simulator action failed")).toHaveTextContent("Fake answered 404");
    });

    it("stays out of the way when the fake has no feeds", async () => {
      const { panel } = await openPanel(fakeSimulator());
      await within(panel).findByText("Show.S01E01.mkv");
      expect(within(panel).queryByRole("region", { name: "Fake feeds" })).not.toBeInTheDocument();
    });
  });

  it("talks to the fake through the dev server by default", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    try {
      const { panel } = await openPanel();
      expect(await within(panel).findByText(/No tasks/)).toBeInTheDocument();
      expect(fetch).toHaveBeenCalledWith("/_fake/_control/tasks", undefined);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
