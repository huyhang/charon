import { CheckIcon, CopyIcon, KeyRoundIcon, Loader2Icon, ShieldAlertIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { errorMessage } from "@/api/errors";
import { useIssueKey } from "@/api/queries";
import type { IssuedApiKey, Role } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import { useCopy } from "@/hooks/useCopy";
import { errorProps, FormField } from "@/features/rules/FormField";

const ROLE_HINTS: Record<Role, string> = {
  client: "Can add downloads and manage rules. Best for phones, scripts and browsers.",
  admin: "Can also issue and revoke keys.",
};

function IssueForm({ onIssued }: { onIssued(key: IssuedApiKey): void }) {
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("client");
  const issue = useIssueKey();
  const error = issue.isError ? errorMessage(issue.error) : undefined;

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    issue.mutate({ name: name.trim(), role }, { onSuccess: onIssued });
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5">
      <DialogHeader>
        <DialogTitle>Issue an API key</DialogTitle>
        <DialogDescription>
          One key per device or script makes it easy to revoke just one.
        </DialogDescription>
      </DialogHeader>
      <FormField id="key-name" label="Name" error={error}>
        <Input
          id="key-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. phone, laptop, sonarr"
          maxLength={100}
          autoFocus
          {...errorProps("key-name", error)}
        />
      </FormField>
      <div className="space-y-2">
        <Segmented<Role>
          label="Role"
          value={role}
          onChange={setRole}
          options={[
            { value: "client", label: "Client" },
            { value: "admin", label: "Admin" },
          ]}
        />
        <p className="text-xs text-muted-foreground">{ROLE_HINTS[role]}</p>
      </div>
      <DialogFooter>
        <Button type="submit" disabled={!name.trim() || issue.isPending}>
          {issue.isPending ? <Loader2Icon className="animate-spin" /> : <KeyRoundIcon />}
          Issue key
        </Button>
      </DialogFooter>
    </form>
  );
}

function RevealKey({ issued, onDone }: { issued: IssuedApiKey; onDone(): void }) {
  const { copied, copy } = useCopy();
  return (
    <div className="space-y-5">
      <DialogHeader>
        <DialogTitle>Key for {issued.name}</DialogTitle>
        <DialogDescription>
          Copy it now. For your safety, Charon won&apos;t show it again.
        </DialogDescription>
      </DialogHeader>
      <div className="flex items-center gap-2 rounded-xl border border-primary/30 bg-primary/5 p-3">
        <code
          className="min-w-0 flex-1 font-mono text-sm break-all select-all"
          data-testid="issued-key"
        >
          {issued.key}
        </code>
        <Button type="button" variant="outline" size="sm" onClick={() => copy(issued.key)}>
          {copied ? <CheckIcon className="text-success" /> : <CopyIcon />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <p className="flex items-start gap-2 text-xs text-muted-foreground">
        <ShieldAlertIcon className="mt-px size-3.5 shrink-0 text-warning" />
        Send it as the <code className="font-mono">X-API-Key</code> header, or paste it into
        Charon&apos;s sign-in screen on that device.
      </p>
      <DialogFooter>
        <Button type="button" onClick={onDone}>
          Done
        </Button>
      </DialogFooter>
    </div>
  );
}

interface IssueKeyDialogProps {
  open: boolean;
  onOpenChange(open: boolean): void;
}

export function IssueKeyDialog({ open, onOpenChange }: IssueKeyDialogProps) {
  const [issued, setIssued] = useState<IssuedApiKey | null>(null);
  const close = () => {
    onOpenChange(false);
    setIssued(null);
  };
  return (
    // Nothing in the dialog opens it, so Radix only ever asks to close it.
    <Dialog open={open} onOpenChange={close}>
      {/* Keep the secret from vanishing on a stray click outside. */}
      <DialogContent onInteractOutside={(event) => issued && event.preventDefault()}>
        {issued ? <RevealKey issued={issued} onDone={close} /> : <IssueForm onIssued={setIssued} />}
      </DialogContent>
    </Dialog>
  );
}
