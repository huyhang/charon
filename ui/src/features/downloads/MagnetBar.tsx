import { Loader2Icon, MagnetIcon, SendHorizonalIcon } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/api/errors";
import { useRules, useSubmitDownload } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { magnetFromInput, magnetName } from "@/lib/magnet";
import { MatchPreview } from "./MatchPreview";

const AUTO = "auto";

interface MagnetBarProps {
  /** A magnet to prefill, e.g. pasted elsewhere in the app. */
  initialMagnet?: string | null;
  /** Bumped to request focus, e.g. from the command palette. */
  focusSignal?: number;
}

export function MagnetBar({ initialMagnet, focusSignal = 0 }: MagnetBarProps) {
  const [value, setValue] = useState(initialMagnet ?? "");
  const [ruleChoice, setRuleChoice] = useState(AUTO);
  const inputRef = useRef<HTMLInputElement>(null);
  const rules = useRules();
  const submit = useSubmitDownload();

  useEffect(() => {
    if (initialMagnet) setValue(initialMagnet);
  }, [initialMagnet]);

  useEffect(() => {
    if (focusSignal || initialMagnet) inputRef.current?.focus();
  }, [focusSignal, initialMagnet]);

  const magnet = magnetFromInput(value);
  const invalid = value.trim() !== "" && magnet === null;
  const ruleId = ruleChoice === AUTO ? null : ruleChoice;

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!magnet) return;
    submit.mutate(
      { magnet, ruleId },
      {
        onSuccess: (job) => {
          toast.success("Download started", {
            description: job.name ?? magnetName(magnet) ?? undefined,
          });
          setValue("");
          setRuleChoice(AUTO);
        },
        onError: (error) =>
          toast.error("Couldn't start the download", { description: errorMessage(error) }),
      },
    );
  };

  return (
    <Card className="group relative overflow-hidden p-1.5 transition focus-within:border-primary/50 focus-within:shadow-[0_0_0_4px_var(--color-ring)]">
      <form onSubmit={onSubmit} className="flex flex-col gap-1.5 sm:flex-row sm:items-center">
        <label className="flex min-w-0 flex-1 items-center gap-3 px-3">
          <MagnetIcon className="size-4 shrink-0 text-primary" />
          <span className="sr-only">Magnet link</span>
          <input
            ref={inputRef}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Paste a magnet link…"
            aria-invalid={invalid}
            spellCheck={false}
            autoComplete="off"
            className="h-10 min-w-0 flex-1 bg-transparent font-mono text-sm outline-none placeholder:font-sans placeholder:text-muted-foreground"
          />
        </label>
        <div className="flex items-center gap-1.5">
          <Select value={ruleChoice} onValueChange={setRuleChoice}>
            <SelectTrigger
              className="h-9 w-full border-transparent bg-muted/50 sm:w-40"
              aria-label="Rule"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={AUTO}>Auto-match rule</SelectItem>
              {rules.data?.map((rule) => (
                <SelectItem key={rule.id} value={rule.id}>
                  {rule.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button type="submit" disabled={!magnet || submit.isPending} className="h-9">
            {submit.isPending ? <Loader2Icon className="animate-spin" /> : <SendHorizonalIcon />}
            Download
          </Button>
        </div>
      </form>
      {(magnet || invalid) && (
        <div className="animate-in border-t px-4 py-3 duration-200 fade-in slide-in-from-top-1">
          {invalid ? (
            <p className="text-xs text-destructive">
              That doesn&apos;t look like a magnet link. It should start with{" "}
              <code className="font-mono">magnet:?</code>
            </p>
          ) : (
            <MatchPreview name={magnetName(magnet!)} ruleId={ruleId} />
          )}
        </div>
      )}
    </Card>
  );
}
