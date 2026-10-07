import { ChevronDownIcon, DownloadIcon, ExternalLinkIcon, Loader2Icon } from "lucide-react";
import { Link } from "react-router";
import { useRules } from "@/api/queries";
import type { FeedItem } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { canDownload, jobBadge } from "@/lib/feeds";

interface ItemActionsProps {
  item: FeedItem;
  pending: boolean;
  onDownload(ruleId?: string | null): void;
}

/** Download (optionally with a chosen rule), or the download's state once it's in Charon. */
export function ItemActions({ item, pending, onDownload }: ItemActionsProps) {
  const rules = useRules();
  if (!canDownload(item) && item.job) {
    const { label, tone } = jobBadge(item.job);
    return (
      <div className="flex items-center gap-1.5" onClick={(event) => event.stopPropagation()}>
        <Badge tone={tone} title="This torrent is already in Charon">
          {label}
        </Badge>
        <Button asChild size="sm" variant="ghost" className="h-7 px-2">
          <Link to={`/downloads/${item.job.id}`} aria-label={`Open the download of ${item.name}`}>
            <ExternalLinkIcon />
          </Link>
        </Button>
      </div>
    );
  }
  return (
    <div className="flex items-center" onClick={(event) => event.stopPropagation()}>
      <Button
        size="sm"
        className="h-7 rounded-r-none px-2.5"
        disabled={pending}
        onClick={() => onDownload(null)}
        aria-label={`Download ${item.name}`}
      >
        {pending ? <Loader2Icon className="animate-spin" /> : <DownloadIcon />}
        <span className="hidden sm:inline">Download</span>
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            size="sm"
            className="h-7 rounded-l-none border-l border-primary-foreground/20 px-1.5"
            disabled={pending}
            aria-label={`Download ${item.name} with a rule`}
          >
            <ChevronDownIcon />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>Download with rule</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {rules.data?.length ? (
            rules.data.map((rule) => (
              <DropdownMenuItem key={rule.id} onSelect={() => onDownload(rule.id)}>
                {rule.name}
              </DropdownMenuItem>
            ))
          ) : (
            <DropdownMenuItem disabled>No rules yet</DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
