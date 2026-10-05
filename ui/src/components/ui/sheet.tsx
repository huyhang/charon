import { XIcon } from "lucide-react";
import { Dialog as SheetPrimitive } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";
import { DialogOverlay } from "./dialog";

export const Sheet = SheetPrimitive.Root;
export const SheetClose = SheetPrimitive.Close;

/** A panel that slides in from the right (or up from the bottom on small screens). */
export function SheetContent({
  className,
  children,
  ...props
}: ComponentProps<typeof SheetPrimitive.Content>) {
  return (
    <SheetPrimitive.Portal>
      <DialogOverlay />
      <SheetPrimitive.Content
        className={cn(
          "fixed z-50 flex flex-col bg-popover shadow-2xl transition ease-in-out data-[state=closed]:animate-out data-[state=closed]:duration-200 data-[state=open]:animate-in data-[state=open]:duration-300",
          "inset-x-0 bottom-0 max-h-[92dvh] rounded-t-2xl border-t data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom",
          "sm:inset-y-0 sm:right-0 sm:left-auto sm:h-full sm:max-h-none sm:w-full sm:max-w-xl sm:rounded-none sm:border-t-0 sm:border-l sm:data-[state=closed]:slide-out-to-right sm:data-[state=open]:slide-in-from-right",
          className,
        )}
        {...props}
      >
        {children}
        <SheetPrimitive.Close className="absolute top-4 right-4 rounded-md p-1 text-muted-foreground transition hover:bg-accent hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:outline-none">
          <XIcon className="size-4" />
          <span className="sr-only">Close</span>
        </SheetPrimitive.Close>
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  );
}

export function SheetHeader({ className, ...props }: ComponentProps<"div">) {
  return (
    <div className={cn("flex flex-col gap-1 border-b px-6 pt-6 pb-4", className)} {...props} />
  );
}

export function SheetBody({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("flex-1 overflow-y-auto px-6 py-5", className)} {...props} />;
}

export function SheetFooter({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn("flex items-center justify-end gap-2 border-t px-6 py-4", className)}
      {...props}
    />
  );
}

export function SheetTitle({ className, ...props }: ComponentProps<typeof SheetPrimitive.Title>) {
  return (
    <SheetPrimitive.Title
      className={cn("pr-8 text-lg font-semibold tracking-tight", className)}
      {...props}
    />
  );
}

export function SheetDescription({
  className,
  ...props
}: ComponentProps<typeof SheetPrimitive.Description>) {
  return (
    <SheetPrimitive.Description
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}
