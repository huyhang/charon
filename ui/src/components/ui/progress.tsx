import { cn } from "@/lib/cn";

interface ProgressProps {
  value: number;
  className?: string;
  /** Animated stripes for work in progress with no measurable percentage. */
  indeterminate?: boolean;
  tone?: "primary" | "success" | "danger" | "muted";
}

const FILL = {
  primary: "bg-river",
  success: "bg-success",
  danger: "bg-destructive",
  muted: "bg-muted-foreground/40",
};

export function Progress({
  value,
  className,
  indeterminate = false,
  tone = "primary",
}: ProgressProps) {
  const clamped = Math.min(Math.max(value, 0), 100);
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : Math.round(clamped)}
      className={cn("relative h-1.5 w-full overflow-hidden rounded-full bg-muted", className)}
    >
      <div
        className={cn(
          "h-full rounded-full transition-[width] duration-700 ease-out",
          FILL[tone],
          indeterminate && "animate-shimmer bg-[length:200%_100%]",
        )}
        style={{ width: `${indeterminate ? 100 : clamped}%` }}
      />
    </div>
  );
}
