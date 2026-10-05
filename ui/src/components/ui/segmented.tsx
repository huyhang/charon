import { cn } from "@/lib/cn";

interface SegmentedProps<T extends string> {
  value: T;
  onChange(value: T): void;
  options: { value: T; label: string }[];
  label: string;
}

/** A small single-choice switch, e.g. glob / regex. */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: SegmentedProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex rounded-lg border bg-muted/40 p-0.5"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "h-7 rounded-md px-3 text-xs font-medium text-muted-foreground transition outline-none focus-visible:ring-[3px] focus-visible:ring-ring",
            value === option.value && "bg-background text-foreground shadow-sm",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
