import type { RenameStep, RuleSpec } from "@/api/types";
import { moveItem } from "./rules";

/** Immutable edits to a rule draft's rename steps. */
export function addStep(spec: RuleSpec): RuleSpec {
  return { ...spec, steps: [...(spec.steps ?? []), { op: "replace", find: "", replace: "" }] };
}

export function updateStep(spec: RuleSpec, index: number, patch: Partial<RenameStep>): RuleSpec {
  return {
    ...spec,
    steps: (spec.steps ?? []).map((step, i) => (i === index ? { ...step, ...patch } : step)),
  };
}

export function removeStep(spec: RuleSpec, index: number): RuleSpec {
  return { ...spec, steps: (spec.steps ?? []).filter((_, i) => i !== index) };
}

export function moveStep(spec: RuleSpec, from: number, to: number): RuleSpec {
  const steps = spec.steps ?? [];
  if (to < 0 || to >= steps.length) return spec;
  return { ...spec, steps: moveItem(steps, from, to) };
}

/** Error codes that belong to one form field rather than the whole form. */
const CODE_FIELDS: Record<string, string> = {
  destination_not_allowed: "destination",
  rule_timeout: "pattern",
};

export function fieldForCode(code: string): string | null {
  return CODE_FIELDS[code] ?? null;
}

/** Fields whose error may no longer apply once another field changes. */
const AFFECTS: Record<string, string[]> = { match_type: ["pattern"] };

/**
 * Drops server errors made stale by editing `changed`: errors on those fields (and their
 * children, e.g. steps.0.find) and the form-level error. Other fields keep theirs.
 */
export function clearStaleErrors(
  errors: Record<string, string>,
  changed: readonly string[],
): Record<string, string> {
  const fields = changed.flatMap((field) => [field, ...(AFFECTS[field] ?? [])]);
  const stale = (key: string) =>
    key === "_" || fields.some((field) => key === field || key.startsWith(`${field}.`));
  return Object.fromEntries(Object.entries(errors).filter(([key]) => !stale(key)));
}

export function draftProblems(spec: RuleSpec): string[] {
  const problems: string[] = [];
  if (!spec.name.trim()) problems.push("Give the rule a name.");
  if (!spec.pattern.trim()) problems.push("Add a pattern to match download names.");
  if (!spec.destination.startsWith("/")) problems.push("Choose a destination folder.");
  if (spec.steps?.some((step) => !step.find))
    problems.push("Every rename step needs something to find.");
  return problems;
}
