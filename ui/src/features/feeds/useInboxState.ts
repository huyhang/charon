import { useCallback, useMemo, useState } from "react";
import type { FeedItem } from "@/api/types";
import { canDownload } from "@/lib/feeds";

function toggled(set: ReadonlySet<string>, key: string): Set<string> {
  const next = new Set(set);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}

/** Which items are expanded, selected, and under the keyboard cursor. */
export function useInboxState(items: readonly FeedItem[]) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [activeHash, setActiveHash] = useState<string | null>(null);

  const selectable = useMemo(() => items.filter(canDownload).map((i) => i.info_hash), [items]);
  // Selections of items no longer listed, or no longer downloadable, don't count.
  const selectedHashes = selectable.filter((hash) => selected.has(hash));
  // -1 until the user picks a row (j/k, a click, Tab): until then d, x and Enter do nothing.
  const cursor = items.findIndex((item) => item.info_hash === activeHash);
  const activeItem = cursor === -1 ? undefined : items[cursor];

  const toggleExpanded = useCallback((hash: string) => setExpanded((s) => toggled(s, hash)), []);
  const toggleSelected = useCallback((hash: string) => setSelected((s) => toggled(s, hash)), []);
  const selectAll = useCallback(
    (all: boolean) => setSelected(all ? new Set(selectable) : new Set()),
    [selectable],
  );
  const clearSelection = useCallback(() => setSelected(new Set()), []);
  /** Narrows the selection to `hashes`, e.g. the items whose download failed. */
  const keepSelected = useCallback(
    (hashes: readonly string[]) => setSelected((s) => new Set(hashes.filter((h) => s.has(h)))),
    [],
  );
  /** Moves the cursor by `step`; the first move lands on the first (or last) item. */
  const move = (step: number) => {
    const target = cursor === -1 ? (step > 0 ? 0 : items.length - 1) : cursor + step;
    const next = items[Math.min(Math.max(target, 0), items.length - 1)];
    if (next) setActiveHash(next.info_hash);
    return next;
  };

  return {
    expanded,
    selectedHashes,
    activeItem,
    // The row Tab lands on: the active one, else the first, so the list stays reachable.
    tabStopHash: activeItem?.info_hash ?? items[0]?.info_hash ?? null,
    allSelected:
      selectedHashes.length === 0
        ? false
        : selectedHashes.length === selectable.length
          ? true
          : ("indeterminate" as const),
    canSelect: selectable.length > 0,
    isSelected: (hash: string) => selected.has(hash) && selectable.includes(hash),
    setActiveHash,
    toggleExpanded,
    toggleSelected,
    selectAll,
    clearSelection,
    keepSelected,
    move,
  };
}
