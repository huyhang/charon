import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "flex h-9 w-full min-w-0 rounded-lg border border-input bg-background/40 px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none placeholder:text-muted-foreground/70 focus-visible:border-primary/60 focus-visible:ring-[3px] focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20",
        className,
      )}
      {...props}
    />
  );
}
