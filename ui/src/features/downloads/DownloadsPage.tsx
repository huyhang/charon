import { DownloadCloudIcon, Loader2Icon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { allJobs, useDownloadSummary, useDownloads } from "@/api/queries";
import type { Job } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FILTERS, isListCapped, MAX_LISTED, type FilterId } from "@/lib/jobs";
import { isMagnet } from "@/lib/magnet";
import { JobCard } from "./JobCard";
import { JobDrawer } from "./JobDrawer";
import { MagnetBar } from "./MagnetBar";
import { StatsStrip } from "./StatsStrip";

export function parseFilter(value: string | null): FilterId {
  return FILTERS.some((f) => f.id === value) ? (value as FilterId) : "all";
}

/** Reads and clears `?add=` (a magnet to prefill, or anything else to just focus). */
function useAddRequest(): { magnet: string | null; focusSignal: number } {
  const [params, setParams] = useSearchParams();
  const [request, setRequest] = useState({ magnet: null as string | null, focusSignal: 0 });
  const add = params.get("add");

  useEffect(() => {
    if (add === null) return;
    setRequest((prev) => ({
      magnet: isMagnet(add) ? add : prev.magnet,
      focusSignal: prev.focusSignal + 1,
    }));
    setParams(
      (prev) => {
        prev.delete("add");
        return prev;
      },
      { replace: true },
    );
  }, [add, setParams]);

  return request;
}

function JobListSkeleton() {
  return (
    <div className="space-y-3" aria-label="Loading downloads">
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-24 rounded-xl" />
      ))}
    </div>
  );
}

export function DownloadsPage() {
  const [params, setParams] = useSearchParams();
  const { jobId } = useParams();
  const navigate = useNavigate();
  const filter = parseFilter(params.get("status"));
  const downloads = useDownloads(filter);
  const summary = useDownloadSummary();
  const { magnet, focusSignal } = useAddRequest();
  const jobs = allJobs(downloads.data);
  const query = params.toString() ? `?${params.toString()}` : "";

  const openJob = useCallback(
    (job: Job) => navigate(`/downloads/${job.id}${query}`),
    [navigate, query],
  );
  const closeJob = useCallback(() => navigate(`/downloads${query}`), [navigate, query]);
  const setFilter = (value: string) =>
    setParams((prev) => {
      if (value === "all") prev.delete("status");
      else prev.set("status", value);
      return prev;
    });

  return (
    <div className="space-y-8">
      <PageHeader
        title="Downloads"
        description="Paste a magnet link anywhere to start. Charon files it when it's done."
      />
      <MagnetBar initialMagnet={magnet} focusSignal={focusSignal} />
      <StatsStrip summary={summary.data} />

      <section className="space-y-4">
        <Tabs value={filter} onValueChange={setFilter}>
          <TabsList aria-label="Filter downloads">
            {FILTERS.map((f) => (
              <TabsTrigger key={f.id} value={f.id}>
                {f.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        {downloads.isPending ? (
          <JobListSkeleton />
        ) : downloads.isError ? (
          <ErrorState error={downloads.error} onRetry={() => downloads.refetch()} />
        ) : jobs.length === 0 ? (
          <EmptyState
            icon={DownloadCloudIcon}
            title={filter === "all" ? "Nothing here yet" : "No downloads match"}
            description={
              filter === "all"
                ? "Paste a magnet link above, or anywhere on this page, to start your first download."
                : "Try another filter."
            }
          />
        ) : (
          <div className="space-y-3">
            {jobs.map((job) => (
              <JobCard key={job.id} job={job} onOpen={openJob} />
            ))}
            {downloads.hasNextPage && (
              <div className="flex justify-center pt-2">
                <Button
                  variant="outline"
                  onClick={() => downloads.fetchNextPage()}
                  disabled={downloads.isFetchingNextPage}
                >
                  {downloads.isFetchingNextPage && <Loader2Icon className="animate-spin" />}
                  Load more
                </Button>
              </div>
            )}
            {isListCapped(downloads.data?.pages ?? []) && (
              <p className="pt-2 text-center text-xs text-muted-foreground">
                Showing the newest {MAX_LISTED} downloads. Older ones are still in Charon.
              </p>
            )}
          </div>
        )}
      </section>

      <JobDrawer jobId={jobId} onClose={closeJob} />
    </div>
  );
}
