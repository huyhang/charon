import type { JobStatus } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { isInFlight, STATUS_META } from "@/lib/jobs";

export function StatusBadge({ status }: { status: JobStatus }) {
  const { label, tone } = STATUS_META[status];
  return (
    <Badge tone={tone}>
      <span
        className={cn("size-1.5 rounded-full bg-current", isInFlight(status) && "animate-pulse")}
      />
      {label}
    </Badge>
  );
}
