import type { DownloadSummary, Job, JobStatus } from "@/api/types";
import { magnetName } from "./magnet";

export type Tone = "neutral" | "info" | "progress" | "success" | "danger" | "muted";

interface StatusMeta {
  label: string;
  tone: Tone;
}

export const STATUS_META: Record<JobStatus, StatusMeta> = {
  queued: { label: "Queued", tone: "neutral" },
  downloading: { label: "Downloading", tone: "progress" },
  completed: { label: "Downloaded", tone: "info" },
  processing: { label: "Filing", tone: "info" },
  done: { label: "Done", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "muted" },
};

const IN_FLIGHT: ReadonlySet<JobStatus> = new Set([
  "queued",
  "downloading",
  "completed",
  "processing",
]);
const CANCELLABLE: ReadonlySet<JobStatus> = new Set(["queued", "downloading", "completed"]);

export const isInFlight = (status: JobStatus): boolean => IN_FLIGHT.has(status);
export const canCancel = (status: JobStatus): boolean => CANCELLABLE.has(status);
export const canRetry = (status: JobStatus): boolean => status === "failed";

/** The best name we have: Download Station's, else the one the magnet advertises. */
export function jobTitle(job: Pick<Job, "name" | "magnet">): string | null {
  return job.name ?? magnetName(job.magnet);
}

export type FilterId = "all" | "active" | "done" | "failed" | "cancelled";

export const FILTERS: { id: FilterId; label: string; statuses?: JobStatus[] }[] = [
  { id: "all", label: "All" },
  { id: "active", label: "Active", statuses: [...IN_FLIGHT] },
  { id: "done", label: "Done", statuses: ["done"] },
  { id: "failed", label: "Failed", statuses: ["failed"] },
  { id: "cancelled", label: "Cancelled", statuses: ["cancelled"] },
];

export function statusesFor(filter: FilterId): JobStatus[] | undefined {
  return FILTERS.find((f) => f.id === filter)?.statuses;
}

export const FAST_POLL_MS = 1500;
export const SLOW_POLL_MS = 15000;

/** Poll quickly only while something is moving. */
export function pollInterval(jobs: readonly Job[]): number {
  return jobs.some((job) => isInFlight(job.status)) ? FAST_POLL_MS : SLOW_POLL_MS;
}

export interface Summary {
  active: number;
  speedBps: number;
  done: number;
  failed: number;
}

/** Headline numbers from Charon's totals. A status missing from `counts` has no jobs. */
export function summarize(summary: DownloadSummary): Summary {
  const count = (status: JobStatus) => summary.counts[status] ?? 0;
  return {
    active: [...IN_FLIGHT].reduce((sum, status) => sum + count(status), 0),
    speedBps: summary.download_speed_bps,
    done: count("done"),
    failed: count("failed"),
  };
}

export function summaryPollInterval(summary: DownloadSummary | undefined): number {
  return summary && summarize(summary).active > 0 ? FAST_POLL_MS : SLOW_POLL_MS;
}

export type StepState = "complete" | "current" | "upcoming" | "failed" | "skipped";

export interface TimelineStep {
  status: JobStatus;
  label: string;
  state: StepState;
}

const PATH: JobStatus[] = ["queued", "downloading", "completed", "processing", "done"];

/** The happy path, annotated with where this job is or where it stopped. */
export function timeline(job: Pick<Job, "status" | "error">): TimelineStep[] {
  const stop = stopIndex(job);
  return PATH.map((status, index) => ({
    status,
    label: STATUS_META[status].label,
    state: stepState(job.status, index, stop),
  }));
}

function stopIndex(job: Pick<Job, "status" | "error">): number {
  if (job.status === "failed")
    return PATH.indexOf(job.error?.stage === "processing" ? "processing" : "downloading");
  if (job.status === "cancelled") return -1;
  return PATH.indexOf(job.status);
}

function stepState(status: JobStatus, index: number, stop: number): StepState {
  if (status === "cancelled") return "skipped";
  if (index < stop) return "complete";
  if (index > stop) return "upcoming";
  if (status === "failed") return "failed";
  return status === "done" ? "complete" : "current";
}
