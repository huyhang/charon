import { screen } from "@testing-library/react";
import { ApiError } from "@/api/errors";
import type { CharonClient } from "@/api/client";
import { createFakeClient } from "@/test/fakeClient";
import { makeRule } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { MatchPreview } from "./MatchPreview";

const NAME = "Show.S01E01.1080p.mkv";
const tv = makeRule({ id: "tv", name: "TV" });

function preview(
  rule_id: string | null,
  new_name: string,
  final_path: string | null,
): Partial<CharonClient> {
  return {
    previewRule: async () => ({ rule_id, new_name, final_path }),
    listRules: async () => [tv],
  };
}

/** Matches the innermost element whose text, across its children, is exactly `text`. */
const wholeText = (text: string) => (_: string, el: Element | null) =>
  el?.textContent === text && ![...el.children].some((child) => child.textContent === text);

describe("MatchPreview", () => {
  it.each<[string, Partial<CharonClient>, string[]]>([
    [
      "the matching rule and its folder",
      preview("tv", "Show.S01E01.mkv", "/library/tv/Show.S01E01.mkv"),
      ["Matches rule TV", "/library/tv"],
    ],
    [
      "a dash for a rule it can't name",
      preview("deleted", "Show.S01E01.mkv", "/library/tv/Show.S01E01.mkv"),
      ["Matches rule —", "/library/tv"],
    ],
    ["the root folder", preview("tv", "Show.mkv", "/Show.mkv"), ["Matches rule TV", "/"]],
    [
      "that the download stays put when no rule matches",
      preview(null, NAME, null),
      [`No rule matches ${NAME}. It will stay in the download folder.`],
    ],
    [
      "why the rules couldn't be checked",
      {
        previewRule: async () =>
          Promise.reject(
            new ApiError(422, { code: "rule_timeout", message: "regex took too long" }),
          ),
      },
      ["regex took too long"],
    ],
  ])("shows %s", async (_label, overrides, texts) => {
    const client = createFakeClient(overrides);
    await renderWithApp(<MatchPreview name={NAME} ruleId={null} />, { client });
    for (const text of texts) {
      expect(await screen.findByText(wholeText(text))).toBeInTheDocument();
    }
  });

  it.each<[string | null]>([[null], ["tv"]])(
    "asks Charon with the chosen rule (%s)",
    async (ruleId) => {
      const client = createFakeClient(preview("tv", "Show.mkv", "/library/tv/Show.mkv"));
      await renderWithApp(<MatchPreview name={NAME} ruleId={ruleId} />, { client });
      await screen.findByText(/Matches rule/);
      expect(client.previewRule).toHaveBeenLastCalledWith({ name: NAME, rule_id: ruleId });
    },
  );

  it("checks while waiting for Charon", async () => {
    const client = createFakeClient({ previewRule: () => new Promise(() => {}) });
    await renderWithApp(<MatchPreview name={NAME} ruleId={null} />, { client });
    expect(screen.getByText("Checking your rules…")).toBeInTheDocument();
  });

  it("explains a magnet without a name, without asking Charon", async () => {
    const client = createFakeClient();
    await renderWithApp(<MatchPreview name={null} ruleId={null} />, { client });
    expect(screen.getByText(/doesn.t include a name/)).toBeInTheDocument();
    expect(client.previewRule).not.toHaveBeenCalled();
  });
});
