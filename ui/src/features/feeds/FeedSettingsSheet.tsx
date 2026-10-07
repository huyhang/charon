import { EyeIcon, Loader2Icon, RefreshCwIcon, Trash2Icon, TriangleAlertIcon } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/api/errors";
import { useDeleteFeed, useRefreshFeed, useRevealFeedUrl, useUpdateFeed } from "@/api/queries";
import type { Feed } from "@/api/types";
import { usePrincipal } from "@/auth/AuthProvider";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { cn } from "@/lib/cn";
import { feedHealth, formatInterval, HEALTH_META, REFRESH_CHOICES } from "@/lib/feeds";
import { formatDateTime, formatRelative } from "@/lib/format";

function Toggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: ReactNode;
  checked: boolean;
  onChange(checked: boolean): void;
}) {
  return (
    <label className="flex items-start justify-between gap-3 rounded-lg border px-3 py-2.5">
      <span className="text-sm">
        {label}
        <span className="block text-xs text-muted-foreground">{description}</span>
      </span>
      <Switch checked={checked} onCheckedChange={onChange} aria-label={label} />
    </label>
  );
}

/** How the feed is doing, with a way to check it right now. */
function FeedStatus({ feed }: { feed: Feed }) {
  const refresh = useRefreshFeed();
  const { label, dot } = HEALTH_META[feedHealth(feed)];
  const onRefresh = () =>
    refresh.mutate(feed.id, {
      onSuccess: (checked) =>
        checked.last_error
          ? toast.error(`${checked.name} can't be read`, {
              description: checked.last_error.message,
            })
          : toast.success(`${checked.name} is up to date`),
      onError: (error) => toast.error("Couldn't refresh", { description: errorMessage(error) }),
    });
  return (
    <section className="space-y-3 rounded-xl border bg-card p-4" aria-label="Status">
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm font-medium">
          <span className={cn("size-2 rounded-full", dot)} /> {label}
        </p>
        <Button size="sm" variant="outline" onClick={onRefresh} disabled={refresh.isPending}>
          <RefreshCwIcon className={cn(refresh.isPending && "animate-spin")} /> Refresh now
        </Button>
      </div>
      <dl className="grid grid-cols-[7rem_1fr] gap-y-1 text-xs">
        <dt className="text-muted-foreground">Last checked</dt>
        <dd title={formatDateTime(feed.last_checked_at)}>
          {feed.last_checked_at ? formatRelative(feed.last_checked_at) : "Never"}
        </dd>
        <dt className="text-muted-foreground">Next check</dt>
        <dd>{feed.next_check_at ? formatDateTime(feed.next_check_at) : "Paused"}</dd>
      </dl>
      {feed.last_error && (
        <div role="alert" className="space-y-1 text-xs">
          <p className="flex items-start gap-2 text-destructive">
            <TriangleAlertIcon className="mt-px size-3.5 shrink-0" /> {feed.last_error.message}
          </p>
          {feed.last_error.hint && (
            <p className="pl-5.5 text-muted-foreground">{feed.last_error.hint}</p>
          )}
        </div>
      )}
    </section>
  );
}

/** The masked address; admins can reveal the whole thing and change it. */
function AddressField({
  feed,
  value,
  onChange,
}: {
  feed: Feed;
  value: string | null;
  onChange(url: string): void;
}) {
  const principal = usePrincipal();
  const reveal = useRevealFeedUrl();
  const isAdmin = principal.role === "admin";
  const onReveal = () =>
    reveal.mutate(feed.id, {
      onSuccess: onChange,
      onError: (error) =>
        toast.error("Couldn't reveal the address", { description: errorMessage(error) }),
    });
  return (
    <div className="space-y-1.5">
      <Label htmlFor="feed-settings-url">Address</Label>
      {value === null ? (
        <div className="flex items-center gap-2">
          <code
            id="feed-settings-url"
            className="min-w-0 flex-1 truncate rounded-lg border bg-muted/40 px-3 py-2 font-mono text-xs"
          >
            {feed.url}
          </code>
          {isAdmin && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onReveal}
              disabled={reveal.isPending}
            >
              <EyeIcon /> Reveal
            </Button>
          )}
        </div>
      ) : (
        // Only shown once revealed: focus moves here, ready for a new address to be pasted.
        <Input
          id="feed-settings-url"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          spellCheck={false}
          autoFocus
          className="font-mono text-xs"
        />
      )}
      <p className="text-xs text-muted-foreground">
        {value !== null
          ? "A new address is fetched on the feed's next check."
          : isAdmin
            ? "Passkeys and tokens are hidden. Reveal the address to see or change it."
            : "Passkeys and tokens are hidden. Only admins can see or change the address."}
      </p>
    </div>
  );
}

function SettingsForm({ feed, onDone }: { feed: Feed; onDone(): void }) {
  const [name, setName] = useState(feed.name);
  const [url, setUrl] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(feed.enabled);
  const [refreshMinutes, setRefreshMinutes] = useState(feed.refresh_minutes);
  const [autoDownload, setAutoDownload] = useState(feed.auto_download);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const update = useUpdateFeed();
  const remove = useDeleteFeed();
  const choices = [...new Set([...REFRESH_CHOICES, feed.refresh_minutes])].sort((a, b) => a - b);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const changes = {
      name: name.trim(),
      url,
      enabled,
      refresh_minutes: refreshMinutes,
      auto_download: autoDownload,
    };
    update.mutate(
      { id: feed.id, changes },
      {
        onSuccess: (saved) => {
          toast.success("Feed saved", { description: saved.name });
          onDone();
        },
        onError: (error) =>
          toast.error("Couldn't save the feed", { description: errorMessage(error) }),
      },
    );
  };

  const onDelete = () =>
    remove.mutate(feed.id, {
      onSuccess: () => {
        toast("Unsubscribed", { description: feed.name });
        onDone();
      },
      onError: (error) =>
        toast.error("Couldn't remove the feed", { description: errorMessage(error) }),
    });

  return (
    <form onSubmit={onSubmit} className="flex min-h-0 flex-1 flex-col" noValidate>
      <SheetBody className="space-y-6">
        <FeedStatus feed={feed} />
        <div className="space-y-1.5">
          <Label htmlFor="feed-settings-name">Name</Label>
          <Input
            id="feed-settings-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={100}
          />
        </div>
        <AddressField feed={feed} value={url} onChange={setUrl} />
        <div className="space-y-1.5">
          <Label htmlFor="feed-settings-interval">Check every</Label>
          <Select
            value={String(refreshMinutes)}
            onValueChange={(v) => setRefreshMinutes(Number(v))}
          >
            <SelectTrigger id="feed-settings-interval" aria-label="Check every" className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {choices.map((minutes) => (
                <SelectItem key={minutes} value={String(minutes)}>
                  {formatInterval(minutes)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Toggle
          label="Check this feed"
          description="Paused feeds keep their items, aren't checked on a schedule, and never auto-download."
          checked={enabled}
          onChange={setEnabled}
        />
        <Toggle
          label="Download matches automatically"
          description="New items that match a rule start downloading on their own, from the moment you turn this on."
          checked={autoDownload}
          onChange={setAutoDownload}
        />
      </SheetBody>
      <SheetFooter className="justify-between">
        <Button
          type="button"
          variant="ghost"
          className="text-destructive hover:text-destructive"
          onClick={() => setConfirmDelete(true)}
        >
          <Trash2Icon /> Unsubscribe
        </Button>
        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" onClick={onDone}>
            Cancel
          </Button>
          <Button type="submit" disabled={!name.trim() || update.isPending}>
            {update.isPending && <Loader2Icon className="animate-spin" />}
            Save
          </Button>
        </div>
      </SheetFooter>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Unsubscribe from ${feed.name}?`}
        description="Items only this feed listed leave your inbox. Downloads already started are not affected."
        confirmLabel="Unsubscribe"
        onConfirm={onDelete}
        destructive
      />
    </form>
  );
}

interface FeedSettingsSheetProps {
  feed: Feed | null;
  onClose(): void;
}

export function FeedSettingsSheet({ feed, onClose }: FeedSettingsSheetProps) {
  return (
    <Sheet open={feed !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>{feed?.name ?? "Feed"}</SheetTitle>
          <SheetDescription>{feed?.title ?? "Feed settings"}</SheetDescription>
        </SheetHeader>
        {feed && <SettingsForm key={feed.id} feed={feed} onDone={onClose} />}
      </SheetContent>
    </Sheet>
  );
}
