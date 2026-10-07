import {
  CheckCircle2Icon,
  CircleDashedIcon,
  FlaskConicalIcon,
  Loader2Icon,
  TriangleAlertIcon,
} from "lucide-react";
import { useId, useState } from "react";
import { errorMessage } from "@/api/errors";
import { allJobs, useDownloads, usePreview } from "@/api/queries";
import type { RuleSpec } from "@/api/types";
import { NameDiff } from "@/components/NameDiff";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { isPreviewable } from "@/lib/rules";

/** Recent download names, offered as realistic samples. */
function useSampleNames(): string[] {
  const downloads = useDownloads("all");
  const names = allJobs(downloads.data).flatMap((job) => (job.name ? [job.name] : []));
  return [...new Set(names)].slice(0, 10);
}

function Result({ spec, name }: { spec: RuleSpec; name: string }) {
  const request = useDebouncedValue(isPreviewable(spec) && name ? { name, rule: spec } : null, 300);
  const preview = usePreview(request);

  if (!isPreviewable(spec)) {
    return (
      <p className="text-xs text-muted-foreground">
        Fill in a pattern and destination to try the rule.
      </p>
    );
  }
  if (!name)
    return <p className="text-xs text-muted-foreground">Type a sample name to see what happens.</p>;
  if (preview.isError) {
    return (
      <p className="flex items-start gap-2 text-xs text-warning">
        <TriangleAlertIcon className="mt-px size-3.5 shrink-0" />
        {errorMessage(preview.error)}
      </p>
    );
  }
  if (!preview.data) {
    return (
      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2Icon className="size-3.5 animate-spin" /> Trying…
      </p>
    );
  }
  if (!preview.data.final_path) {
    return (
      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <CircleDashedIcon className="size-3.5" /> The pattern doesn&apos;t match this name.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <p className="flex items-center gap-2 text-xs text-success">
        <CheckCircle2Icon className="size-3.5" /> Matches
      </p>
      <NameDiff before={name} after={preview.data.new_name} />
      <p className="font-mono text-xs break-all text-muted-foreground">
        → {preview.data.final_path}
      </p>
    </div>
  );
}

/** Runs the unsaved draft on the server against a sample name, as you type. */
export function TestBench({ spec, initialName = "" }: { spec: RuleSpec; initialName?: string }) {
  const samples = useSampleNames();
  const [name, setName] = useState(initialName);
  const listId = useId();
  const sample = name || samples[0] || "";

  return (
    <div className="space-y-3 rounded-xl border border-primary/20 bg-primary/[0.03] p-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        <FlaskConicalIcon className="size-4 text-primary" /> Test bench
      </div>
      <Input
        aria-label="Sample name"
        list={listId}
        value={name}
        placeholder={samples[0] ?? "Some.Show.S01E01.1080p.mkv"}
        onChange={(event) => setName(event.target.value)}
        spellCheck={false}
        className="font-mono text-xs"
      />
      <datalist id={listId}>
        {samples.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      <Result spec={spec} name={sample} />
    </div>
  );
}
