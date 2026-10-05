import { firstFieldMessage } from "@/lib/fieldErrors";
import type { ErrorDetail } from "./types";

/** A failed API call, carrying Charon's stable error code. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetail["details"];

  constructor(status: number, detail: ErrorDetail) {
    super(detail.message);
    this.name = "ApiError";
    this.status = status;
    this.code = detail.code;
    this.details = detail.details ?? null;
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
