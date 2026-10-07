import { useQuery, useQueryClient } from "@tanstack/react-query";
import { HeartPulseIcon, MegaphoneIcon, UnplugIcon } from "lucide-react";
import { toast } from "sonner";
import { useClient } from "@/api/context";
import { errorMessage } from "@/api/errors";
import { queryKeys } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { SimulatorClient } from "./simulatorClient";

/** Steers the fake's RSS feeds, then has Charon fetch them so the inbox shows the change. */
export function FakeFeedsSection({
  simulator,
  open,
}: {
  simulator: SimulatorClient;
  open: boolean;
}) {
  const client = useClient();
  const queryClient = useQueryClient();
  const feeds = useQuery({
    queryKey: ["simulator", "feeds"],
    queryFn: () => simulator.listFeeds(),
    enabled: open,
    retry: false,
  });

  const run = async (label: string, action: () => Promise<void>) => {
    try {
      await action();
      const subscribed = await client.listFeeds();
      await Promise.all(subscribed.map((feed) => client.refreshFeed(feed.id)));
      toast(label, { description: `Charon refreshed ${subscribed.length} feed(s)` });
    } catch (error) {
      toast.error("Simulator action failed", { description: errorMessage(error) });
    }
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["simulator", "feeds"] }),
      queryClient.invalidateQueries({ queryKey: queryKeys.feeds }),
    ]);
  };

  if (!feeds.data?.length) return null;
  return (
    <section className="space-y-1 border-t p-2" aria-label="Fake feeds">
      <p className="px-2 pt-1 text-xs font-medium text-muted-foreground">Fake feeds</p>
      <ul className="space-y-1">
        {feeds.data.map((feed) => (
          <li key={feed.slug} className="space-y-1.5 rounded-lg px-2 py-2 hover:bg-accent/50">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-xs">
                {feed.title} <span className="text-muted-foreground">({feed.items.length})</span>
              </span>
              <Badge tone={feed.mode === "ok" ? "success" : "danger"}>{feed.mode}</Badge>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <Button
                size="sm"
                variant="outline"
                className="h-6 px-2 text-[11px]"
                onClick={() =>
                  run(`Published to ${feed.title}`, () => simulator.publish(feed.slug))
                }
              >
                <MegaphoneIcon /> Publish
              </Button>
              {feed.mode === "ok" ? (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 px-2 text-[11px] text-destructive"
                    onClick={() =>
                      run(`${feed.title} now fails`, () =>
                        simulator.breakFeed(feed.slug, "http_error"),
                      )
                    }
                  >
                    <UnplugIcon /> Fail (503)
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 px-2 text-[11px] text-destructive"
                    onClick={() =>
                      run(`${feed.title} now serves HTML`, () =>
                        simulator.breakFeed(feed.slug, "bad_xml"),
                      )
                    }
                  >
                    <UnplugIcon /> Not RSS
                  </Button>
                </>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-6 px-2 text-[11px]"
                  onClick={() => run(`${feed.title} healed`, () => simulator.healFeed(feed.slug))}
                >
                  <HeartPulseIcon /> Heal
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
