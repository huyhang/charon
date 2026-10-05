import { CheckIcon, FolderInputIcon, TriangleAlertIcon } from "lucide-react";
import type { Job } from "@/api/types";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/cn";
import { errorHint } from "@/lib/errorHints";
import { formatBytes, formatEta, formatPercent, formatRelative, formatSpeed } from "@/lib/format";
import { jobTitle } from "@/lib/jobs";
import { JobActions } from "./JobActions";
import { StatusBadge } from "./StatusBadge";

function JobDetail({ job }: { job: Job }) {
  const { progress } = job;
  switch (job.status) {
    case "queued":
      return (
        <div className="space-y-2">
          <Progress value={0} indeterminate tone="muted" />
          <p className="text-xs text-muted-foreground">Waiting for Download Station…</p>
        </div>
      );
    case "downloading":
      return (
        <div className="space-y-2">
          <Progress value={progress.percent} />
          <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground tabular-nums">
            <span className="font-medium text-foreground">{formatPercent(progress.percent)}</span>
            <span>{formatSpeed(progress.download_speed_bps)}</span>
            <span>{formatEta(progress.eta_seconds)} left</span>
            <span>
              {formatBytes(progress.downloaded_bytes)} of {formatBytes(progress.size_bytes)}
            </span>
          </p>
        </div>
      );
    case "completed":
    case "processing":
      return (
        <div className="space-y-2">
          <Progress value={100} indeterminate />
          <p className="text-xs text-muted-foreground">Renaming and moving into place…</p>
        </div>
      );
    case "done":
      return (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          {job.processing.final_path ? (
            <>
              <FolderInputIcon className="size-3.5 shrink-0 text-success" />
              <span className="truncate font-mono">{job.processing.final_path}</span>
            </>
          ) : (
            <>
              <CheckIcon className="size-3.5 shrink-0 text-success" />
              No rule matched. Left in the download folder.
            </>
          )}
        </p>
      );
    case "failed":
      return (
        <div className="space-y-1 text-xs">
          <p className="flex items-start gap-2 text-destructive">
            <TriangleAlertIcon className="mt-px size-3.5 shrink-0" />
            <span className="break-words">{job.error?.message ?? "Failed"}</span>
          </p>
          {errorHint(job.error) && (
            <p className="pl-5.5 text-muted-foreground">{errorHint(job.error)}</p>
          )}
        </div>
      );
    case "cancelled":
      return <p className="text-xs text-muted-foreground">Cancelled.</p>;
  }
}

interface JobCardProps {
  job: Job;
  onOpen(job: Job): void;
}

export function JobCard({ job, onOpen }: JobCardProps) {
  const title = jobTitle(job);
  return (
    <article
      role="button"
      tabIndex={0}
      aria-label={title ?? "Unnamed download"}
      onClick={() => onOpen(job)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(job);
        }
      }}
      className={cn(
        "group cursor-pointer space-y-3 rounded-xl border bg-card/70 p-4 transition outline-none hover:border-primary/30 hover:bg-card focus-visible:ring-[3px] focus-visible:ring-ring",
        job.status === "cancelled" && "opacity-60",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 flex-1 truncate font-mono text-sm font-medium">
          {title ?? <span className="text-muted-foreground">Fetching name…</span>}
        </h3>
        <StatusBadge status={job.status} />
      </div>
      <JobDetail job={job} />
      <div className="flex min-h-7 items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">Added {formatRelative(job.created_at)}</p>
        <JobActions job={job} />
      </div>
    </article>
  );
}
