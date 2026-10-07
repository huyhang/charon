import { SearchIcon } from "lucide-react";
import type { RefObject } from "react";
import type { MatchFilter } from "@/api/types";
import { Checkbox } from "@/components/ui/checkbox";
import { Kbd } from "@/components/ui/kbd";
import { Segmented } from "@/components/ui/segmented";
import { MATCH_FILTERS } from "@/lib/feeds";

interface InboxToolbarProps {
  match: MatchFilter;
  onMatch(match: MatchFilter): void;
  search: string;
  onSearch(search: string): void;
  searchRef: RefObject<HTMLInputElement | null>;
  /** True, false, or "indeterminate" when only some items are selected. */
  allSelected: boolean | "indeterminate";
  onSelectAll(selected: boolean): void;
  selectable: boolean;
}

export function InboxToolbar({
  match,
  onMatch,
  search,
  onSearch,
  searchRef,
  allSelected,
  onSelectAll,
  selectable,
}: InboxToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Checkbox
        checked={allSelected}
        onCheckedChange={(checked) => onSelectAll(checked === true)}
        disabled={!selectable}
        aria-label="Select everything that can be downloaded"
        className="ml-3 sm:ml-4"
      />
      <Segmented
        label="Which items"
        value={match}
        onChange={onMatch}
        options={MATCH_FILTERS.map((f) => ({ value: f.id, label: f.label }))}
      />
      <label className="flex h-8 min-w-48 flex-1 items-center gap-2 rounded-lg border bg-background/50 px-2.5 transition focus-within:border-primary/50 focus-within:ring-[3px] focus-within:ring-ring">
        <SearchIcon className="size-3.5 text-muted-foreground" />
        <input
          ref={searchRef}
          aria-label="Search items"
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          onKeyDown={(event) => event.key === "Escape" && event.currentTarget.blur()}
          placeholder="Search names"
          spellCheck={false}
          className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
        <Kbd className="hidden sm:inline-flex">/</Kbd>
      </label>
    </div>
  );
}
