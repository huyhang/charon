import type { ReactNode } from "react";
import { Label } from "@/components/ui/label";

interface FormFieldProps {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
}

/** Marks an input invalid and points it at its error, so screen readers announce the error. */
export function errorProps(id: string, error: string | null | undefined) {
  return error
    ? { "aria-invalid": true, "aria-describedby": `${id}-error` }
    : { "aria-invalid": false };
}

/** A labelled input with its error (id `${id}-error`, see `errorProps`) or hint below it. */
export function FormField({ id, label, hint, error, children }: FormFieldProps) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : (
        hint && <p className="text-xs text-muted-foreground">{hint}</p>
      )}
    </div>
  );
}
