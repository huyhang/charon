import type { Rule, RuleSpec, RuleUpdate } from "@/api/types";

export const PRIORITY_STEP = 10;

export function moveItem<T>(items: readonly T[], from: number, to: number): T[] {
  const next = [...items];
  const [moved] = next.splice(from, 1);
  if (moved === undefined) return next;
  next.splice(to, 0, moved);
  return next;
}

export function nextPriority(rules: readonly Rule[]): number {
  return rules.reduce((max, rule) => Math.max(max, rule.priority), 0) + PRIORITY_STEP;
}

export function toSpec(rule: Rule): RuleSpec {
  const { name, description, priority, enabled, match_type, pattern, steps, destination } = rule;
  return {
    name,
    description: description ?? "",
    priority,
    enabled,
    match_type,
    pattern,
    steps: steps ?? [],
    destination,
  };
}

/** The rule as an update that fails, rather than overwrites, if someone changed it meanwhile. */
export function toUpdate(rule: Rule, patch: Partial<RuleSpec> = {}): RuleUpdate {
  return { ...toSpec(rule), ...patch, version: rule.version };
}

export function emptySpec(priority: number, destination = ""): RuleSpec {
  return {
    name: "",
    description: "",
    priority,
    enabled: true,
    match_type: "glob",
    pattern: "",
    steps: [],
    destination,
  };
}

/** Whether a draft has enough filled in to preview on the server. */
export function isPreviewable(spec: RuleSpec): boolean {
  return Boolean(
    spec.pattern && spec.destination.startsWith("/") && spec.steps?.every((s) => s.find),
  );
}
