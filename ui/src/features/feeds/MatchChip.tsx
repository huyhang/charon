import { ArrowRightIcon, CircleDashedIcon, TriangleAlertIcon } from "lucide-react";
import type { FeedItem } from "@/api/types";
import { Badge } from "@/components/ui/badge";

/** Which rule would file the item: its name, "No rule", or a warning when the rule breaks. */
export function MatchChip({ item }: { item: Pick<FeedItem, "match" | "match_error"> }) {
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
    <Badge tone="progress" title={`Filed by ${item.match.rule_name} into ${item.match.final_path}`}>
      <ArrowRightIcon /> {item.match.rule_name}
    </Badge>
  );
}
