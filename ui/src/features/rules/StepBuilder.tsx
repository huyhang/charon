import { ArrowDownIcon, ArrowUpIcon, PlusIcon, Trash2Icon } from "lucide-react";
import type { ReactNode } from "react";
import type { RenameStep, RuleSpec } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { addStep, moveStep, removeStep, updateStep } from "@/lib/ruleDraft";
import { errorProps } from "./FormField";

interface StepBuilderProps {
  spec: RuleSpec;
  onChange(spec: RuleSpec): void;
  errors: Record<string, string>;
  /** More ways to add steps, shown beside "Add step". */
  actions?: ReactNode;
}

const OPS: { value: RenameStep["op"]; label: string }[] = [
  { value: "replace", label: "Replace text" },
  { value: "regex_replace", label: "Replace regex" },
];

export function StepBuilder({ spec, onChange, errors, actions }: StepBuilderProps) {
  const steps = spec.steps ?? [];
  return (
    <div className="space-y-2">
      {steps.length === 0 && (
        <p className="rounded-lg border border-dashed px-3 py-3 text-xs text-muted-foreground">
          No rename steps: the name is kept as is.
        </p>
      )}
      <ol className="space-y-2">
        {steps.map((step, index) => {
          const findError = errors[`steps.${index}.find`] ?? errors[`steps.${index}`];
          const replaceError = errors[`steps.${index}.replace`];
          return (
            <li key={index} className="space-y-2 rounded-lg border bg-background/30 p-2.5">
              <div className="flex items-center gap-2">
                <span className="flex size-5 items-center justify-center rounded-full bg-muted text-[10px] font-semibold text-muted-foreground">
                  {index + 1}
                </span>
                <Select
                  value={step.op}
                  onValueChange={(op) =>
                    onChange(updateStep(spec, index, { op: op as RenameStep["op"] }))
                  }
                >
                  <SelectTrigger className="h-8 w-40" aria-label={`Step ${index + 1} type`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {OPS.map((op) => (
                      <SelectItem key={op.value} value={op.value}>
                        {op.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <div className="ml-auto flex">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Move step ${index + 1} up`}
                    disabled={index === 0}
                    onClick={() => onChange(moveStep(spec, index, index - 1))}
                  >
                    <ArrowUpIcon />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Move step ${index + 1} down`}
                    disabled={index === steps.length - 1}
                    onClick={() => onChange(moveStep(spec, index, index + 1))}
                  >
                    <ArrowDownIcon />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove step ${index + 1}`}
                    onClick={() => onChange(removeStep(spec, index))}
                  >
                    <Trash2Icon />
                  </Button>
                </div>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <Input
                  aria-label={`Step ${index + 1} find`}
                  placeholder={
                    step.op === "regex_replace" ? "Regex, e.g. \\.1080p" : "Find, e.g. XYZ"
                  }
                  value={step.find}
                  onChange={(event) =>
                    onChange(updateStep(spec, index, { find: event.target.value }))
                  }
                  {...errorProps(`step-${index}`, findError)}
                  className="h-8 font-mono text-xs"
                />
                <Input
                  aria-label={`Step ${index + 1} replace`}
                  placeholder={
                    step.op === "regex_replace"
                      ? "Replacement, e.g. \\1 (blank removes)"
                      : "Replace with (blank removes)"
                  }
                  value={step.replace}
                  onChange={(event) =>
                    onChange(updateStep(spec, index, { replace: event.target.value }))
                  }
                  {...errorProps(`step-${index}`, replaceError)}
                  className="h-8 font-mono text-xs"
                />
              </div>
              {(findError || replaceError) && (
                <p id={`step-${index}-error`} role="alert" className="text-xs text-destructive">
                  {findError ?? replaceError}
                </p>
              )}
            </li>
          );
        })}
      </ol>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => onChange(addStep(spec))}>
          <PlusIcon /> Add step
        </Button>
        {actions}
      </div>
    </div>
  );
}
