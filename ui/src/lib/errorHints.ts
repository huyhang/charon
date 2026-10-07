import type { JobError } from "@/api/types";

/** What the user can do about a failure, in plain language. Charon supplies the advice. */
export function errorHint(error: Pick<JobError, "hint"> | null | undefined): string | null {
  return error?.hint ?? null;
}
