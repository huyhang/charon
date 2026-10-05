import { Loader2Icon, RotateCwIcon, UnplugIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

export const RETRY_MS = 5000;

interface UnreachablePageProps {
  error: string;
  onRetry(): Promise<void>;
  retryMs?: number;
}

/** Shown when Charon doesn't answer as the app opens. Keeps retrying until it does. */
export function UnreachablePage({ error, onRetry, retryMs = RETRY_MS }: UnreachablePageProps) {
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => void onRetry(), retryMs);
    return () => clearInterval(timer);
  }, [onRetry, retryMs]);

  const retryNow = async () => {
    setPending(true);
    await onRetry();
    setPending(false);
  };

  return (
    <div className="flex min-h-dvh items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-5 rounded-2xl border bg-card/80 p-6 text-center shadow-2xl">
        <UnplugIcon className="mx-auto size-10 text-warning" />
        <div className="space-y-2">
          <h1 className="text-xl font-semibold tracking-tight">Can&apos;t reach Charon</h1>
          <p className="text-sm text-muted-foreground">
            It may be restarting, or the NAS may be off. This page retries every few seconds.
          </p>
          <p role="alert" className="font-mono text-xs break-all text-destructive">
            {error}
          </p>
        </div>
        <Button className="w-full" onClick={retryNow} disabled={pending}>
          {pending ? <Loader2Icon className="animate-spin" /> : <RotateCwIcon />}
          Retry now
        </Button>
      </div>
    </div>
  );
}
