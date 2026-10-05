import { CheckIcon, XIcon } from "lucide-react";
import type { Job } from "@/api/types";
import { cn } from "@/lib/cn";
import { timeline, type StepState } from "@/lib/jobs";

const DOT: Record<StepState, string> = {
  complete: "border-success bg-success text-background",
  current: "border-primary bg-primary/15 text-primary",
  upcoming: "border-border bg-background text-muted-foreground",
  failed: "border-destructive bg-destructive text-white",
  skipped: "border-border bg-muted text-muted-foreground",
};

export function Timeline({ job }: { job: Pick<Job, "status" | "error"> }) {
  const steps = timeline(job);
  return (
    <ol className="space-y-0" aria-label="Progress">
      {steps.map((step, index) => (
        <li
          key={step.status}
          className="relative flex gap-3 pb-4 last:pb-0"
          aria-current={step.state === "current" ? "step" : undefined}
        >
          {index < steps.length - 1 && (
            <span
              aria-hidden
              className={cn(
                "absolute top-5 left-[9px] h-[calc(100%-12px)] w-px",
                step.state === "complete" ? "bg-success/60" : "bg-border",
              )}
            />
          )}
          <span
            className={cn(
              "relative z-10 flex size-[19px] shrink-0 items-center justify-center rounded-full border text-[10px]",
              DOT[step.state],
            )}
          >
            {step.state === "complete" && <CheckIcon className="size-3" strokeWidth={3} />}
            {step.state === "failed" && <XIcon className="size-3" strokeWidth={3} />}
            {step.state === "current" && (
              <span className="size-1.5 animate-pulse rounded-full bg-current" />
            )}
          </span>
          <span
            className={cn(
              "text-sm",
              step.state === "upcoming" || step.state === "skipped"
                ? "text-muted-foreground"
                : "text-foreground",
              step.state === "failed" && "text-destructive",
            )}
          >
            {step.label}
          </span>
        </li>
      ))}
    </ol>
  );
}
