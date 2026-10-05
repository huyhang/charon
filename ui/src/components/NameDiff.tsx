import { diffNames, type Segment } from "@/lib/diff";
import { cn } from "@/lib/cn";

function Segments({ segments, tone }: { segments: Segment[]; tone: "removed" | "added" }) {
  return (
    <>
      {segments.map((segment, index) =>
        segment.changed ? (
          <mark
            key={index}
            className={cn(
              "rounded-[3px] px-px",
              tone === "removed"
                ? "bg-destructive/15 text-destructive line-through decoration-destructive/50"
                : "bg-success/15 text-success",
            )}
          >
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </>
  );
}

/** Before and after a rename, with the changed parts highlighted. */
export function NameDiff({
  before,
  after,
  className,
}: {
  before: string;
  after: string;
  className?: string;
}) {
  const diff = diffNames(before, after);
  const unchanged = before === after;
  return (
    <div className={cn("space-y-1 font-mono text-xs break-all", className)}>
      {!unchanged && (
        <div className="text-muted-foreground" aria-label="Original name">
          <Segments segments={diff.before} tone="removed" />
        </div>
      )}
      <div className="text-foreground" aria-label="New name">
        <Segments segments={diff.after} tone="added" />
      </div>
    </div>
  );
}
