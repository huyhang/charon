import { firstFieldMessage } from "@/lib/fieldErrors";
import type { ErrorDetail } from "./types";

/** What Charon says about a failure; everything but the code and message is optional. */
export type ErrorInit = Pick<ErrorDetail, "code" | "message"> & Partial<ErrorDetail>;

/** A failed API call, carrying Charon's stable error code. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetail["details"];
  /** What to do about it, in plain language, when Charon knows. */
  readonly hint: string | null;
  /** Whether sending the same request again later may succeed. */
  readonly retryable: boolean;

  constructor(status: number, detail: ErrorInit) {
    super(detail.message);
    this.name = "ApiError";
    this.status = status;
    this.code = detail.code;
    this.details = detail.details ?? null;
    this.hint = detail.hint ?? null;
    this.retryable = detail.retryable ?? false;
  }
}

export function isApiError(error: unknown, status?: number): error is ApiError {
  return error instanceof ApiError && (status === undefined || error.status === status);
}

/** A sentence for people. Prefers a specific validation problem over "request validation failed". */
export function errorMessage(error: unknown): string {
  if (isApiError(error)) return firstFieldMessage(error.details) ?? error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}

/** Charon's advice for an error, if it gave any. */
export function errorHintOf(error: unknown): string | null {
  return isApiError(error) ? error.hint : null;
}
