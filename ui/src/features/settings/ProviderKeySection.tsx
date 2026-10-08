import { KeyRoundIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/api/errors";
import { useProviderKey, useRemoveProviderKey } from "@/api/queries";
import type { MetadataProvider, ProviderKey } from "@/api/types";
import { ErrorState } from "@/components/ErrorState";
import { ProviderCredit } from "@/components/ProviderCredit";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { keyCopy, ProviderKeyForm } from "./ProviderKeyForm";

/** Where the key in use comes from, in words. */
export function keySourceText(key: ProviderKey, environment: string | undefined): string {
  if (key.source === "settings") return "saved in Charon";
  return `from ${environment ?? "Charon's environment"}`;
}

function KeyStatus({
  provider,
  status,
  onReplace,
  onRemove,
}: {
  provider: MetadataProvider;
  status: ProviderKey;
  onReplace(): void;
  onRemove(): void;
}) {
  const copy = keyCopy(provider);
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg border bg-background/40 px-4 py-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border text-primary">
        <KeyRoundIcon className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-medium">{copy.name} set · lookups are on</p>
        <p className="text-xs text-muted-foreground">
          {status.hint && <code className="font-mono">…{status.hint}</code>}
          {status.hint && " · "}
          {keySourceText(status, copy.environment)}
        </p>
        {status.source === "environment" && (
          <p className="text-xs text-muted-foreground">One saved here takes its place.</p>
        )}
      </div>
      <Button variant="outline" size="sm" onClick={onReplace}>
        Replace
      </Button>
      {status.source === "settings" && (
        <Button
          variant="ghost"
          size="sm"
          className="text-destructive hover:text-destructive"
          onClick={onRemove}
        >
          Remove
        </Button>
      )}
    </div>
  );
}

/** A provider's key: where it comes from, and replacing or removing it. Admins only. */
export function ProviderKeySection({ provider }: { provider: MetadataProvider }) {
  const key = useProviderKey(provider.id);
  const remove = useRemoveProviderKey(provider.id);
  const [replacing, setReplacing] = useState(false);
  const [confirmingRemove, setConfirmingRemove] = useState(false);
  const copy = keyCopy(provider);

  const onRemove = () =>
    remove.mutate(undefined, {
      onSuccess: (after) => {
        setConfirmingRemove(false);
        toast(`${copy.name} removed`, {
          description: after.configured
            ? `Charon uses the one ${keySourceText(after, copy.environment)} again.`
            : "Title lookup is off until a new one is saved.",
        });
      },
      onError: (error) => toast.error("Couldn't remove it", { description: errorMessage(error) }),
    });

  return (
    <section aria-label={`${provider.name} title lookup`} className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-medium">{provider.name}</h3>
        <ProviderCredit provider={provider} />
      </div>
      {key.isPending ? (
        <Skeleton className="h-20 rounded-lg" />
      ) : key.isError ? (
        <ErrorState error={key.error} onRetry={() => key.refetch()} />
      ) : key.data.configured && !replacing ? (
        <KeyStatus
          provider={provider}
          status={key.data}
          onReplace={() => setReplacing(true)}
          onRemove={() => setConfirmingRemove(true)}
        />
      ) : (
        <ProviderKeyForm
          provider={provider}
          onSaved={() => setReplacing(false)}
          onCancel={replacing ? () => setReplacing(false) : undefined}
        />
      )}
      <ConfirmDialog
        open={confirmingRemove}
        onOpenChange={setConfirmingRemove}
        title={`Remove the ${copy.name}?`}
        description={
          copy.environment
            ? `If ${copy.environment} is set, Charon uses that one again; otherwise title lookup stops.`
            : "Title lookup stops until a new one is saved."
        }
        confirmLabel="Remove"
        onConfirm={onRemove}
        destructive
      />
    </section>
  );
}
