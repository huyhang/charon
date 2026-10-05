import { Popover as PopoverPrimitive } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;
export const PopoverAnchor = PopoverPrimitive.Anchor;

export function PopoverContent({
  className,
  ...props
}: ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        sideOffset={6}
        className={cn(
          "z-50 rounded-xl border bg-popover text-popover-foreground shadow-xl outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          className,
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
}
