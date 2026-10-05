import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@/api/errors";
import type { Preview, PreviewRequest, RuleSpec } from "@/api/types";
import { emptySpec } from "@/lib/rules";
import { createFakeClient } from "@/test/fakeClient";
import { makeJob } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { TestBench } from "./TestBench";

const READY: RuleSpec = { ...emptySpec(10), name: "TV", pattern: "*S0?E*", destination: "/tv" };
const invalidRegex = new ApiError(422, {
  code: "invalid_request",
  message: "request validation failed",
  details: [{ loc: ["body", "rule", "pattern"], msg: "Value error, invalid regex '('" }],
});

describe("TestBench", () => {
  it.each<[string, RuleSpec, string]>([
    [
      "no pattern yet",
      { ...READY, pattern: "" },
      "Fill in a pattern and destination to try the rule.",
    ],
    [
      "a relative destination",
      { ...READY, destination: "tv" },
      "Fill in a pattern and destination to try the rule.",
    ],
    ["no sample name or downloads", READY, "Type a sample name to see what happens."],
  ])("asks for more with %s", async (_label, spec, prompt) => {
    const client = createFakeClient();
    await renderWithApp(<TestBench spec={spec} />, { client });
    expect(await screen.findByText(prompt)).toBeInTheDocument();
    expect(client.previewRule).not.toHaveBeenCalled();
  });

  it.each<[string, (request: PreviewRequest) => Promise<Preview>, string]>([
    [
      "a match, with the new name and destination",
      async ({ name }) => ({ rule_id: null, new_name: "Show.mkv", final_path: `/tv/${name}` }),
      "→ /tv/Show.S01E01.1080p.mkv",
    ],
    [
      "no match",
      async ({ name }) => ({ rule_id: null, new_name: name, final_path: null }),
      "The pattern doesn't match this name.",
    ],
    [
      "the server's specific complaint",
      async () => Promise.reject(invalidRegex),
      "Invalid regex '('",
    ],
  ])("shows %s", async (_label, previewRule, expected) => {
    const client = createFakeClient({ previewRule });
    await renderWithApp(<TestBench spec={READY} />, { client });
    await userEvent.type(screen.getByLabelText("Sample name"), "Show.S01E01.1080p.mkv");
    expect(await screen.findByText(expected)).toBeInTheDocument();
    expect(client.previewRule).toHaveBeenLastCalledWith({
      name: "Show.S01E01.1080p.mkv",
      rule: READY,
    });
  });

  it("offers recent download names as samples and tries the newest one", async () => {
    const client = createFakeClient({
      listDownloads: async () => ({
        items: [
          makeJob({ id: "1", name: "Newest.S01E02.mkv" }),
          makeJob({ id: "2", name: null }),
          makeJob({ id: "3", name: "Older.S01E01.mkv" }),
          makeJob({ id: "4", name: "Newest.S01E02.mkv" }),
        ],
        next_cursor: null,
      }),
    });
    const { container } = await renderWithApp(<TestBench spec={READY} />, { client });
    await waitFor(() =>
      expect(screen.getByLabelText("Sample name")).toHaveAttribute(
        "placeholder",
        "Newest.S01E02.mkv",
      ),
    );
    const options = [...container.querySelectorAll("datalist option")].map((o) =>
      o.getAttribute("value"),
    );
    expect(options).toEqual(["Newest.S01E02.mkv", "Older.S01E01.mkv"]);
    await waitFor(() =>
      expect(client.previewRule).toHaveBeenCalledWith({ name: "Newest.S01E02.mkv", rule: READY }),
    );
  });
});
