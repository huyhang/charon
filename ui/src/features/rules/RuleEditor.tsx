import { Loader2Icon, Trash2Icon } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { errorMessage, isApiError } from "@/api/errors";
import { useDeleteRule, useSaveRule } from "@/api/queries";
import type { Rule, RuleSpec } from "@/api/types";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { fieldErrors } from "@/lib/fieldErrors";
import { clearStaleErrors, draftProblems, fieldForCode } from "@/lib/ruleDraft";
import { toSpec } from "@/lib/rules";
import { DestinationPicker } from "./DestinationPicker";
import { errorProps, FormField } from "./FormField";
import { StepBuilder } from "./StepBuilder";
import { TestBench } from "./TestBench";

export type EditorTarget = { mode: "create"; spec: RuleSpec } | { mode: "edit"; rule: Rule };

function errorsFrom(error: unknown): Record<string, string> {
  if (!isApiError(error)) return { _: errorMessage(error) };
  if (error.details) return fieldErrors(error.details);
  const field = fieldForCode(error.code);
  return { [field ?? "_"]: error.message };
}

const PATTERN_HINTS = {
  glob: (
    <>
      Must match the whole name. <code className="font-mono">*</code> is anything,{" "}
      <code className="font-mono">?</code> one character.
    </>
  ),
  regex: "Python regex, matched anywhere in the name.",
};

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-sm font-medium">{title}</h3>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>
      {children}
    </section>
  );
}

function EditorForm({ target, onDone }: { target: EditorTarget; onDone(): void }) {
  const [spec, setSpec] = useState<RuleSpec>(
    target.mode === "edit" ? toSpec(target.rule) : target.spec,
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [confirmDelete, setConfirmDelete] = useState(false);
  const save = useSaveRule();
  const remove = useDeleteRule();
  const problems = draftProblems(spec);
  const ruleId = target.mode === "edit" ? target.rule.id : undefined;
  const update = (patch: Partial<RuleSpec>) => {
    setSpec((prev) => ({ ...prev, ...patch }));
    setErrors((prev) => clearStaleErrors(prev, Object.keys(patch)));
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    setErrors({});
    save.mutate(
      { id: ruleId, spec },
      {
        onSuccess: (rule) => {
          toast.success(ruleId ? "Rule saved" : "Rule created", { description: rule.name });
          onDone();
        },
        onError: (error) => setErrors(errorsFrom(error)),
      },
    );
  };

  const onDelete = () =>
    remove.mutate(ruleId!, {
      onSuccess: () => {
        toast("Rule deleted", { description: spec.name });
        onDone();
      },
      onError: (error) =>
        toast.error("Couldn't delete the rule", { description: errorMessage(error) }),
    });

  return (
    <form onSubmit={onSubmit} className="flex min-h-0 flex-1 flex-col" noValidate>
      <SheetBody className="space-y-7">
        <Section title="Basics">
          <FormField id="rule-name" label="Name" error={errors.name}>
            <Input
              id="rule-name"
              value={spec.name}
              onChange={(e) => update({ name: e.target.value })}
              placeholder="TV shows"
              autoFocus
              {...errorProps("rule-name", errors.name)}
            />
          </FormField>
          <label className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5">
            <span className="text-sm">
              Enabled
              <span className="block text-xs text-muted-foreground">
                Disabled rules are skipped when matching.
              </span>
            </span>
            <Switch
              checked={spec.enabled}
              onCheckedChange={(enabled) => update({ enabled })}
              aria-label="Enabled"
            />
          </label>
        </Section>

        <Section title="Match" description="Which downloads this rule applies to.">
          <Segmented
            label="Pattern type"
            value={spec.match_type}
            onChange={(match_type) => update({ match_type })}
            options={[
              { value: "glob", label: "Glob" },
              { value: "regex", label: "Regex" },
            ]}
          />
          <FormField
            id="rule-pattern"
            label="Pattern"
            error={errors.pattern}
            hint={PATTERN_HINTS[spec.match_type]}
          >
            <Input
              id="rule-pattern"
              value={spec.pattern}
              onChange={(e) => update({ pattern: e.target.value })}
              placeholder={spec.match_type === "glob" ? "*S0?E*" : "S\\d+E\\d+"}
              {...errorProps("rule-pattern", errors.pattern)}
              spellCheck={false}
              className="font-mono text-xs"
            />
          </FormField>
        </Section>

        <Section title="Rename" description="Steps run in order on the file or folder name.">
          <StepBuilder
            spec={spec}
            onChange={(next) => update({ steps: next.steps })}
            errors={errors}
          />
        </Section>

        <Section title="Destination" description="Where matching downloads are moved.">
          <DestinationPicker
            id="rule-destination"
            value={spec.destination}
            onChange={(destination) => update({ destination })}
            error={errors.destination}
          />
        </Section>

        <TestBench spec={spec} />

        {errors._ && (
          <p
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
          >
            {errors._}
          </p>
        )}
      </SheetBody>
      <SheetFooter className="justify-between">
        {ruleId ? (
          <Button
            type="button"
            variant="ghost"
            className="text-destructive hover:text-destructive"
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2Icon /> Delete
          </Button>
        ) : (
          <span />
        )}
        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" onClick={onDone}>
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={problems.length > 0 || save.isPending}
            title={problems[0]}
          >
            {save.isPending && <Loader2Icon className="animate-spin" />}
            {ruleId ? "Save rule" : "Create rule"}
          </Button>
        </div>
      </SheetFooter>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this rule?"
        description={`"${spec.name}" will no longer match new downloads. Finished downloads stay where they are.`}
        confirmLabel="Delete rule"
        onConfirm={onDelete}
        destructive
      />
    </form>
  );
}

interface RuleEditorProps {
  target: EditorTarget | null;
  onClose(): void;
}

export function RuleEditor({ target, onClose }: RuleEditorProps) {
  return (
    <Sheet open={target !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>{target?.mode === "edit" ? "Edit rule" : "New rule"}</SheetTitle>
          <SheetDescription>
            Match downloads by name, rename them, and file them away.
          </SheetDescription>
        </SheetHeader>
        {target && (
          <EditorForm
            key={target.mode === "edit" ? target.rule.id : "new"}
            target={target}
            onDone={onClose}
          />
        )}
      </SheetContent>
    </Sheet>
  );
}
