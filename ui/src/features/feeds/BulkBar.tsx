import { DownloadIcon, Loader2Icon, XIcon } from "lucide-react";
import { toast } from "sonner";
import { errorMessage } from "@/api/errors";
import { useDownloadFeedItems, type BulkDownloadResult } from "@/api/queries";
import { Button } from "@/components/ui/button";

interface BulkBarProps {
  selected: string[];
  onClear(): void;
  /** Keeps only these selected, e.g. the items that couldn't start, ready to try again. */
  onKeep(hashes: string[]): void;
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** What to tell people after a bulk download, leading with failures when nothing started. */
export function bulkSummary({ started, already, failed }: BulkDownloadResult) {
  const reason = failed.length ? errorMessage(failed[0]!.error) : null;
  if (failed.length && started + already === 0) {
    return {
      tone: "error" as const,
      title: `Couldn't start ${plural(failed.length, "download")}`,
      description: reason ?? undefined,
    };
  }
  const parts = [
    already && `${already} already in Charon`,
    failed.length && `${failed.length} couldn't start: ${reason}`,
  ].filter(Boolean);
  return {
    tone: failed.length ? ("warning" as const) : ("success" as const),
    title: `Started ${plural(started, "download")}`,
    description: parts.join(" · ") || undefined,
  };
}

/** What to do with the selected items. */
export function BulkBar({ selected, onClear, onKeep }: BulkBarProps) {
  const download = useDownloadFeedItems();
  if (selected.length === 0) return null;
  const onDownload = () =>
    download.mutate(selected, {
      onSuccess: (result) => {
        const { tone, title, description } = bulkSummary(result);
        toast[tone](title, { description });
        onKeep(result.failed.map((f) => f.infoHash));
      },
      onError: (error) =>
        toast.error("Couldn't start the downloads", { description: errorMessage(error) }),
    });
  return (
    <div
      role="toolbar"
      aria-label="Selected items"
      className="sticky top-16 z-20 flex animate-in items-center justify-between gap-3 rounded-xl border border-primary/30 bg-popover/95 px-4 py-2 shadow-lg backdrop-blur fade-in slide-in-from-top-1 md:top-4"
    >
      <span className="text-sm font-medium tabular-nums">{selected.length} selected</span>
      <div className="flex items-center gap-1.5">
        <Button size="sm" onClick={onDownload} disabled={download.isPending}>
          {download.isPending ? <Loader2Icon className="animate-spin" /> : <DownloadIcon />}
          Download {selected.length}
        </Button>
        <Button size="sm" variant="ghost" onClick={onClear} aria-label="Clear selection">
          <XIcon />
        </Button>
      </div>
    </div>
  );
}
