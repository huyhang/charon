import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

export function Card({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-card/80 text-card-foreground shadow-[0_1px_0_0_rgb(255_255_255/0.03)_inset] backdrop-blur-sm",
        className,
      )}
      {...props}
    />
  );
}
