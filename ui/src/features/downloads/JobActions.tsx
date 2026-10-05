import { RotateCcwIcon, XIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/api/errors";
import { useCancelDownload, useRetryDownload } from "@/api/queries";
import type { Job } from "@/api/types";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { canCancel, canRetry, jobTitle } from "@/lib/jobs";

/** Retry and cancel, shown only when the job's status allows them. */
export function JobActions({ job, size = "sm" }: { job: Job; size?: "sm" | "default" }) {
  const cancel = useCancelDownload();
  const retry = useRetryDownload();
  const [confirming, setConfirming] = useState(false);
  const label = jobTitle(job) ?? "this download";

  const onRetry = () =>
    retry.mutate(job.id, {
      onSuccess: () => toast.success("Retrying", { description: label }),
      onError: (error) => toast.error("Couldn't retry", { description: errorMessage(error) }),
    });
  const onCancel = () =>
    cancel.mutate(job.id, {
      onSuccess: () => toast("Download cancelled", { description: label }),
      onError: (error) => toast.error("Couldn't cancel", { description: errorMessage(error) }),
    });

  return (
    <div className="flex items-center gap-1.5" onClick={(event) => event.stopPropagation()}>
      {canRetry(job.status) && (
        <Button variant="outline" size={size} onClick={onRetry} disabled={retry.isPending}>
          <RotateCcwIcon /> Retry
        </Button>
      )}
      {canCancel(job.status) && (
        <>
          <Button
            variant="ghost"
            size={size}
            onClick={() => setConfirming(true)}
            disabled={cancel.isPending}
          >
            <XIcon /> Cancel
          </Button>
          <ConfirmDialog
            open={confirming}
            onOpenChange={setConfirming}
            title="Cancel this download?"
            description={
              <>
                <span className="font-mono break-all">{label}</span> will be removed from Download
                Station. You can&apos;t resume it later.
              </>
            }
            confirmLabel="Cancel download"
            onConfirm={onCancel}
            destructive
          />
        </>
      )}
    </div>
  );
}
