import { CheckIcon, CopyIcon } from "lucide-react";
import { useCopy } from "@/hooks/useCopy";
import { cn } from "@/lib/cn";
import { Button } from "./ui/button";

interface CopyButtonProps {
  value: string;
  label?: string;
  className?: string;
}

export function CopyButton({ value, label = "Copy", className }: CopyButtonProps) {
  const { copied, copy } = useCopy();
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      className={cn("text-muted-foreground", className)}
      onClick={(event) => {
        event.stopPropagation();
        void copy(value);
      }}
      aria-label={copied ? "Copied" : label}
    >
      {copied ? <CheckIcon className="text-success" /> : <CopyIcon />}
    </Button>
  );
}
