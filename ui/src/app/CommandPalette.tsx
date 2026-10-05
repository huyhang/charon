import { LaptopIcon, LogOutIcon, MoonIcon, PlusIcon, SunIcon } from "lucide-react";
import { useEffect } from "react";
import { useNavigate } from "react-router";
import { useRecentJobs } from "@/api/queries";
import { useAuth, usePrincipal } from "@/auth/AuthProvider";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { isPaletteShortcut } from "@/lib/keyboard";
import { jobTitle, STATUS_META } from "@/lib/jobs";
import { useTheme } from "@/theme/ThemeProvider";
import { navItemsFor } from "./nav";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange(open: boolean): void;
}

export function useCommandPaletteShortcut(toggle: () => void): void {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isPaletteShortcut(event)) {
        event.preventDefault();
        toggle();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [toggle]);
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const navigate = useNavigate();
  const principal = usePrincipal();
  const { signOut } = useAuth();
  const { setTheme } = useTheme();
  const recent = useRecentJobs(open).data?.items ?? [];

  const run = (action: () => void) => () => {
    onOpenChange(false);
    action();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent hideClose className="top-[20%] translate-y-0 overflow-hidden p-0 sm:max-w-xl">
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <Command loop>
          <CommandInput placeholder="Type a command or search…" />
          <CommandList>
            <CommandEmpty>No results.</CommandEmpty>
            <CommandGroup heading="Actions">
              <CommandItem onSelect={run(() => navigate("/downloads?add=1"))}>
                <PlusIcon /> Add a magnet link
              </CommandItem>
              <CommandItem onSelect={run(() => navigate("/rules?new=1"))}>
                <PlusIcon /> New rule
              </CommandItem>
            </CommandGroup>
            <CommandGroup heading="Go to">
              {navItemsFor(principal).map(({ to, label, icon: Icon }) => (
                <CommandItem key={to} onSelect={run(() => navigate(to))}>
                  <Icon /> {label}
                </CommandItem>
              ))}
            </CommandGroup>
            {recent.length > 0 && (
              <CommandGroup heading="Recent downloads">
                {recent.map((job) => (
                  <CommandItem
                    key={job.id}
                    value={`${jobTitle(job) ?? ""} ${job.id}`}
                    onSelect={run(() => navigate(`/downloads/${job.id}`))}
                  >
                    <span className="min-w-0 flex-1 truncate">
                      {jobTitle(job) ?? "Unnamed download"}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {STATUS_META[job.status].label}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            <CommandGroup heading="Theme">
              <CommandItem onSelect={run(() => setTheme("light"))}>
                <SunIcon /> Light theme
              </CommandItem>
              <CommandItem onSelect={run(() => setTheme("dark"))}>
                <MoonIcon /> Dark theme
              </CommandItem>
              <CommandItem onSelect={run(() => setTheme("system"))}>
                <LaptopIcon /> System theme
              </CommandItem>
            </CommandGroup>
            {principal.auth_enabled && (
              <CommandGroup heading="Account">
                <CommandItem onSelect={run(() => signOut())}>
                  <LogOutIcon /> Sign out
                </CommandItem>
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
