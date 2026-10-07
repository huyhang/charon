import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@/api/errors";
import type { Rule, RuleSpec, RuleUpdate } from "@/api/types";
import { Toaster } from "@/components/ui/sonner";
import { createFakeClient } from "@/test/fakeClient";
import { makeRule } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { RulesPage } from "./RulesPage";
import { stepSummary } from "./RuleRow";

/** A fake rule store: saving changes what the next listing returns, ordered like Charon's. */
function ruleStore(rules: Rule[], { failReorder = false, failUpdate = false } = {}) {
  let stored = rules.map((rule) => ({ ...rule }));
  const sorted = () => [...stored].sort((a, b) => a.priority - b.priority);
  return createFakeClient({
    listRules: async () => sorted(),
    updateRule: async (id: string, spec: RuleSpec) => {
      if (failUpdate) throw new ApiError(500, { code: "internal_error", message: "disk full" });
      const saved = { ...stored.find((rule) => rule.id === id)!, ...spec };
      stored = stored.map((rule) => (rule.id === id ? saved : rule));
      return saved;
    },
    reorderRules: async (ids: string[]) => {
      if (failReorder) throw new ApiError(500, { code: "internal_error", message: "disk full" });
      stored = stored.map((rule) => ({ ...rule, priority: (ids.indexOf(rule.id) + 1) * 10 }));
      return sorted();
    },
  });
}

/** jsdom lays nothing out; stack the rule rows 80px apart so drag and drop can find them. */
function layOutRows() {
  const original = Element.prototype.getBoundingClientRect;
  return vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (
    this: Element,
  ) {
    const list = this.parentElement;
    if (this.tagName !== "LI" || !list?.matches("ol")) return original.call(this);
    const top = [...list.children].indexOf(this) * 80;
    return {
      x: 0,
      y: top,
      top,
      left: 0,
      width: 600,
      height: 70,
      right: 600,
      bottom: top + 70,
      toJSON: () => ({}),
    };
  });
}

const rowNames = () =>
  within(screen.getByRole("list", { name: /priority order/ }))
    .getAllByRole("button", { name: /^Reorder / })
    .map((grip) => grip.getAttribute("aria-label")?.replace("Reorder ", ""));

const THREE = [
  makeRule({ id: "a", name: "TV", priority: 10 }),
  makeRule({ id: "b", name: "Movies", priority: 20 }),
  makeRule({ id: "c", name: "Anime", priority: 30 }),
];

describe("stepSummary", () => {
  it.each([
    [[], "Keeps the name"],
    [[{ op: "replace" as const, find: "a", replace: "" }], "1 rename step"],
    [Array(3).fill({ op: "replace" as const, find: "a", replace: "" }), "3 rename steps"],
    [undefined, "Keeps the name"],
  ])("%j -> %s", (steps, expected) => {
    expect(stepSummary({ steps })).toBe(expected);
  });
});

describe("RulesPage", () => {
  it("lists rules in priority order", async () => {
    const client = createFakeClient({
      listRules: async () => [
        makeRule({ id: "a", name: "TV" }),
        makeRule({ id: "b", name: "Movies", priority: 20 }),
      ],
    });
    await renderWithApp(<RulesPage />, { client });
    const list = await screen.findByRole("list", { name: /priority order/ });
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual([expect.stringContaining("TV"), expect.stringContaining("Movies")]);
  });

  it.each<[string, boolean, boolean, boolean, string]>([
    ["turns off an enabled rule", true, false, false, "TV disabled"],
    ["turns on a disabled rule", false, false, true, "TV enabled"],
    ["reports a failed save", true, true, false, "Couldn't update the rule"],
  ])("%s", async (_label, enabled, failUpdate, saved, toastText) => {
    const client = ruleStore([makeRule({ id: "a", name: "TV", enabled })], { failUpdate });
    await renderWithApp(
      <>
        <RulesPage />
        <Toaster />
      </>,
      { client },
    );
    await userEvent.click(await screen.findByRole("switch", { name: "Enable TV" }));
    expect(await screen.findByText(toastText)).toBeInTheDocument();
    expect(client.updateRule).toHaveBeenCalledWith(
      "a",
      expect.objectContaining({ enabled: saved, version: 1 }),
    );
  });

  it("labels regex rules and summarizes each rule's steps", async () => {
    const step = { op: "regex_replace" as const, find: "x", replace: "" };
    const client = createFakeClient({
      listRules: async () => [makeRule({ match_type: "regex", pattern: "S\\d+", steps: [step] })],
    });
    await renderWithApp(<RulesPage />, { client });
    const row = await screen.findByRole("button", { name: /^TV/ });
    expect(within(row).getByText("regex")).toBeInTheDocument();
    expect(within(row).getByText("1 rename step")).toBeInTheDocument();
  });

  it("reorders by keyboard drag, saving the new order in one request", async () => {
    const layout = layOutRows();
    const client = ruleStore(THREE);
    await renderWithApp(<RulesPage />, { client });
    (await screen.findByRole("button", { name: "Reorder TV" })).focus();
    await userEvent.keyboard(" ");
    await userEvent.keyboard("{ArrowDown}");
    await userEvent.keyboard(" ");
    await waitFor(() => expect(rowNames()).toEqual(["Movies", "TV", "Anime"]));
    await waitFor(() => expect(client.reorderRules).toHaveBeenCalledWith(["b", "a", "c"]));
    expect(client.updateRule).not.toHaveBeenCalled();
    layout.mockRestore();
  });

  it("saves nothing when a rule is dropped where it was", async () => {
    const layout = layOutRows();
    const client = ruleStore(THREE);
    await renderWithApp(<RulesPage />, { client });
    (await screen.findByRole("button", { name: "Reorder TV" })).focus();
    await userEvent.keyboard(" ");
    await userEvent.keyboard(" ");
    expect(rowNames()).toEqual(["TV", "Movies", "Anime"]);
    expect(client.reorderRules).not.toHaveBeenCalled();
    layout.mockRestore();
  });

  it("puts the old order back and says so when saving a new order fails", async () => {
    const layout = layOutRows();
    const client = ruleStore(THREE, { failReorder: true });
    await renderWithApp(
      <>
        <RulesPage />
        <Toaster />
      </>,
      { client },
    );
    (await screen.findByRole("button", { name: "Reorder TV" })).focus();
    await userEvent.keyboard(" ");
    await userEvent.keyboard("{ArrowDown}");
    await userEvent.keyboard(" ");
    const toast = (await screen.findByText("Couldn't save the new order")).closest("li");
    expect(within(toast as HTMLElement).getByText("disk full")).toBeInTheDocument();
    // Back to what Charon has: the save failed, so TV still sorts first.
    await waitFor(() => expect(client.listRules).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(rowNames()).toEqual(["TV", "Movies", "Anime"]));
    layout.mockRestore();
  });

  it("offers to retry when the rules can't be loaded", async () => {
    const client = createFakeClient({
      listRules: vi
        .fn<() => Promise<Rule[]>>()
        .mockRejectedValueOnce(
          new ApiError(503, { code: "http_error", message: "Charon is restarting" }),
        )
        .mockResolvedValue([makeRule({ name: "TV" })]),
    });
    await renderWithApp(<RulesPage />, { client });
    expect(await screen.findByRole("alert")).toHaveTextContent("Charon is restarting");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("button", { name: "Reorder TV" })).toBeInTheDocument();
  });

  it.each<[string, (user: typeof userEvent) => Promise<unknown>]>([
    ["Cancel", (user) => user.click(screen.getByRole("button", { name: "Cancel" }))],
    ["Escape", (user) => user.keyboard("{Escape}")],
  ])("opens a rule for editing and closes it with %s", async (_label, close) => {
    const client = createFakeClient({ listRules: async () => [makeRule({ name: "TV" })] });
    await renderWithApp(<RulesPage />, { client });
    await userEvent.click(await screen.findByRole("button", { name: /^TV/ }));
    const dialog = await screen.findByRole("dialog", { name: "Edit rule" });
    expect(within(dialog).getByLabelText("Name")).toHaveValue("TV");
    await close(userEvent);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("invites creating the first rule", async () => {
    await renderWithApp(<RulesPage />);
    await userEvent.click(await screen.findByRole("button", { name: /create your first rule/i }));
    expect(await screen.findByRole("dialog", { name: "New rule" })).toBeInTheDocument();
    expect(screen.getByLabelText("Destination")).toHaveValue("/library/");
  });

  it("opens the editor from ?new", async () => {
    await renderWithApp(<RulesPage />, { route: "/rules?new=1" });
    expect(await screen.findByRole("dialog", { name: "New rule" })).toBeInTheDocument();
  });

  it("starts a rule from a download name, e.g. a feed item's", async () => {
    const name = "Some.Documentary.Special.1080p.mkv";
    const { router } = await renderWithApp(<RulesPage />, {
      route: `/rules?new=1&sample=${encodeURIComponent(name)}`,
    });
    expect(await screen.findByRole("dialog", { name: "New rule" })).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("Some Documentary Special");
    expect(screen.getByLabelText("Pattern")).toHaveValue("Some.Documentary.Special.*");
    expect(screen.getByLabelText("Sample name")).toHaveValue(name);
    expect(screen.getByLabelText("Destination")).toHaveValue("/library/");
    expect(router.state.location.search).toBe("");
  });

  it("saves after a conflict once the rule is opened again", async () => {
    let stored: Rule = makeRule({ id: "a", name: "TV", version: 1 });
    const client = createFakeClient({
      listRules: async () => [stored],
      updateRule: async (_id: string, spec: RuleUpdate) => {
        if (spec.version != null && spec.version !== stored.version) {
          throw new ApiError(409, {
            code: "rule_changed",
            message: "rule a changed since you loaded it; reload it",
          });
        }
        stored = { ...stored, ...spec, version: stored.version + 1 };
        return stored;
      },
    });
    await renderWithApp(<RulesPage />, { client, route: "/rules", path: "/rules" });
    const open = async () =>
      userEvent.click(await screen.findByRole("button", { name: /^TVglob/ }));

    await open();
    stored = { ...stored, pattern: "*changed*", version: 2 }; // someone else saves meanwhile
    await userEvent.click(screen.getByRole("button", { name: "Save rule" }));
    await screen.findByText(/changed since you loaded it/);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    // As the hint says: load it again, then save.
    await open();
    await userEvent.click(screen.getByRole("button", { name: "Save rule" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(client.updateRule.mock.calls.map(([, spec]) => spec.version)).toEqual([1, 2]);
    expect(stored.version).toBe(3);
  });
});
