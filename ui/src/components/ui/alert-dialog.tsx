import { AlertDialog as AlertPrimitive } from "radix-ui";
import type { ReactNode } from "react";
import { buttonVariants } from "./button";
import { overlayClassName } from "./dialog";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange(open: boolean): void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  onConfirm(): void;
  destructive?: boolean;
}

/** A confirmation step for actions that are hard to undo. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  onConfirm,
  destructive = false,
}: ConfirmDialogProps) {
  return (
    <AlertPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <AlertPrimitive.Portal>
        <AlertPrimitive.Overlay className={overlayClassName} />
        <AlertPrimitive.Content className="fixed top-[50%] left-[50%] z-50 grid w-[calc(100%-2rem)] max-w-md translate-x-[-50%] translate-y-[-50%] gap-4 rounded-2xl border bg-popover p-6 shadow-2xl duration-200 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95">
          <AlertPrimitive.Title className="text-lg font-semibold tracking-tight">
            {title}
          </AlertPrimitive.Title>
          <AlertPrimitive.Description className="text-sm text-muted-foreground">
            {description}
          </AlertPrimitive.Description>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <AlertPrimitive.Cancel className={buttonVariants({ variant: "ghost" })}>
              Cancel
            </AlertPrimitive.Cancel>
            <AlertPrimitive.Action
              className={buttonVariants({ variant: destructive ? "destructive" : "default" })}
              onClick={onConfirm}
            >
              {confirmLabel}
            </AlertPrimitive.Action>
          </div>
        </AlertPrimitive.Content>
      </AlertPrimitive.Portal>
    </AlertPrimitive.Root>
  );
}
