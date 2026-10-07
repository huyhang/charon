import { useNavigate } from "react-router";
import { toast } from "sonner";
import { errorHintOf, errorMessage } from "@/api/errors";
import { useDownloadFeedItem, usePendingFeedDownloads } from "@/api/queries";
import type { FeedItem } from "@/api/types";

/**
 * Downloads items and says how each went, with a way to open the download. Every download is
 * tracked and reported on its own, however many are in flight; an item already on its way
 * isn't sent again.
 */
export function useFeedDownload() {
  const download = useDownloadFeedItem();
  const pendingHashes = usePendingFeedDownloads();
  const navigate = useNavigate();

  const reportStarted = (item: Pick<FeedItem, "name">, jobId: string, created: boolean) => {
    const open = { label: "Open", onClick: () => navigate(`/downloads/${jobId}`) };
    if (created) toast.success("Download started", { description: item.name, action: open });
    else toast("Already in Charon", { description: item.name, action: open });
  };
  const reportFailed = (error: unknown) =>
    toast.error("Couldn't start the download", {
      description: [errorMessage(error), errorHintOf(error)].filter(Boolean).join(" "),
    });

  const start = (item: Pick<FeedItem, "info_hash" | "name">, ruleId?: string | null) => {
    if (pendingHashes.has(item.info_hash)) return;
    // Per-call handlers: mutate()'s own callbacks only fire for the latest call.
    download
      .mutateAsync({ infoHash: item.info_hash, ruleId })
      .then(({ job, created }) => reportStarted(item, job.id, created), reportFailed);
  };
  return { start, pendingHashes };
}
