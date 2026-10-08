import { useQuery, useQueryClient } from "@tanstack/react-query";
import { GaugeIcon, HeartPulseIcon, UnplugIcon } from "lucide-react";
import { toast } from "sonner";
import { errorMessage } from "@/api/errors";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { FakeTmdbMode, SimulatorClient } from "./simulatorClient";

const QUERY_KEY = ["simulator", "tmdb"];

/** Steers the fake TMDB, and shows whether Charon has kept within its request budget. */
export function FakeTmdbSection({
  simulator,
  open,
}: {
  simulator: SimulatorClient;
  open: boolean;
}) {
  const queryClient = useQueryClient();
  const state = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => simulator.tmdbState(),
    enabled: open,
    refetchInterval: 1000,
    retry: false,
  });

  const run = async (label: string, mode: FakeTmdbMode) => {
    try {
      await simulator.setTmdbMode(mode);
      toast(label);
    } catch (error) {
      toast.error("Simulator action failed", { description: errorMessage(error) });
    }
    await queryClient.invalidateQueries({ queryKey: QUERY_KEY });
  };

  if (!state.data) return null;
  const { mode, requests, busiest_window, limit, window_seconds } = state.data;
  return (
    <section className="space-y-1.5 border-t p-2" aria-label="Fake TMDB">
      <div className="flex items-center justify-between gap-2 px-2 pt-1">
        <p className="text-xs font-medium text-muted-foreground">Fake TMDB</p>
        <Badge tone={mode === "ok" ? "success" : "danger"}>{mode}</Badge>
      </div>
      <p
        className={cn(
          "px-2 text-[11px] text-muted-foreground",
          busiest_window > limit && "text-destructive",
        )}
      >
        {requests} request(s) · busiest {window_seconds} s: {busiest_window} of {limit}
      </p>
      <div className="flex flex-wrap gap-1.5 px-2">
        {mode === "ok" ? (
          <>
            <Button
              size="sm"
              variant="outline"
              className="h-6 px-2 text-[11px] text-destructive"
              onClick={() => run("Fake TMDB now answers 429", "throttled")}
            >
              <GaugeIcon /> Throttle (429)
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-6 px-2 text-[11px] text-destructive"
              onClick={() => run("Fake TMDB is down", "down")}
            >
              <UnplugIcon /> Down (503)
            </Button>
          </>
        ) : (
          <Button
            size="sm"
            variant="outline"
            className="h-6 px-2 text-[11px]"
            onClick={() => run("Fake TMDB healed", "ok")}
          >
            <HeartPulseIcon /> Heal
          </Button>
        )}
      </div>
      <p className="px-2 text-[11px] text-muted-foreground">
        Charon remembers answers for a day, so try a new title to reach the fake.
      </p>
    </section>
  );
}
