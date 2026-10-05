import type { ErrorDetail } from "@/api/types";

type Details = ErrorDetail["details"];

/**
 * Maps FastAPI validation details to form fields, e.g. `body.steps.0.find` -> "steps.0.find".
 * The first message per field wins.
 */
export function fieldErrors(details: Details): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const detail of details ?? []) {
    const loc = Array.isArray(detail.loc) ? detail.loc : [];
    const field = loc.filter((part, i) => !(i === 0 && part === "body")).join(".");
    const message = typeof detail.msg === "string" ? cleanMessage(detail.msg) : "Invalid value";
    errors[field || "_"] ??= message;
  }
  return errors;
}

/** The first readable validation message, e.g. for a toast with no form field to sit next to. */
export function firstFieldMessage(details: Details): string | null {
  const detail = details?.find((d) => typeof d.msg === "string");
  return detail ? cleanMessage(detail.msg as string) : null;
}

function cleanMessage(message: string): string {
  const text = message.replace(/^Value error, /, "");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
