import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ArrowRightIcon, FolderIcon, GripVerticalIcon } from "lucide-react";
import type { Rule } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/cn";

interface RuleRowProps {
  rule: Rule;
  position: number;
  onOpen(rule: Rule): void;
  onToggle(rule: Rule, enabled: boolean): void;
}

export function stepSummary(rule: Pick<Rule, "steps">): string {
  const count = rule.steps?.length ?? 0;
  if (count === 0) return "Keeps the name";
  return count === 1 ? "1 rename step" : `${count} rename steps`;
}

export function RuleRow({ rule, position, onOpen, onToggle }: RuleRowProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: rule.id,
  });

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "group flex items-center gap-3 rounded-xl border bg-card/70 p-3 pr-4 transition-colors hover:border-primary/30",
        isDragging && "z-10 border-primary/50 bg-card shadow-2xl",
        !rule.enabled && "opacity-60",
      )}
    >
      <button
        ref={setActivatorNodeRef}
        type="button"
        aria-label={`Reorder ${rule.name}`}
        className="cursor-grab touch-none rounded-md p-1 text-muted-foreground hover:bg-accent active:cursor-grabbing"
        {...attributes}
        {...listeners}
      >
        <GripVerticalIcon className="size-4" />
      </button>
      <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-muted text-xs font-semibold text-muted-foreground tabular-nums">
        {position}
      </span>
      <button
        type="button"
        onClick={() => onOpen(rule)}
        className="min-w-0 flex-1 space-y-1.5 text-left outline-none"
      >
        <div className="flex items-center gap-2">
          <span className="truncate font-medium">{rule.name}</span>
          <Badge tone={rule.match_type === "regex" ? "warning" : "neutral"}>
            {rule.match_type}
          </Badge>
        </div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <code className="max-w-[16rem] truncate rounded bg-muted px-1.5 py-0.5 font-mono text-foreground/80">
            {rule.pattern}
          </code>
          <ArrowRightIcon className="size-3" />
          <span>{stepSummary(rule)}</span>
          <ArrowRightIcon className="size-3" />
          <span className="flex min-w-0 items-center gap-1">
            <FolderIcon className="size-3 shrink-0" />
            <span className="truncate font-mono">{rule.destination}</span>
          </span>
        </div>
      </button>
      <Switch
        checked={rule.enabled}
        onCheckedChange={(enabled) => onToggle(rule, enabled)}
        aria-label={`Enable ${rule.name}`}
      />
    </li>
  );
}
