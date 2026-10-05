import { ArrowRightIcon, FolderIcon, InfoIcon, Loader2Icon, TriangleAlertIcon } from "lucide-react";
import type { ReactNode } from "react";
import { errorMessage } from "@/api/errors";
import { usePreview, useRules } from "@/api/queries";
import { NameDiff } from "@/components/NameDiff";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";

interface MatchPreviewProps {
  name: string | null;
  ruleId: string | null;
}

function Line({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-xs text-muted-foreground [&_svg]:mt-0.5 [&_svg]:size-3.5 [&_svg]:shrink-0">
      {icon}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

/** What Charon will do with a download of this name, before submitting it. */
export function MatchPreview({ name, ruleId }: MatchPreviewProps) {
  const debouncedName = useDebouncedValue(name);
  const preview = usePreview(debouncedName ? { name: debouncedName, rule_id: ruleId } : null);
  const rules = useRules();

  if (!name) {
    return (
      <Line icon={<InfoIcon />}>
        This link doesn&apos;t include a name, so rules are matched once the download starts.
      </Line>
    );
  }
  if (preview.isError) {
    return (
      <Line icon={<TriangleAlertIcon className="text-warning" />}>
        <span className="text-warning">{errorMessage(preview.error)}</span>
      </Line>
    );
  }
  if (!preview.data || debouncedName !== name) {
    return <Line icon={<Loader2Icon className="animate-spin" />}>Checking your rules…</Line>;
  }
  const { rule_id, new_name, final_path } = preview.data;
  if (!final_path) {
    return (
      <Line icon={<InfoIcon />}>
        No rule matches <span className="font-mono text-foreground">{name}</span>. It will stay in
        the download folder.
      </Line>
    );
  }
  const rule = rules.data?.find((r) => r.id === rule_id);
  const folder = final_path.slice(0, final_path.length - new_name.length - 1) || "/";
  return (
    <div className="space-y-2">
      <Line icon={<ArrowRightIcon className="text-primary" />}>
        Matches rule <span className="font-medium text-foreground">{rule?.name ?? "—"}</span>
      </Line>
      <NameDiff before={name} after={new_name} className="pl-5.5" />
      <Line icon={<FolderIcon />}>
        <span className="font-mono">{folder}</span>
      </Line>
    </div>
  );
}
