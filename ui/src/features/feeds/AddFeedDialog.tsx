import { Loader2Icon } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/api/errors";
import { useCreateFeed, useFeedPreview } from "@/api/queries";
import type { Feed } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { isHttpUrl } from "@/lib/feeds";
import { FeedPreviewPanel } from "./FeedPreviewPanel";

interface AddFeedDialogProps {
  open: boolean;
  /** An address to start with, e.g. one pasted on the page. */
  initialUrl?: string | null;
  onOpenChange(open: boolean): void;
  onCreated(feed: Feed): void;
}

function AddFeedForm({
  initialUrl,
  onDone,
  onCreated,
}: {
  initialUrl: string;
  onDone(): void;
  onCreated(feed: Feed): void;
}) {
  const [url, setUrl] = useState(initialUrl);
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [autoDownload, setAutoDownload] = useState(false);
  const address = useDebouncedValue(url.trim(), 400);
  const preview = useFeedPreview(isHttpUrl(address) ? address : null);
  const create = useCreateFeed();
  const title = preview.data?.title;

  useEffect(() => {
    if (title && !nameTouched) setName(title);
  }, [title, nameTouched]);

  const checking = preview.isFetching || address !== url.trim();
  // Said once typing pauses, so it doesn't flash while "https://" is still being typed.
  const notAnAddress = Boolean(address) && !checking && !isHttpUrl(address);
  const ready = Boolean(name.trim() && address && !checking && (preview.data || preview.isError));

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    create.mutate(
      {
        name: name.trim(),
        url: address,
        enabled: true,
        refresh_minutes: 15,
        auto_download: autoDownload,
      },
      {
        onSuccess: (feed) => {
          toast.success(`Subscribed to ${feed.name}`, {
            description: feed.last_error ? feed.last_error.message : "Its items are in your inbox.",
          });
          onCreated(feed);
          onDone();
        },
        onError: (error) => toast.error("Couldn't subscribe", { description: errorMessage(error) }),
      },
    );
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      <div className="space-y-1.5">
        <Label htmlFor="feed-url">Address</Label>
        <Input
          id="feed-url"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://tracker.example/rss?passkey=…"
          spellCheck={false}
          autoComplete="off"
          autoFocus
          aria-invalid={notAnAddress || undefined}
          aria-describedby={notAnAddress ? "feed-url-hint" : undefined}
          className="font-mono text-xs"
        />
        {notAnAddress && (
          <p id="feed-url-hint" role="alert" className="text-xs text-warning">
            Feed addresses start with http:// or https://
          </p>
        )}
      </div>
      <div className="rounded-xl border bg-muted/30 p-4">
        <FeedPreviewPanel
          preview={preview.data}
          error={preview.isError ? preview.error : null}
          loading={Boolean(address) && preview.isFetching}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="feed-name">Name</Label>
        <Input
          id="feed-name"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setNameTouched(true);
          }}
          placeholder="TV"
          maxLength={100}
        />
      </div>
      <label className="flex items-start justify-between gap-3 rounded-lg border px-3 py-2.5">
        <span className="text-sm">
          Download matches automatically
          <span className="block text-xs text-muted-foreground">
            New items that match a rule start downloading on their own. What the feed lists now is
            left for you to pick.
          </span>
        </span>
        <Switch
          checked={autoDownload}
          onCheckedChange={setAutoDownload}
          aria-label="Download matches automatically"
        />
      </label>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={!ready || create.isPending}>
          {create.isPending && <Loader2Icon className="animate-spin" />}
          {preview.isError ? "Subscribe anyway" : "Subscribe"}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function AddFeedDialog({ open, initialUrl, onOpenChange, onCreated }: AddFeedDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Add a feed</DialogTitle>
          <DialogDescription>
            An RSS feed whose items link to magnets. Its address stays private: only admins can see
            it whole.
          </DialogDescription>
        </DialogHeader>
        {open && (
          <AddFeedForm
            initialUrl={initialUrl ?? ""}
            onDone={() => onOpenChange(false)}
            onCreated={onCreated}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
