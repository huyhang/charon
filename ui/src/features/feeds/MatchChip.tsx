import { ArrowRightIcon, CircleDashedIcon, TriangleAlertIcon } from "lucide-react";
import type { FeedItem } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";

interface MatchChipProps {
  item: Pick<FeedItem, "match" | "match_error">;
  className?: string;
}

/**
 * Which rule would file the item: its name, "No rule", or a warning when the rule breaks.
 * A long rule name is cut short (it's in full on hover) rather than crowding out the item.
 */
export function MatchChip({ item, className }: MatchChipProps) {
  if (item.match_error) {
    return (
      <Badge tone="warning" title={item.match_error.message}>
        <TriangleAlertIcon /> Rule problem
      </Badge>
    );
  }
  if (!item.match) {
    return (
      <Badge tone="muted">
        <CircleDashedIcon /> No rule
      </Badge>
    );
  }
  return (
    <Badge
      tone="progress"
      title={`Filed by ${item.match.rule_name} into ${item.match.final_path}`}
      className={cn("max-w-64 min-w-0", className)}
    >
      <ArrowRightIcon /> <span className="truncate">{item.match.rule_name}</span>
    </Badge>
  );
}
