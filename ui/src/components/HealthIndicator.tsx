import { useHealth } from "@/api/queries";
import { cn } from "@/lib/cn";

type HealthState = "checking" | "reachable" | "unreachable" | "offline";

const COPY: Record<HealthState, { label: string; dot: string }> = {
  checking: { label: "Checking connection…", dot: "bg-muted-foreground" },
  reachable: { label: "Download Station connected", dot: "bg-success" },
  unreachable: { label: "Download Station unreachable", dot: "bg-warning" },
  offline: { label: "Charon unreachable", dot: "bg-destructive" },
};

export function healthState(
  data: { downloader: "reachable" | "unreachable" } | undefined,
  isError: boolean,
): HealthState {
  if (isError) return "offline";
  return data?.downloader ?? "checking";
}

export function HealthIndicator({ compact = false }: { compact?: boolean }) {
  const { data, isError } = useHealth();
  const state = healthState(data, isError);
  const { label, dot } = COPY[state];
  return (
    <div
      className="flex items-center gap-2 text-xs text-muted-foreground"
      role="status"
      title={label}
    >
      <span className="relative flex size-2">
        {state === "reachable" && (
          <span
            className={cn(
              "absolute inline-flex size-full animate-ping rounded-full opacity-50",
              dot,
            )}
          />
        )}
        <span className={cn("relative inline-flex size-2 rounded-full", dot)} />
      </span>
      <span className={cn(compact && "sr-only")}>{label}</span>
    </div>
  );
}
