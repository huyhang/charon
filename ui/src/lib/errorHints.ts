import type { components } from "@/api/schema";

type JobError = components["schemas"]["JobError"];

const HINTS: Record<string, string> = {
  destination_exists:
    "Something with the same name is already at the destination. Move or rename it, then retry.",
  destination_not_allowed:
    "The rule's destination is outside the folders Charon may write to. Edit the rule, then retry.",
  filesystem_error:
    "Charon couldn't read or write a folder. Check the folder permissions, then retry.",
  move_failed: "The file couldn't be moved. Check permissions and free space, then retry.",
  rule_timeout: "A rule's regex took too long on this name. Simplify the pattern, then retry.",
  unsafe_name:
    "A rule renamed this to an unsafe name (e.g. with a slash). Fix the rule's steps, then retry.",
  rule_not_found:
    "The rule picked for this download was deleted. Retry to match the current rules.",
  task_missing: "The task disappeared from Download Station. Retry to start a fresh download.",
  backend_error: "Download Station reported a problem. Check the link is still valid, then retry.",
  internal_error:
    "Something unexpected went wrong. Charon's log has the details; retrying may help.",
};

/** What the user can do about a failure, in plain language. */
export function errorHint(error: Pick<JobError, "code"> | null | undefined): string | null {
  if (!error) return null;
  return HINTS[error.code] ?? null;
}
