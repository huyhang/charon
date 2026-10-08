import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckIcon,
  FlaskConicalIcon,
  RotateCcwIcon,
  TimerResetIcon,
  XIcon,
  ZapIcon,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/api/errors";
import { queryKeys } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import { FakeFeedsSection } from "./FakeFeedsSection";
import { FakeTmdbSection } from "./FakeTmdbSection";
import { createHttpSimulator, taskPercent, type SimulatorClient } from "./simulatorClient";

const FAILURE_DETAIL = "broken_link";

function useSimulatorAction(simulator: SimulatorClient) {
  const queryClient = useQueryClient();
  return async (label: string, action: (s: SimulatorClient) => Promise<void>) => {
    try {
      await action(simulator);
      toast(label);
      await queryClient.invalidateQueries({ queryKey: ["simulator"] });
      setTimeout(() => queryClient.invalidateQueries({ queryKey: queryKeys.downloads }), 1200);
    } catch (error) {
      toast.error("Simulator action failed", { description: errorMessage(error) });
    }
  };
}

/** Dev-only: steer the fake Download Station without leaving the UI. Not in production builds. */
export default function SimulatorPanel({
  simulator = createHttpSimulator(),
}: {
  simulator?: SimulatorClient;
}) {
  const [open, setOpen] = useState(false);
  const tasks = useQuery({
    queryKey: ["simulator", "tasks"],
    queryFn: () => simulator.listTasks(),
    enabled: open,
    refetchInterval: 1000,
    retry: false,
  });
  const run = useSimulatorAction(simulator);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="fixed bottom-20 left-4 z-40 flex items-center gap-2 rounded-full border border-warning/40 bg-popover/90 px-3 py-2 text-xs font-medium text-warning shadow-xl backdrop-blur transition hover:border-warning md:bottom-4 md:left-64"
        >
          <FlaskConicalIcon className="size-3.5" /> Simulator
        </button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="start"
        className="max-h-[calc(100dvh-6rem)] w-[min(24rem,calc(100vw-2rem))] overflow-y-auto p-0"
      >
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div>
            <p className="text-sm font-medium">Fake Download Station</p>
            <p className="text-xs text-muted-foreground">Dev builds only</p>
          </div>
          <Badge tone="warning">dev</Badge>
        </div>
        <div className="max-h-72 overflow-y-auto p-2">
          {tasks.isError && (
            <p className="px-2 py-4 text-xs text-destructive">
              Can&apos;t reach the fake: {errorMessage(tasks.error)}
            </p>
          )}
          {tasks.data?.length === 0 && (
            <p className="px-2 py-4 text-xs text-muted-foreground">
              No tasks. Add a magnet to create one.
            </p>
          )}
          <ul className="space-y-1">
            {tasks.data?.map((task) => (
              <li key={task.id} className="space-y-2 rounded-lg px-2 py-2 hover:bg-accent/50">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-xs">{task.title}</span>
                  <Badge
                    tone={
                      task.status === "error"
                        ? "danger"
                        : task.status === "finished"
                          ? "success"
                          : "progress"
                    }
                  >
                    {task.status}
                  </Badge>
                </div>
                {task.status === "downloading" && (
                  <div className="flex items-center gap-2">
                    <Progress value={taskPercent(task)} className="flex-1" />
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-6 px-2 text-[11px]"
                      onClick={() => run(`Completed ${task.title}`, (s) => s.complete(task.id))}
                    >
                      <CheckIcon /> Complete
                    </Button>
                    {[FAILURE_DETAIL].map((detail) => (
                      <Button
                        key={detail}
                        size="sm"
                        variant="outline"
                        className="h-6 px-2 text-[11px] text-destructive"
                        onClick={() => run(`Failed ${task.title}`, (s) => s.fail(task.id, detail))}
                      >
                        <XIcon /> Fail
                      </Button>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
        <FakeFeedsSection simulator={simulator} open={open} />
        <FakeTmdbSection simulator={simulator} open={open} />
        <div className="grid grid-cols-2 gap-2 border-t p-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => run("Download Station sessions expired", (s) => s.expireSessions())}
          >
            <TimerResetIcon /> Expire sessions
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-destructive"
            onClick={() => run("Fake Download Station reset", (s) => s.reset())}
          >
            <RotateCcwIcon /> Reset fake
          </Button>
        </div>
        <p className="flex items-center gap-1.5 border-t px-4 py-2 text-[11px] text-muted-foreground">
          <ZapIcon className="size-3" /> Reset drops every task, so in-flight jobs fail with
          task_missing.
        </p>
      </PopoverContent>
    </Popover>
  );
}
