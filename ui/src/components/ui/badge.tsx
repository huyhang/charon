import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

export const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap [&_svg]:size-3",
  {
    variants: {
      tone: {
        neutral: "border-border bg-secondary text-secondary-foreground",
        info: "border-info/25 bg-info/10 text-info",
        progress: "border-primary/25 bg-primary/10 text-primary",
        success: "border-success/25 bg-success/10 text-success",
        danger: "border-destructive/25 bg-destructive/10 text-destructive",
        muted: "border-border bg-transparent text-muted-foreground",
        warning: "border-warning/25 bg-warning/10 text-warning",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export interface BadgeProps extends ComponentProps<"span">, VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
