import {
  ActivityIcon,
  CheckCircle2Icon,
  GaugeIcon,
  XCircleIcon,
  type LucideIcon,
} from "lucide-react";
import type { DownloadSummary } from "@/api/types";
import { formatSpeed } from "@/lib/format";
import { summarize } from "@/lib/jobs";
import { cn } from "@/lib/cn";

function Stat({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="flex items-center gap-3 rounded-xl border bg-card/60 px-4 py-3"
    >
      <div className={cn("flex size-8 items-center justify-center rounded-lg bg-current/10", tone)}>
        <Icon className="size-4" />
      </div>
      <div className="min-w-0">
        <div className="text-lg leading-tight font-semibold tabular-nums">{value}</div>
        <div className="text-xs text-muted-foreground">{label}</div>
      </div>
    </div>
  );
}

const PENDING = "—";

/** Totals across every download; shows dashes until the first summary arrives. */
export function StatsStrip({ summary }: { summary: DownloadSummary | undefined }) {
  const stats = summary && summarize(summary);
  const count = (value: number | undefined) => (value === undefined ? PENDING : String(value));
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Stat
        icon={ActivityIcon}
        label="In progress"
        value={count(stats?.active)}
        tone="text-primary"
      />
      <Stat
        icon={GaugeIcon}
        label="Download speed"
        value={stats ? formatSpeed(stats.speedBps) : PENDING}
        tone="text-info"
      />
      <Stat icon={CheckCircle2Icon} label="Done" value={count(stats?.done)} tone="text-success" />
      <Stat
        icon={XCircleIcon}
        label="Failed"
        value={count(stats?.failed)}
        tone="text-destructive"
      />
    </div>
  );
}
