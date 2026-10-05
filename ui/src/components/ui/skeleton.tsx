import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "animate-shimmer rounded-md bg-[linear-gradient(90deg,var(--color-muted)_0%,var(--color-accent)_50%,var(--color-muted)_100%)] bg-[length:200%_100%]",
        className,
      )}
      {...props}
    />
  );
}
