import type { RenameStep, RuleSpec, TitleMatch } from "@/api/types";
import { suggestRule, titleInName } from "./feeds";

/** What to search a provider for, guessed from a release name: "Kusuriya no Hitorigoto". */
export function queryFromName(name: string): string {
  return name.trim() ? suggestRule(name).name : "";
}

/** The separator between the words of a release name: ".", "_" or " " (the default). */
export function separatorOf(name: string): string {
  const rest = name.replace(/^\[[^\]]*\]\s*/, "");
  return /[._ ]/.exec(rest)?.[0] ?? " ";
}

/**
 * A title made safe in a file name on a NAS shared over SMB: no slashes (which would make a
 * folder), no characters Windows refuses, and no trailing dots or spaces, which it drops.
 */
export function safeTitle(title: string): string {
  return title
    .replace(/\s*:\s*/g, " - ")
    .replace(/[/\\]/g, "-")
    .replace(/[\u0000-\u001f]/g, " ")
    .replace(/[<>"|?*]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[. ]+$/, "");
}

/** The title written the way the release writes its own: "The.Apothecary.Diaries.(2023)". */
export function styledTitle(title: string, separator: string, year?: number | null): string {
  const words = safeTitle(title).split(" ");
  // A lone dash reads well between spaces, but not as "Frieren.-.Beyond".
  const kept = separator === " " ? words : words.filter((word) => word !== "-");
  const styled = kept.join(separator);
  return year ? `${styled}${separator}(${year})` : styled;
}

/** Whether `name` has `year` as a number of its own, not inside a longer one. */
function hasYear(name: string, year: number): boolean {
  return new RegExp(`(^|\\D)${year}(\\D|$)`).test(name);
}

/** Lower-case letters and digits, one space between words: "kusuriya no hitorigoto". */
function words(text: string): string {
  return text
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .filter(Boolean)
    .join(" ");
}

function findText(name: string, query: string): { text: string; fromName: boolean } {
  const inName = name.trim() ? titleInName(name) : "";
  const wanted = words(query);
  const named = words(inName);
  // The sample may be an unrelated recent download: only use it if it's what was searched for.
  const fromName =
    named !== "" && (wanted === "" || named.includes(wanted) || wanted.includes(named));
  return fromName ? { text: inName, fromName } : { text: query.trim(), fromName };
}

/**
 * What a title step replaces: the title as `name` spells it ("Kusuriya.no.Hitorigoto") if it is
 * what was searched for, or else the search itself.
 */
export function titleFindText(name: string, query: string): string {
  return findText(name, query).text;
}

/**
 * A step putting `match`'s canonical title in place of the release's own (see titleFindText).
 * Null if there's nothing to find.
 */
export function titleStep(
  name: string,
  query: string,
  match: TitleMatch,
  includeYear: boolean,
): RenameStep | null {
  const { text: find, fromName } = findText(name, query);
  if (!find) return null;
  const separator = fromName ? separatorOf(name) : " ";
  // A release that already names the year ("Face.Off.1997.1080p") shouldn't get it twice.
  const year = includeYear && match.year && !hasYear(name, match.year) ? match.year : null;
  return { op: "replace", find, replace: styledTitle(match.title, separator, year) };
}

/**
 * The draft with `step` first, since it is written against the original name. A step that
 * replaced the same text (an earlier pick) is swapped out rather than kept. The rule is named
 * after the title if it had no name, or only the one guessed from the release name.
 */
export function withTitle(
  spec: RuleSpec,
  step: RenameStep,
  title: string,
  guessedName: string,
): RuleSpec {
  const steps = spec.steps ?? [];
  const [first, ...rest] = steps;
  const earlierPick = first?.op === "replace" && first.find === step.find;
  const name = spec.name.trim();
  return {
    ...spec,
    name: !name || name === guessedName ? title : spec.name,
    steps: [step, ...(earlierPick ? rest : steps)],
  };
}
