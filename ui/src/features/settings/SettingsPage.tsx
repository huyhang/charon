import { HistoryIcon } from "lucide-react";
import { toast } from "sonner";
import { errorMessage } from "@/api/errors";
import { useClearTitleCache, useMetadataProviders } from "@/api/queries";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ProviderKeySection } from "./ProviderKeySection";

function RememberedSearches() {
  const clear = useClearTitleCache();
  const onClear = () =>
    clear.mutate(undefined, {
      onSuccess: () =>
        toast("Remembered searches cleared", { description: "The next searches ask again." }),
      onError: (error) => toast.error("Couldn't clear them", { description: errorMessage(error) }),
    });

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
      <p className="max-w-prose text-xs text-muted-foreground">
        Charon remembers searches for a day, so repeating one costs nothing, and answers from older
        ones (up to a week) while the provider can&apos;t be reached.
      </p>
      <Button variant="outline" size="sm" onClick={onClear} disabled={clear.isPending}>
        <HistoryIcon /> Clear remembered searches
      </Button>
    </div>
  );
}

function TitleLookupSettings() {
  const providers = useMetadataProviders();
  if (providers.isPending) return <Skeleton className="h-32 rounded-xl" />;
  if (providers.isError) {
    return <ErrorState error={providers.error} onRetry={() => providers.refetch()} />;
  }
  return (
    <>
      {providers.data.map((provider) => (
        <ProviderKeySection key={provider.id} provider={provider} />
      ))}
      <RememberedSearches />
    </>
  );
}

/** Admin settings Charon keeps itself, rather than in its environment. */
export function SettingsPage() {
  return (
    <div className="space-y-8">
      <PageHeader title="Settings" description="Changes here apply at once, without a restart." />
      <section
        aria-labelledby="title-lookup"
        className="space-y-4 rounded-xl border bg-card/70 p-4"
      >
        <div className="space-y-1">
          <h2 id="title-lookup" className="text-lg font-semibold">
            Title lookup
          </h2>
          <p className="text-sm text-muted-foreground">
            Lets rule authors look up a show&apos;s or movie&apos;s official title and rename
            releases to it.
          </p>
        </div>
        <TitleLookupSettings />
      </section>
    </div>
  );
}
