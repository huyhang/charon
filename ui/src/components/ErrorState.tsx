import { AlertTriangleIcon } from "lucide-react";
import { errorMessage } from "@/api/errors";
import { Button } from "./ui/button";

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-center gap-3 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm"
    >
      <AlertTriangleIcon className="size-4 shrink-0 text-destructive" />
      <span className="flex-1">{errorMessage(error)}</span>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
