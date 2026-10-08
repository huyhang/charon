import type { RenameStep, RuleSpec } from "@/api/types";
import { makeTitle } from "@/test/factories";
import { titleInName } from "./feeds";
import { emptySpec } from "./rules";
import {
  queryFromName,
  safeTitle,
  separatorOf,
  styledTitle,
  titleFindText,
  titleStep,
  withTitle,
} from "./titles";

const APOTHECARY = makeTitle();
const FRIEREN = makeTitle({ title: "Frieren: Beyond Journey's End", year: 2023 });

describe("titleInName", () => {
  it.each([
    ["Kusuriya no Hitorigoto - 24 (1080p).mkv", "Kusuriya no Hitorigoto"],
    ["[SubsPlease] Kusuriya no Hitorigoto - 24 (1080p).mkv", "Kusuriya no Hitorigoto"],
    ["Kusuriya.no.Hitorigoto.S02E12.1080p.mkv", "Kusuriya.no.Hitorigoto"],
    ["Sousou_no_Frieren_-_13_[1080p].mkv", "Sousou_no_Frieren"],
    ["Severance.S02E04.1080p.WEB-DL.mkv", "Severance"],
    ["Dune.Part.Two.2024.2160p.mkv", "Dune.Part.Two"],
    ["", ""],
  ])("finds the title in %s", (name, expected) => {
    expect(titleInName(name)).toBe(expected);
  });
});

describe("queryFromName", () => {
  it.each([
    ["Kusuriya.no.Hitorigoto.S02E12.1080p.mkv", "Kusuriya no Hitorigoto"],
    ["[SubsPlease] Frieren - 13 (1080p).mkv", "Frieren"],
    ["", ""],
    ["   ", ""],
  ])("searches %s as %s", (name, expected) => {
    expect(queryFromName(name)).toBe(expected);
  });
});

describe("separatorOf", () => {
  it.each([
    ["Kusuriya.no.Hitorigoto.S02E12.mkv", "."],
    ["Kusuriya no Hitorigoto - 24.mkv", " "],
    ["[SubsPlease] Frieren - 13 (1080p).mkv", " "],
    ["[Group].Frieren.13.mkv", "."],
    ["Sousou_no_Frieren_13.mkv", "_"],
    ["Frieren", " "],
  ])("reads %s as %j", (name, expected) => {
    expect(separatorOf(name)).toBe(expected);
  });
});

describe("safeTitle", () => {
  it.each([
    ["The Apothecary Diaries", "The Apothecary Diaries"],
    ["Frieren: Beyond Journey's End", "Frieren - Beyond Journey's End"],
    ["Re:ZERO", "Re - ZERO"],
    ["Fate/Zero", "Fate-Zero"],
    ["AC\\DC", "AC-DC"],
    ['What If...? "Live" <Now> | *', "What If... Live Now"],
    ["  Spaced \t out  ", "Spaced out"],
    ["Ends with dots...", "Ends with dots"],
    ["Line\nbreak", "Line break"],
    ["Either | Or", "Either Or"],
  ])("makes %j safe", (title, expected) => {
    expect(safeTitle(title)).toBe(expected);
  });
});

describe("styledTitle", () => {
  it.each<[string, string, number | null, string]>([
    ["The Apothecary Diaries", ".", null, "The.Apothecary.Diaries"],
    ["The Apothecary Diaries", " ", null, "The Apothecary Diaries"],
    ["The Apothecary Diaries", "_", 2023, "The_Apothecary_Diaries_(2023)"],
    ["The Apothecary Diaries", " ", 2023, "The Apothecary Diaries (2023)"],
    ["Frieren: Beyond Journey's End", ".", null, "Frieren.Beyond.Journey's.End"],
    ["Frieren: Beyond Journey's End", " ", null, "Frieren - Beyond Journey's End"],
  ])("writes %j with %j and year %s", (title, separator, year, expected) => {
    expect(styledTitle(title, separator, year)).toBe(expected);
  });
});

describe("titleFindText", () => {
  it.each([
    ["Kusuriya.no.Hitorigoto.S02E12.mkv", "Kusuriya no Hitorigoto", "Kusuriya.no.Hitorigoto"],
    ["Kusuriya.no.Hitorigoto.S02E12.mkv", "kusuriya", "Kusuriya.no.Hitorigoto"],
    ["Kusuriya.no.Hitorigoto.S02E12.mkv", "", "Kusuriya.no.Hitorigoto"],
    ["[SubsPlease] Frieren - 13 (1080p).mkv", "Sousou no Frieren", "Frieren"],
    ["Severance.S02E04.1080p.mkv", " Sousou no Frieren ", "Sousou no Frieren"],
    ["", " Kusuriya no Hitorigoto ", "Kusuriya no Hitorigoto"],
    ["  ", "", ""],
  ])("finds the title in %j, or else uses %j", (name, query, expected) => {
    expect(titleFindText(name, query)).toBe(expected);
  });
});

describe("titleStep", () => {
  it.each<[string, string, string, boolean, RenameStep | null]>([
    [
      "a dotted release",
      "Kusuriya.no.Hitorigoto.S02E12.1080p.mkv",
      "Kusuriya no Hitorigoto",
      false,
      { op: "replace", find: "Kusuriya.no.Hitorigoto", replace: "The.Apothecary.Diaries" },
    ],
    [
      "a spaced release, with the year",
      "[SubsPlease] Kusuriya no Hitorigoto - 24 (1080p).mkv",
      "Kusuriya no Hitorigoto",
      true,
      {
        op: "replace",
        find: "Kusuriya no Hitorigoto",
        replace: "The Apothecary Diaries (2023)",
      },
    ],
    [
      "no sample name: what was searched for",
      "",
      "  Kusuriya no Hitorigoto ",
      false,
      { op: "replace", find: "Kusuriya no Hitorigoto", replace: "The Apothecary Diaries" },
    ],
    ["nothing to find", " ", " ", false, null],
  ])("builds a step for %s", (_label, name, query, includeYear, expected) => {
    expect(titleStep(name, query, APOTHECARY, includeYear)).toEqual(expected);
  });

  it.each<[string, string, string]>([
    ["already naming the year", "Face.Off.1997.1080p.BluRay.mkv", "Face-Off"],
    ["naming it in brackets", "Face Off (1997) 1080p.mkv", "Face-Off"],
    ["with the year only inside a longer number", "Face.Off.S01E19970.mkv", "Face-Off.(1997)"],
  ])("adds the year once, to a release %s", (_label, name, expected) => {
    const faceOff = makeTitle({ title: "Face/Off", year: 1997 });
    expect(titleStep(name, "Face Off", faceOff, true)?.replace).toBe(expected);
  });

  it("leaves the year out when the provider doesn't know it", () => {
    const step = titleStep("Show.S01E01.mkv", "", makeTitle({ title: "Show", year: null }), true);
    expect(step?.replace).toBe("Show");
  });

  it("ignores an unrelated sample name, styling the title like the search", () => {
    expect(titleStep("Severance.S02E04.1080p.mkv", "Kusuriya", APOTHECARY, false)).toEqual({
      op: "replace",
      find: "Kusuriya",
      replace: "The Apothecary Diaries",
    });
  });

  it("makes the title safe in a file name", () => {
    expect(titleStep("Sousou.no.Frieren.S01E13.mkv", "", FRIEREN, false)?.replace).toBe(
      "Frieren.Beyond.Journey's.End",
    );
  });
});

describe("withTitle", () => {
  const STEP: RenameStep = { op: "replace", find: "Kusuriya no Hitorigoto", replace: "A" };
  const OTHER: RenameStep = { op: "regex_replace", find: " \\(1080p\\)", replace: "" };
  const spec = (patch: Partial<RuleSpec>): RuleSpec => ({ ...emptySpec(10), ...patch });

  it.each<[string, Partial<RuleSpec>, string]>([
    ["no name", { name: "" }, "The Apothecary Diaries"],
    ["a blank name", { name: "  " }, "The Apothecary Diaries"],
    ["the guessed name", { name: "Kusuriya no Hitorigoto" }, "The Apothecary Diaries"],
    ["a name of its own", { name: "Anime I follow" }, "Anime I follow"],
  ])("names a rule with %s", (_label, patch, expected) => {
    const next = withTitle(spec(patch), STEP, "The Apothecary Diaries", "Kusuriya no Hitorigoto");
    expect(next.name).toBe(expected);
  });

  it.each<[string, RenameStep[], RenameStep[]]>([
    ["no steps", [], [STEP]],
    ["other steps, which run after it", [OTHER], [STEP, OTHER]],
    ["an earlier pick, which it replaces", [{ ...STEP, replace: "Old" }, OTHER], [STEP, OTHER]],
    [
      "a different first replace step, which stays",
      [{ op: "replace", find: "x", replace: "y" }],
      [STEP, { op: "replace", find: "x", replace: "y" }],
    ],
  ])("puts the step first, given %s", (_label, steps, expected) => {
    expect(withTitle(spec({ name: "n", steps }), STEP, "T", "").steps).toEqual(expected);
  });
});
