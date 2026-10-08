import { ExternalLinkIcon, Loader2Icon, SearchIcon, TriangleAlertIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { errorHintOf, errorMessage, isApiError } from "@/api/errors";
import { useMetadataProviders, useRefreshTitleSearch, useTitleSearch } from "@/api/queries";
import type {
  KindFilter,
  MetadataProvider,
  RenameStep,
  TitleMatch,
  TitleSearch,
  TitleSearchQuery,
} from "@/api/types";
import { usePrincipal } from "@/auth/AuthProvider";
import { canChangeSettings } from "@/auth/permissions";
import { ProviderCredit } from "@/components/ProviderCredit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import { ProviderKeyForm } from "@/features/settings/ProviderKeyForm";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";
import { queryFromName, titleFindText, titleStep } from "@/lib/titles";

// Searching waits for a pause in typing, so Charon spends little of the provider's budget.
export const SEARCH_DELAY_MS = 400;
const MIN_QUERY_LENGTH = 2;
// Answers younger than this are as good as new: no need to say they were remembered.
const FRESH_ENOUGH_SECONDS = 60;

const KINDS: { value: KindFilter; label: string }[] = [
  { value: "any", label: "All" },
  { value: "tv", label: "TV" },
  { value: "movie", label: "Movies" },
];

interface TitleLookupProps {
  /** A release name to guess the search from and find the title in; may be blank. */
  sample: string;
  /** `step` renames the release's title to `match`'s canonical one. */
  onPick(step: RenameStep, match: TitleMatch): void;
}

/** Lookups need the provider's key first: admins can save it right here. */
function NotConfigured({ provider }: { provider: MetadataProvider }) {
  const principal = usePrincipal();
  if (!canChangeSettings(principal)) {
    return (
      <p className="text-sm text-muted-foreground">
        Title lookup needs a {provider.name} token. Ask an admin to add one in Settings.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <p className="text-sm">
        Title lookup needs a {provider.name} token first. Saved once, it works for everyone; you can
        change it later in Settings.
      </p>
      <ProviderKeyForm provider={provider} />
    </div>
  );
}

/** How old a remembered answer is, with a way to ask again. A warning if it had to stand in. */
function Freshness({
  provider,
  found,
  query,
}: {
  provider: MetadataProvider;
  found: TitleSearch;
  query: TitleSearchQuery;
}) {
  const refresh = useRefreshTitleSearch();
  if (!found.stale && found.age_seconds < FRESH_ENOUGH_SECONDS) return null;
  const when = formatRelative(new Date(Date.now() - found.age_seconds * 1000).toISOString());
  return (
    <p
      className={cn(
        "flex flex-wrap items-center gap-x-2 text-[11px]",
        found.stale ? "text-warning" : "text-muted-foreground",
      )}
    >
      {found.stale
        ? `${provider.name} couldn't be asked just now: these results are from ${when}.`
        : `Remembered from ${when}.`}
      <button
        type="button"
        className="text-primary hover:underline disabled:opacity-50"
        disabled={refresh.isPending}
        onClick={() => refresh.mutate(query)}
      >
        Ask again
      </button>
      {refresh.isError && <span role="alert">{errorMessage(refresh.error)}</span>}
    </p>
  );
}

function ResultRow({
  match,
  provider,
  renamesTo,
  onUse,
}: {
  match: TitleMatch;
  provider: MetadataProvider;
  renamesTo: string | undefined;
  onUse(): void;
}) {
  return (
    <li className="flex items-start gap-3 rounded-lg border bg-background/30 p-2.5">
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="flex flex-wrap items-center gap-x-2 text-sm font-medium">
          <span className="break-words">{match.title}</span>
          {match.year && <span className="text-muted-foreground">{match.year}</span>}
          <Badge tone="muted">{match.kind === "tv" ? "TV" : "Movie"}</Badge>
        </p>
        {match.original_title !== match.title && (
          <p className="text-xs break-words text-muted-foreground">{match.original_title}</p>
        )}
        {match.overview && (
          <p className="line-clamp-2 text-xs text-muted-foreground">{match.overview}</p>
        )}
        {renamesTo && <p className="font-mono text-[11px] break-all text-success">→ {renamesTo}</p>}
        <a
          href={match.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
        >
          View on {provider.name} <ExternalLinkIcon className="size-3" />
        </a>
      </div>
      <Button type="button" size="sm" onClick={onUse} aria-label={`Use ${match.title}`}>
        Use
      </Button>
    </li>
  );
}

function Results({
  provider,
  term,
  kind,
  stepFor,
  onPick,
}: {
  provider: MetadataProvider;
  term: string;
  kind: KindFilter;
  stepFor(match: TitleMatch): RenameStep | null;
  onPick(step: RenameStep, match: TitleMatch): void;
}) {
  const query = term.length >= MIN_QUERY_LENGTH ? { q: term, provider: provider.id, kind } : null;
  const search = useTitleSearch(query);

  if (!query) {
    return <p className="text-xs text-muted-foreground">Type a title to look it up.</p>;
  }
  // The key was removed since the dialog opened.
  if (isApiError(search.error) && search.error.code === "metadata_not_configured") {
    return <NotConfigured provider={provider} />;
  }
  if (search.isError) {
    const hint = errorHintOf(search.error);
    return (
      <div role="alert" className="flex items-start gap-2 text-xs text-warning">
        <TriangleAlertIcon className="mt-px size-3.5 shrink-0" />
        <span>
          {errorMessage(search.error)}
          {hint && <span className="block text-muted-foreground">{hint}</span>}
        </span>
      </div>
    );
  }
  if (!search.data) {
    return (
      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2Icon className="size-3.5 animate-spin" /> Searching…
      </p>
    );
  }
  const freshness = <Freshness provider={provider} found={search.data} query={query} />;
  if (search.data.results.length === 0) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-muted-foreground">
          No movies or shows match “{term}”. Try the title in another language.
        </p>
        {freshness}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <ul className="max-h-[45dvh] space-y-2 overflow-y-auto" aria-label="Results">
        {search.data.results.map((match) => {
          const step = stepFor(match);
          return (
            <ResultRow
              key={`${match.kind}-${match.id}`}
              match={match}
              provider={provider}
              renamesTo={step?.replace}
              onUse={() => step && onPick(step, match)}
            />
          );
        })}
      </ul>
      {freshness}
    </div>
  );
}

function LookupForm({
  provider,
  sample,
  onPick,
}: TitleLookupProps & { provider: MetadataProvider }) {
  const [text, setText] = useState(() => queryFromName(sample));
  const [kind, setKind] = useState<KindFilter>("any");
  const [includeYear, setIncludeYear] = useState(false);
  const term = useDebouncedValue(text.trim(), SEARCH_DELAY_MS);
  const find = titleFindText(sample, text);

  // The dialog renders outside the rule form, but React still bubbles events through it:
  // Enter here mustn't save the rule.
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    event.stopPropagation();
  };

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <Input
        aria-label="Title to look up"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="Kusuriya no Hitorigoto"
        autoFocus
        spellCheck={false}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Segmented<KindFilter> label="Kind" value={kind} onChange={setKind} options={KINDS} />
        <label className="flex items-center gap-2 text-xs">
          <Checkbox
            checked={includeYear}
            onCheckedChange={(checked) => setIncludeYear(checked === true)}
            aria-label="Include year"
          />
          Include year
        </label>
      </div>
      {find && (
        <p className="text-xs text-muted-foreground">
          Replaces <code className="font-mono break-all text-foreground">{find}</code> in the name.
        </p>
      )}
      <Results
        provider={provider}
        term={term}
        kind={kind}
        stepFor={(match) => titleStep(sample, text, match, includeYear)}
        onPick={onPick}
      />
      <ProviderCredit provider={provider} className="justify-end border-t pt-3" />
    </form>
  );
}

/**
 * Looks a canonical title up (e.g. on TMDB) and turns the pick into a rename step. Offered
 * whenever Charon knows a provider; until it has a key, the dialog explains how to add one.
 */
export function TitleLookup({ sample, onPick }: TitleLookupProps) {
  const providers = useMetadataProviders();
  const [open, setOpen] = useState(false);
  const provider = providers.data?.[0];
  if (!provider) return null;

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
        <SearchIcon /> Look up official title
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Look up the official title</DialogTitle>
            <DialogDescription>
              Pick a result to add a step that renames the release&apos;s title to it.
            </DialogDescription>
          </DialogHeader>
          {provider.configured ? (
            <LookupForm
              provider={provider}
              sample={sample}
              onPick={(step, match) => {
                onPick(step, match);
                setOpen(false);
              }}
            />
          ) : (
            <NotConfigured provider={provider} />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
