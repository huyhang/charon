import { KeyRoundIcon, PlusIcon, ShieldIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/api/errors";
import { useApiKeys, useRevokeKey } from "@/api/queries";
import type { ApiKey } from "@/api/types";
import { usePrincipal } from "@/auth/AuthProvider";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";
import { IssueKeyDialog } from "./IssueKeyDialog";

/** Active keys first (newest first), then revoked ones. */
export function sortKeys(keys: readonly ApiKey[]): ApiKey[] {
  return [...keys].sort(
    (a, b) =>
      Number(a.revoked_at !== null) - Number(b.revoked_at !== null) ||
      b.created_at.localeCompare(a.created_at),
  );
}

function KeyRow({
  apiKey,
  isCurrent,
  onRevoke,
}: {
  apiKey: ApiKey;
  isCurrent: boolean;
  onRevoke(key: ApiKey): void;
}) {
  const revoked = apiKey.revoked_at !== null;
  return (
    <li className={cn("flex items-center gap-4 px-4 py-3", revoked && "opacity-55")}>
      <div
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-lg border",
          apiKey.role === "admin" ? "text-primary" : "text-muted-foreground",
        )}
      >
        {apiKey.role === "admin" ? (
          <ShieldIcon className="size-4" />
        ) : (
          <KeyRoundIcon className="size-4" />
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-0.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-medium">{apiKey.name}</span>
          <Badge tone={apiKey.role === "admin" ? "progress" : "neutral"}>{apiKey.role}</Badge>
          {isCurrent && <Badge tone="success">this browser</Badge>}
          {revoked && <Badge tone="muted">revoked {formatRelative(apiKey.revoked_at!)}</Badge>}
        </div>
        <p className="text-xs text-muted-foreground">
          <code className="font-mono">{apiKey.prefix}…</code> · created{" "}
          {formatRelative(apiKey.created_at)}
        </p>
      </div>
      {!revoked && (
        <Button
          variant="ghost"
          size="sm"
          className="text-destructive hover:text-destructive"
          onClick={() => onRevoke(apiKey)}
        >
          Revoke
        </Button>
      )}
    </li>
  );
}

export function KeysPage() {
  const principal = usePrincipal();
  const keys = useApiKeys();
  const revoke = useRevokeKey();
  const [issuing, setIssuing] = useState(false);
  const [revoking, setRevoking] = useState<ApiKey | null>(null);

  const onRevoke = (key: ApiKey) =>
    revoke.mutate(key.id, {
      onSuccess: () => toast("Key revoked", { description: `${key.name} can no longer sign in.` }),
      onError: (error) =>
        toast.error("Couldn't revoke the key", { description: errorMessage(error) }),
    });

  return (
    <div className="space-y-8">
      <PageHeader
        title="API keys"
        description="Give every device or script its own key, so you can revoke one without touching the others."
        actions={
          <Button onClick={() => setIssuing(true)}>
            <PlusIcon /> Issue key
          </Button>
        }
      />
      {keys.isPending ? (
        <Skeleton className="h-48 rounded-xl" />
      ) : keys.isError ? (
        <ErrorState error={keys.error} onRetry={() => keys.refetch()} />
      ) : keys.data.length === 0 ? (
        <EmptyState
          icon={KeyRoundIcon}
          title="No issued keys"
          description="You're using the bootstrap admin key. Issue a key for each device instead of sharing it."
          action={
            <Button onClick={() => setIssuing(true)}>
              <PlusIcon /> Issue your first key
            </Button>
          }
        />
      ) : (
        <ul className="divide-y overflow-hidden rounded-xl border bg-card/70">
          {sortKeys(keys.data).map((key) => (
            <KeyRow
              key={key.id}
              apiKey={key}
              isCurrent={key.id === principal.key_id}
              onRevoke={setRevoking}
            />
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">
        The bootstrap admin key comes from <code className="font-mono">CHARON_ADMIN_API_KEY</code>{" "}
        and isn&apos;t listed here. Rotate it by changing the setting and restarting Charon.
      </p>
      <IssueKeyDialog open={issuing} onOpenChange={setIssuing} />
      <ConfirmDialog
        open={revoking !== null}
        onOpenChange={(open) => !open && setRevoking(null)}
        title={`Revoke "${revoking?.name}"?`}
        description={
          revoking?.id === principal.key_id
            ? "This is the key this browser is using. You'll be signed out immediately."
            : "Anything using this key is rejected from its very next request. This can't be undone."
        }
        confirmLabel="Revoke key"
        onConfirm={() => revoking && onRevoke(revoking)}
        destructive
      />
    </div>
  );
}
