import type { Rule, RuleSpec } from "@/api/types";

export const PRIORITY_STEP = 10;

export function moveItem<T>(items: readonly T[], from: number, to: number): T[] {
  const next = [...items];
  const [moved] = next.splice(from, 1);
  if (moved === undefined) return next;
  next.splice(to, 0, moved);
  return next;
}

export interface PriorityChange {
  rule: Rule;
  priority: number;
}

/** Evenly spaced priorities for `ordered`, returning only the rules that change. */
export function priorityChanges(ordered: readonly Rule[]): PriorityChange[] {
  return ordered
    .map((rule, index) => ({ rule, priority: (index + 1) * PRIORITY_STEP }))
    .filter(({ rule, priority }) => rule.priority !== priority);
}

export function nextPriority(rules: readonly Rule[]): number {
  return rules.reduce((max, rule) => Math.max(max, rule.priority), 0) + PRIORITY_STEP;
}

export function toSpec(rule: Rule): RuleSpec {
  const { name, priority, enabled, match_type, pattern, steps, destination } = rule;
  return { name, priority, enabled, match_type, pattern, steps: steps ?? [], destination };
}

export function emptySpec(priority: number, destination = ""): RuleSpec {
  return {
    name: "",
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
