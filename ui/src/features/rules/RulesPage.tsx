import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { restrictToVerticalAxis } from "@dnd-kit/modifiers";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { PlusIcon, WorkflowIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { errorMessage } from "@/api/errors";
import { useDestinationRoots, useReorderRules, useRules, useSaveRule } from "@/api/queries";
import type { Rule } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { suggestRule } from "@/lib/feeds";
import { emptySpec, moveItem, nextPriority, toUpdate } from "@/lib/rules";
import { RuleEditor, type EditorTarget } from "./RuleEditor";
import { RuleRow } from "./RuleRow";

/**
 * Reads and clears `?new=` (open a new rule), with an optional `&sample=` name to start from.
 * Waits until `ready`, e.g. until the destination roots are known, so the draft can use them.
 */
function useNewRuleRequest(open: (sample: string | null) => void, ready: boolean): void {
  const [params, setParams] = useSearchParams();
  const requested = params.get("new") !== null;
  const sample = params.get("sample");
  useEffect(() => {
    if (!requested || !ready) return;
    open(sample);
    setParams(
      (prev) => {
        prev.delete("new");
        prev.delete("sample");
        return prev;
      },
      { replace: true },
    );
  }, [requested, sample, ready, open, setParams]);
}

export function RulesPage() {
  const rules = useRules();
  const roots = useDestinationRoots();
  const reorder = useReorderRules();
  const save = useSaveRule();
  const [target, setTarget] = useState<EditorTarget | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const list = rules.data ?? [];

  const firstRoot = roots.data?.[0];
  const openNew = useCallback(
    (sample: string | null = null) => {
      const spec = emptySpec(nextPriority(list), firstRoot ? `${firstRoot}/` : "");
      setTarget({
        mode: "create",
        spec: sample ? { ...spec, ...suggestRule(sample) } : spec,
        sample: sample ?? undefined,
      });
    },
    [list, firstRoot],
  );
  useNewRuleRequest(openNew, !roots.isPending && !rules.isPending);

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const from = list.findIndex((r) => r.id === active.id);
    const to = list.findIndex((r) => r.id === over.id);
    reorder.mutate(moveItem(list, from, to), {
      onError: (error) =>
        toast.error("Couldn't save the new order", { description: errorMessage(error) }),
    });
  };

  const onToggle = (rule: Rule, enabled: boolean) =>
    save.mutate(
      { id: rule.id, spec: toUpdate(rule, { enabled }) },
      {
        onSuccess: () => toast(`${rule.name} ${enabled ? "enabled" : "disabled"}`),
        onError: (error) =>
          toast.error("Couldn't update the rule", { description: errorMessage(error) }),
      },
    );

  return (
    <div className="space-y-8">
      <PageHeader
        title="Rules"
        description="Rules are tried top to bottom. The first one whose pattern matches renames and files the download. Drag to reorder."
        actions={
          <Button onClick={() => openNew()}>
            <PlusIcon /> New rule
          </Button>
        }
      />
      {rules.isPending ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-[74px] rounded-xl" />
          ))}
        </div>
      ) : rules.isError ? (
        <ErrorState error={rules.error} onRetry={() => rules.refetch()} />
      ) : list.length === 0 ? (
        <EmptyState
          icon={WorkflowIcon}
          title="No rules yet"
          description="Without rules, downloads stay in the download folder. Create one to rename and file them automatically."
          action={
            <Button onClick={() => openNew()}>
              <PlusIcon /> Create your first rule
            </Button>
          }
        />
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          modifiers={[restrictToVerticalAxis]}
          onDragEnd={onDragEnd}
        >
          <SortableContext items={list.map((r) => r.id)} strategy={verticalListSortingStrategy}>
            <ol className="space-y-2" aria-label="Rules in priority order">
              {list.map((rule, index) => (
                <RuleRow
                  key={rule.id}
                  rule={rule}
                  position={index + 1}
                  onOpen={(r) => setTarget({ mode: "edit", rule: r })}
                  onToggle={onToggle}
                />
              ))}
            </ol>
          </SortableContext>
        </DndContext>
      )}
      <RuleEditor target={target} onClose={() => setTarget(null)} />
    </div>
  );
}
