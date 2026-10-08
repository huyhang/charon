import { Loader2Icon } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { errorHintOf, errorMessage } from "@/api/errors";
import { useSaveProviderKey } from "@/api/queries";
import type { ProviderInfo } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface KeyCopy {
  /** What the provider calls the key. */
  name: string;
  /** Where to get it. */
  help: ReactNode;
  /** The setting that gives Charon a key when it starts, used while none is saved. */
  environment?: string;
}

const COPY: Record<string, KeyCopy> = {
  tmdb: {
    name: "API Read Access Token",
    help: (
      <>
        Free for personal use: on{" "}
        <a
          href="https://www.themoviedb.org/settings/api"
          target="_blank"
          rel="noreferrer"
          className="text-primary underline underline-offset-2"
        >
          themoviedb.org → Settings → API
        </a>
        , copy the long API Read Access Token, not the short API Key.
      </>
    ),
    environment: "CHARON_TMDB_TOKEN",
  },
};

export function keyCopy(provider: ProviderInfo): KeyCopy {
  return COPY[provider.id] ?? { name: "API key", help: `The key ${provider.name} gave you.` };
}

interface ProviderKeyFormProps {
  provider: ProviderInfo;
  onSaved?(): void;
  /** Shows a Cancel button. */
  onCancel?(): void;
}

/** Saves a provider's key in Charon. Charon never shows the key back. */
export function ProviderKeyForm({ provider, onSaved, onCancel }: ProviderKeyFormProps) {
  const [key, setKey] = useState("");
  const save = useSaveProviderKey(provider.id);
  const inputId = useId();
  const copy = keyCopy(provider);

  // Rendered inside the rule editor too (through a dialog): Enter here mustn't save the rule.
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    event.stopPropagation();
    if (!key.trim() || save.isPending) return;
    save.mutate(key.trim(), {
      onSuccess: () => {
        toast.success(`${provider.name} ${copy.name.toLowerCase()} saved`, {
          description: "Title lookup is ready.",
        });
        setKey("");
        onSaved?.();
      },
    });
  };

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor={inputId}>
          {provider.name} {copy.name}
        </Label>
        <Input
          id={inputId}
          type="password"
          value={key}
          onChange={(event) => setKey(event.target.value)}
          autoComplete="off"
          spellCheck={false}
          aria-invalid={save.isError || undefined}
          className="font-mono text-xs"
        />
        <p className="text-xs text-muted-foreground">{copy.help}</p>
      </div>
      {save.isError && (
        <p role="alert" className="text-xs text-destructive">
          {errorMessage(save.error)}
          {errorHintOf(save.error) && (
            <span className="block text-muted-foreground">{errorHintOf(save.error)}</span>
          )}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={!key.trim() || save.isPending}>
          {save.isPending && <Loader2Icon className="animate-spin" />}
          Save
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}
