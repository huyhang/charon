import { TriangleAlertIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { errorMessage } from "@/api/errors";
import { useJob, useRules } from "@/api/queries";
import type { Job } from "@/api/types";
import { CopyButton } from "@/components/CopyButton";
import { Progress } from "@/components/ui/progress";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { errorHint } from "@/lib/errorHints";
import { formatBytes, formatDateTime, formatEta, formatPercent, formatSpeed } from "@/lib/format";
import { jobTitle } from "@/lib/jobs";
import { magnetHash } from "@/lib/magnet";
import { JobActions } from "./JobActions";
import { StatusBadge } from "./StatusBadge";
import { Timeline } from "./Timeline";

function Field({
  label,
  children,
  copy,
}: {
  label: string;
  children: ReactNode;
  copy?: string | null;
}) {
  return (
    <div className="grid grid-cols-[7rem_1fr] items-start gap-3 py-2 text-sm">
      <dt className="pt-px text-muted-foreground">{label}</dt>
      <dd className="flex min-w-0 items-start gap-1">
        <div className="min-w-0 flex-1 break-all">{children}</div>
        {copy && (
          <CopyButton
            value={copy}
            label={`Copy ${label.toLowerCase()}`}
            className="-my-1.5 size-7"
          />
        )}
      </dd>
    </div>
  );
}

function JobDetails({ job }: { job: Job }) {
  const rules = useRules();
  const ruleId = job.processing.rule_id;
  const rule = rules.data?.find((r) => r.id === ruleId);
  const { progress } = job;
  return (
    <div className="space-y-6">
      {job.status === "downloading" && (
        <div className="space-y-2 rounded-xl border bg-card p-4">
          <div className="flex items-baseline justify-between">
            <span className="text-2xl font-semibold tabular-nums">
              {formatPercent(progress.percent)}
            </span>
            <span className="text-sm text-muted-foreground tabular-nums">
              {formatSpeed(progress.download_speed_bps)} · {formatEta(progress.eta_seconds)} left
            </span>
          </div>
          <Progress value={progress.percent} className="h-2" />
        </div>
      )}
      {job.error && (
        <div
          role="alert"
          className="space-y-1.5 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm"
        >
          <p className="flex items-center gap-2 font-medium text-destructive">
            <TriangleAlertIcon className="size-4" />
            {job.error.stage === "download" ? "Download failed" : "Filing failed"}
            <code className="ml-auto font-mono text-xs opacity-70">{job.error.code}</code>
          </p>
          <p className="break-words">{job.error.message}</p>
          {errorHint(job.error) && <p className="text-muted-foreground">{errorHint(job.error)}</p>}
        </div>
      )}
      <section className="space-y-3">
        <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Progress
        </h3>
        <Timeline job={job} />
      </section>
      <section>
        <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Details
        </h3>
        <dl className="divide-y">
          <Field label="Rule">
            {ruleId ? (
              <Link to="/rules" className="text-primary hover:underline">
                {rule?.name ?? ruleId}
              </Link>
            ) : (
              <span className="text-muted-foreground">
                {job.status === "done" ? "None matched" : "Not chosen yet"}
              </span>
            )}
          </Field>
          <Field label="Saved to" copy={job.processing.final_path}>
            <span className="font-mono text-xs">{job.processing.final_path ?? "—"}</span>
          </Field>
          <Field label="Size">{formatBytes(progress.size_bytes)}</Field>
          <Field label="Info hash" copy={magnetHash(job.magnet)}>
            <span className="font-mono text-xs">{magnetHash(job.magnet) ?? "—"}</span>
          </Field>
          <Field label="Magnet" copy={job.magnet}>
            <span className="line-clamp-2 font-mono text-xs text-muted-foreground">
              {job.magnet}
            </span>
          </Field>
          <Field label="Added">{formatDateTime(job.created_at)}</Field>
          <Field label="Downloaded">{formatDateTime(job.completed_at)}</Field>
          <Field label="Updated">{formatDateTime(job.updated_at)}</Field>
        </dl>
      </section>
    </div>
  );
}

interface JobDrawerProps {
  jobId: string | undefined;
  onClose(): void;
}

export function JobDrawer({ jobId, onClose }: JobDrawerProps) {
  const { data: job, error, isPending } = useJob(jobId);
  return (
    <Sheet open={jobId !== undefined} onOpenChange={(open) => !open && onClose()}>
      <SheetContent>
        <SheetHeader>
          <div className="flex items-center gap-2">
            {job && <StatusBadge status={job.status} />}
          </div>
          <SheetTitle className="font-mono text-base break-all">
            {job ? (jobTitle(job) ?? "Unnamed download") : "Download"}
          </SheetTitle>
          <SheetDescription className="sr-only">Download details</SheetDescription>
        </SheetHeader>
        <SheetBody>
          {job ? (
            <JobDetails job={job} />
          ) : error ? (
            <p className="text-sm text-destructive">{errorMessage(error)}</p>
          ) : (
            isPending && (
              <div className="space-y-3">
                <Skeleton className="h-20" />
                <Skeleton className="h-40" />
              </div>
            )
          )}
        </SheetBody>
        {job && (
          <SheetFooter>
            <JobActions job={job} size="default" />
          </SheetFooter>
        )}
      </SheetContent>
    </Sheet>
  );
}
