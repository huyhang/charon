import type { FeedItem } from "@/api/types";
import { groupByDay, newDividerBefore } from "@/lib/feeds";
import { FeedItemRow } from "./FeedItemRow";
import type { useInboxState } from "./useInboxState";

interface FeedListProps {
  items: FeedItem[];
  state: ReturnType<typeof useInboxState>;
  /** Items whose download is on its way. */
  pendingHashes: ReadonlySet<string>;
  onDownload(item: FeedItem, ruleId?: string | null): void;
}

function SeenDivider() {
  return (
    <li role="separator" aria-label="Seen before" className="flex items-center gap-3 py-1">
      <span className="h-px flex-1 bg-primary/30" />
      <span className="text-[11px] font-medium tracking-wide text-primary uppercase">
        Seen before
      </span>
      <span className="h-px flex-1 bg-primary/30" />
    </li>
  );
}

/** Items grouped by day, with a line between what's new and what was already seen. */
export function FeedList({ items, state, pendingHashes, onDownload }: FeedListProps) {
  const divider = newDividerBefore(items);
  return (
    <div className="space-y-6">
      {groupByDay(items).map((group) => (
        <section key={group.key} aria-label={group.label} className="space-y-2">
          <h2 className="sticky top-14 z-10 -mx-1 bg-background/80 px-1 py-1 text-xs font-medium tracking-wide text-muted-foreground uppercase backdrop-blur md:top-0">
            {group.label}
          </h2>
          <ul className="space-y-2">
            {group.items.map((item) => (
              <FeedRowWithDivider
                key={item.info_hash}
                item={item}
                divider={divider === item.info_hash}
                state={state}
                pending={pendingHashes.has(item.info_hash)}
                onDownload={(ruleId) => onDownload(item, ruleId)}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function FeedRowWithDivider({
  item,
  divider,
  state,
  pending,
  onDownload,
}: {
  item: FeedItem;
  divider: boolean;
  state: FeedListProps["state"];
  pending: boolean;
  onDownload(ruleId?: string | null): void;
}) {
  const hash = item.info_hash;
  return (
    <>
      {divider && <SeenDivider />}
      <FeedItemRow
        item={item}
        tabStop={state.tabStopHash === hash}
        expanded={state.expanded.has(hash)}
        selected={state.isSelected(hash)}
        pending={pending}
        onToggleExpanded={() => state.toggleExpanded(hash)}
        onToggleSelected={() => state.toggleSelected(hash)}
        onDownload={onDownload}
        onFocus={() => state.setActiveHash(hash)}
      />
    </>
  );
}
