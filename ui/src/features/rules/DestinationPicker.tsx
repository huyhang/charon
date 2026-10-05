import {
  ChevronRightIcon,
  FolderIcon,
  FolderOpenIcon,
  FolderPlusIcon,
  Loader2Icon,
} from "lucide-react";
import { useState } from "react";
import { isApiError } from "@/api/errors";
import { useDestinationRoots, useFolders } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { cn } from "@/lib/cn";
import { breadcrumbs, normalizePath, rootOf } from "@/lib/paths";
import { errorProps } from "./FormField";

interface DestinationPickerProps {
  id: string;
  value: string;
  onChange(value: string): void;
  error?: string;
}

type Status = { tone: "muted" | "success" | "warning" | "danger"; text: string };

function useDestinationStatus(value: string, roots: string[] | undefined): Status | null {
  const path = useDebouncedValue(normalizePath(value), 300);
  const root = roots ? rootOf(path, roots) : null;
  const folder = useFolders(path.startsWith("/") && root ? path : null);
  if (!path) return null;
  if (!path.startsWith("/"))
    return { tone: "danger", text: "Use an absolute path, starting with /." };
  if (roots && !root)
    return { tone: "danger", text: `Must be inside ${roots.join(" or ") || "a configured root"}.` };
  if (folder.isSuccess) return { tone: "success", text: "Folder exists." };
  if (isApiError(folder.error, 404))
    return { tone: "warning", text: "New folder: it will be created on the first move." };
  return null;
}

const TONES = {
  muted: "text-muted-foreground",
  success: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
};

function FolderBrowser({
  start,
  roots,
  onPick,
}: {
  start: string;
  roots: string[];
  onPick(path: string): void;
}) {
  const [path, setPath] = useState<string | null>(start || null);
  const folders = useFolders(path);
  const root = path ? rootOf(path, roots) : null;

  if (!path || !root) {
    return (
      <div className="p-1.5">
        <p className="px-2 py-1.5 text-xs text-muted-foreground">Allowed locations</p>
        {roots.length === 0 && (
          <p className="px-2 py-3 text-xs text-muted-foreground">
            No roots configured. Set <code className="font-mono">CHARON_RULE_ROOTS</code>.
          </p>
        )}
        {roots.map((r) => (
          <button
            key={r}
            type="button"
            onClick={() => setPath(r)}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left font-mono text-sm hover:bg-accent"
          >
            <FolderIcon className="size-4 text-primary" /> {r}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="flex max-h-80 flex-col">
      <nav
        aria-label="Folder path"
        className="flex flex-wrap items-center gap-0.5 border-b px-2 py-2 font-mono text-xs"
      >
        {roots.length > 1 && (
          <button
            type="button"
            className="rounded px-1 py-0.5 text-muted-foreground hover:bg-accent"
            onClick={() => setPath(null)}
          >
            roots
          </button>
        )}
        {breadcrumbs(path, root).map((crumb, index) => (
          <span key={crumb.path} className="flex items-center gap-0.5">
            {(index > 0 || roots.length > 1) && (
              <ChevronRightIcon className="size-3 text-muted-foreground" />
            )}
            <button
              type="button"
              onClick={() => setPath(crumb.path)}
              className="rounded px-1 py-0.5 hover:bg-accent"
            >
              {crumb.name}
            </button>
          </span>
        ))}
      </nav>
      <div className="flex-1 overflow-y-auto p-1.5">
        {folders.isPending && (
          <p className="flex items-center gap-2 px-2 py-3 text-xs text-muted-foreground">
            <Loader2Icon className="size-3.5 animate-spin" /> Loading…
          </p>
        )}
        {folders.isError && (
          <p className="px-2 py-3 text-xs text-muted-foreground">
            {isApiError(folders.error, 404)
              ? "This folder doesn't exist yet."
              : String(folders.error.message)}
          </p>
        )}
        {folders.data?.folders.length === 0 && (
          <p className="px-2 py-3 text-xs text-muted-foreground">No subfolders.</p>
        )}
        {folders.data?.folders.map((folder) => (
          <button
            key={folder.path}
            type="button"
            onClick={() => setPath(folder.path)}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
          >
            <FolderIcon className="size-4 text-muted-foreground" />
            <span className="flex-1 truncate">{folder.name}</span>
            <ChevronRightIcon className="size-3.5 text-muted-foreground" />
          </button>
        ))}
      </div>
      <div className="flex items-center justify-between gap-2 border-t p-2">
        <span className="truncate font-mono text-xs text-muted-foreground">{path}</span>
        <Button type="button" size="sm" onClick={() => onPick(path)}>
          Use this folder
        </Button>
      </div>
    </div>
  );
}

/** A path field with a folder browser limited to the configured roots. */
export function DestinationPicker({ id, value, onChange, error }: DestinationPickerProps) {
  const [open, setOpen] = useState(false);
  const roots = useDestinationRoots();
  const status = useDestinationStatus(value, roots.data);
  const startAt = roots.data && rootOf(value, roots.data) ? normalizePath(value) : "";

  return (
    <div className="space-y-1.5">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverAnchor asChild>
          <div className="flex gap-2">
            <Input
              id={id}
              value={value}
              onChange={(event) => onChange(event.target.value)}
              aria-label="Destination"
              placeholder={roots.data?.[0] ? `${roots.data[0]}/tv` : "/library/tv"}
              {...errorProps(id, error)}
              spellCheck={false}
              className="font-mono text-xs"
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
            >
              <FolderOpenIcon /> Browse
            </Button>
          </div>
        </PopoverAnchor>
        <PopoverContent align="end" className="w-[min(26rem,calc(100vw-2rem))] p-0">
          <FolderBrowser
            key={String(open)}
            start={startAt}
            roots={roots.data ?? []}
            onPick={(path) => {
              onChange(path);
              setOpen(false);
            }}
          />
        </PopoverContent>
      </Popover>
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : (
        status && (
          <p className={cn("flex items-center gap-1.5 text-xs", TONES[status.tone])}>
            {status.tone === "warning" && <FolderPlusIcon className="size-3.5" />}
            {status.text}
          </p>
        )
      )}
    </div>
  );
}
