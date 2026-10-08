import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@/api/errors";
import { Toaster } from "@/components/ui/sonner";
import { emptySpec } from "@/lib/rules";
import { createFakeClient } from "@/test/fakeClient";
import { makeJob, makeRule, makeTitle, TMDB } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { RuleEditor, type EditorTarget } from "./RuleEditor";

const CREATE: EditorTarget = { mode: "create", spec: emptySpec(10, "/library/") };

async function fillBasics() {
  await userEvent.type(screen.getByLabelText("Name"), "TV");
  await userEvent.type(screen.getByLabelText("Pattern"), "*S0?E*");
  const destination = screen.getByLabelText("Destination");
  await userEvent.clear(destination);
  await userEvent.type(destination, "/library/tv");
}

describe("RuleEditor", () => {
  it("creates a rule with rename steps", async () => {
    const client = createFakeClient({
      createRule: async (spec) => makeRule({ ...spec, id: "new" }),
    });
    const onClose = vi.fn();
    await renderWithApp(<RuleEditor target={CREATE} onClose={onClose} />, { client });
    await fillBasics();
    await userEvent.click(screen.getByRole("button", { name: /add step/i }));
    await userEvent.type(screen.getByLabelText("Step 1 find"), "XYZ");
    await userEvent.type(screen.getByLabelText("Step 1 replace"), "ABC");
    await userEvent.click(screen.getByRole("button", { name: "Create rule" }));
    await waitFor(() =>
      expect(client.createRule).toHaveBeenCalledWith({
        name: "TV",
        description: "",
        priority: 10,
        enabled: true,
        match_type: "glob",
        pattern: "*S0?E*",
        steps: [{ op: "replace", find: "XYZ", replace: "ABC" }],
        destination: "/library/tv",
      }),
    );
    expect(onClose).toHaveBeenCalled();
  });

  it("keeps save disabled until the draft is complete", async () => {
    await renderWithApp(<RuleEditor target={CREATE} onClose={() => {}} />);
    expect(screen.getByRole("button", { name: "Create rule" })).toBeDisabled();
    await fillBasics();
    expect(screen.getByRole("button", { name: "Create rule" })).toBeEnabled();
  });

  it.each([
    [
      new ApiError(422, {
        code: "invalid_request",
        message: "m",
        details: [{ loc: ["body", "pattern"], msg: "Value error, invalid regex" }],
      }),
      "Pattern",
      "Invalid regex",
    ],
    [
      new ApiError(422, { code: "destination_not_allowed", message: "/etc is outside the roots" }),
      "Destination",
      "/etc is outside the roots",
    ],
  ])("shows server errors next to the field (%#)", async (error, field, message) => {
    const client = createFakeClient({ createRule: async () => Promise.reject(error) });
    await renderWithApp(<RuleEditor target={CREATE} onClose={() => {}} />, { client });
    await fillBasics();
    await userEvent.click(screen.getByRole("button", { name: "Create rule" }));
    const alert = await screen.findByText(message);
    expect(alert).toHaveAttribute("id", `rule-${field.toLowerCase()}-error`);
    expect(screen.getByLabelText(field)).toHaveAccessibleDescription(message);
  });

  it.each<[string, string, (user: typeof userEvent) => Promise<void>]>([
    ["Pattern", "Invalid regex", (user) => user.type(screen.getByLabelText("Pattern"), "x")],
    ["Name", "Name taken", (user) => user.type(screen.getByLabelText("Name"), "x")],
    [
      "Pattern",
      "Invalid regex",
      (user) => user.click(screen.getByRole("radio", { name: "Regex" })),
    ],
  ])("clears the %s error once it is edited, keeping the others", async (field, message, edit) => {
    const error = new ApiError(422, {
      code: "invalid_request",
      message: "request validation failed",
      details: [
        { loc: ["body", "pattern"], msg: "Value error, invalid regex" },
        { loc: ["body", "name"], msg: "Name taken" },
        { loc: ["body"], msg: "Something about the whole rule" },
      ],
    });
    const client = createFakeClient({ createRule: async () => Promise.reject(error) });
    await renderWithApp(<RuleEditor target={CREATE} onClose={() => {}} />, { client });
    await fillBasics();
    await userEvent.click(screen.getByRole("button", { name: "Create rule" }));
    expect(await screen.findByText(message)).toBeInTheDocument();
    await edit(userEvent);
    expect(screen.queryByText(message)).not.toBeInTheDocument();
    expect(screen.queryByText("Something about the whole rule")).not.toBeInTheDocument();
    const other = field === "Name" ? "Invalid regex" : "Name taken";
    expect(screen.getByText(other)).toBeInTheDocument();
  });

  it.each<[string, unknown, string]>([
    ["a network failure", new TypeError("Failed to fetch"), "Failed to fetch"],
    [
      "an error about the whole rule",
      new ApiError(422, { code: "unsafe_name", message: "the new name would contain /" }),
      "the new name would contain /",
    ],
  ])("shows %s below the form", async (_label, error, message) => {
    const client = createFakeClient({ createRule: async () => Promise.reject(error) });
    const onClose = vi.fn();
    await renderWithApp(<RuleEditor target={CREATE} onClose={onClose} />, { client });
    await fillBasics();
    await userEvent.click(screen.getByRole("button", { name: "Create rule" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("creates a rule switched off", async () => {
    const client = createFakeClient({ createRule: async (spec) => makeRule({ ...spec }) });
    await renderWithApp(<RuleEditor target={CREATE} onClose={() => {}} />, { client });
    await fillBasics();
    await userEvent.click(screen.getByRole("switch", { name: "Enabled" }));
    await userEvent.click(screen.getByRole("button", { name: "Create rule" }));
    await waitFor(() =>
      expect(client.createRule).toHaveBeenCalledWith(expect.objectContaining({ enabled: false })),
    );
  });

  it("says why a delete failed and stays open", async () => {
    const client = createFakeClient({
      deleteRule: async () =>
        Promise.reject(new ApiError(404, { code: "rule_not_found", message: "rule r1 is gone" })),
    });
    const onClose = vi.fn();
    await renderWithApp(
      <>
        <RuleEditor target={{ mode: "edit", rule: makeRule({ id: "r1" }) }} onClose={onClose} />
        <Toaster />
      </>,
      { client },
    );
    await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete rule" }));
    expect(await screen.findByText("Couldn't delete the rule")).toBeInTheDocument();
    expect(screen.getByText("rule r1 is gone")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("edits an existing rule in place", async () => {
    const rule = makeRule({ id: "r1", name: "Old" });
    const client = createFakeClient({
      updateRule: async (_, spec) => ({ ...rule, ...spec, version: rule.version + 1 }),
    });
    await renderWithApp(<RuleEditor target={{ mode: "edit", rule }} onClose={() => {}} />, {
      client,
    });
    const name = screen.getByLabelText("Name");
    await userEvent.clear(name);
    await userEvent.type(name, "New");
    await userEvent.click(screen.getByRole("button", { name: "Save rule" }));
    await waitFor(() =>
      expect(client.updateRule).toHaveBeenCalledWith(
        "r1",
        expect.objectContaining({ name: "New", version: 1 }),
      ),
    );
  });

  it("says what to do when someone else changed the rule meanwhile", async () => {
    const rule = makeRule({ id: "r1", name: "Old", version: 3 });
    const client = createFakeClient({
      updateRule: async () => {
        throw new ApiError(409, {
          code: "rule_changed",
          message: "rule r1 changed since you loaded it",
          hint: "Load the rule again.",
        });
      },
    });
    const onClose = vi.fn();
    await renderWithApp(<RuleEditor target={{ mode: "edit", rule }} onClose={onClose} />, {
      client,
    });
    await userEvent.click(screen.getByRole("button", { name: "Save rule" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "rule r1 changed since you loaded it Load the rule again.",
    );
    expect(onClose).not.toHaveBeenCalled();
  });

  it("saves a description of why the rule exists", async () => {
    const client = createFakeClient({
      createRule: async (spec) => makeRule({ ...spec, id: "new" }),
    });
    await renderWithApp(<RuleEditor target={CREATE} onClose={() => {}} />, { client });
    await fillBasics();
    await userEvent.type(screen.getByLabelText("Description"), "Keeps TV tidy");
    await userEvent.click(screen.getByRole("button", { name: "Create rule" }));
    await waitFor(() =>
      expect(client.createRule).toHaveBeenCalledWith(
        expect.objectContaining({ description: "Keeps TV tidy" }),
      ),
    );
  });

  it("deletes after confirming", async () => {
    const client = createFakeClient();
    await renderWithApp(
      <RuleEditor target={{ mode: "edit", rule: makeRule({ id: "r1" }) }} onClose={() => {}} />,
      { client },
    );
    await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete rule" }));
    await waitFor(() => expect(client.deleteRule).toHaveBeenCalledWith("r1"));
  });

  it("previews the unsaved draft on the server", async () => {
    const client = createFakeClient({
      previewRule: async ({ name }) => ({
        rule_id: null,
        new_name: name.replace("XYZ", "ABC"),
        final_path: `/library/tv/${name.replace("XYZ", "ABC")}`,
      }),
    });
    await renderWithApp(<RuleEditor target={CREATE} onClose={() => {}} />, { client });
    await fillBasics();
    await userEvent.type(screen.getByLabelText("Sample name"), "Show.XYZ.mkv");
    expect(await screen.findByText("Matches")).toBeInTheDocument();
    expect(client.previewRule).toHaveBeenLastCalledWith({
      name: "Show.XYZ.mkv",
      rule: expect.objectContaining({ pattern: "*S0?E*", destination: "/library/tv" }),
    });
  });

  it("renames a feed release's title to the official one picked from TMDB", async () => {
    const sample = "Kusuriya no Hitorigoto - 24 (1080p).mkv";
    const client = createFakeClient({
      metadataProviders: async () => [TMDB],
      searchTitles: async () => ({
        attribution: TMDB,
        results: [makeTitle()],
        stale: false,
        age_seconds: 0,
      }),
    });
    const target: EditorTarget = {
      mode: "create",
      spec: { ...CREATE.spec, name: "Kusuriya no Hitorigoto", pattern: "Kusuriya no Hitorigoto*" },
      sample,
    };
    await renderWithApp(<RuleEditor target={target} onClose={() => {}} />, { client });
    await userEvent.click(await screen.findByRole("button", { name: "Look up official title" }));
    const dialog = await screen.findByRole("dialog", { name: "Look up the official title" });
    await userEvent.click(
      await within(dialog).findByRole("button", { name: "Use The Apothecary Diaries" }),
    );
    expect(screen.getByLabelText("Name")).toHaveValue("The Apothecary Diaries");
    expect(screen.getByLabelText("Step 1 find")).toHaveValue("Kusuriya no Hitorigoto");
    expect(screen.getByLabelText("Step 1 replace")).toHaveValue("The Apothecary Diaries");
    expect(screen.getByLabelText("Sample name")).toHaveValue(sample);
  });

  it.each<[string, EditorTarget, string, string | null]>([
    ["from scratch, even with recent downloads", CREATE, "", null],
    [
      "from a feed item",
      { ...CREATE, sample: "Kusuriya.no.Hitorigoto.S02E12.mkv" },
      "Kusuriya no Hitorigoto",
      "Kusuriya.no.Hitorigoto",
    ],
  ])("starts the title lookup %s", async (_label, target, query, replaces) => {
    const client = createFakeClient({
      listDownloads: async () => ({
        items: [makeJob({ name: "Severance.S02E04.1080p.WEB-DL.mkv" })],
        next_cursor: null,
      }),
      metadataProviders: async () => [TMDB],
      searchTitles: async () => ({
        attribution: TMDB,
        results: [makeTitle()],
        stale: false,
        age_seconds: 0,
      }),
    });
    await renderWithApp(<RuleEditor target={target} onClose={() => {}} />, { client });
    // The test bench still tries the newest download when nothing is typed.
    await waitFor(() =>
      expect(screen.getByLabelText("Sample name")).toHaveAttribute(
        "placeholder",
        "Severance.S02E04.1080p.WEB-DL.mkv",
      ),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Look up official title" }));
    const dialog = await screen.findByRole("dialog", { name: "Look up the official title" });
    expect(within(dialog).getByLabelText("Title to look up")).toHaveValue(query);
    if (replaces) {
      expect(within(dialog).getByText(replaces)).toBeInTheDocument();
    } else {
      expect(within(dialog).queryByText(/Replaces/)).not.toBeInTheDocument();
      expect(within(dialog).getByText("Type a title to look it up.")).toBeInTheDocument();
    }
  });

  it("offers no title lookup when no provider is set up", async () => {
    const client = createFakeClient();
    await renderWithApp(<RuleEditor target={CREATE} onClose={() => {}} />, { client });
    await waitFor(() => expect(client.metadataProviders).toHaveBeenCalled());
    expect(
      screen.queryByRole("button", { name: "Look up official title" }),
    ).not.toBeInTheDocument();
  });
});
