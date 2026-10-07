import { SearchIcon } from "lucide-react";
import { useCallback, useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";
import { useFeedSummary, useSessionCheck } from "@/api/queries";
import { usePrincipal } from "@/auth/AuthProvider";
import { HealthIndicator } from "@/components/HealthIndicator";
import { Logo, LogoMark } from "@/components/Logo";
import { Kbd } from "@/components/ui/kbd";
import { UserMenu } from "@/components/UserMenu";
import { useGlobalMagnetPaste } from "@/hooks/useGlobalPaste";
import { cn } from "@/lib/cn";
import { CommandPalette, useCommandPaletteShortcut } from "./CommandPalette";
import { badgeLabel, navItemsFor } from "./nav";

function NavBadge({ to, className }: { to: string; className?: string }) {
  const summary = useFeedSummary();
  const label = to === "/feeds" ? badgeLabel(summary.data?.unread) : null;
  if (!label) return null;
  return (
    <span
      className={cn(
        "rounded-full bg-primary px-1.5 text-[10px] leading-4 font-semibold text-primary-foreground tabular-nums",
        className,
      )}
      aria-label={`${label} new`}
    >
      {label}
    </span>
  );
}

export function AppShell({ devTools }: { devTools?: ReactNode }) {
  const principal = usePrincipal();
  useSessionCheck(principal);
  const navigate = useNavigate();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const togglePalette = useCallback(() => setPaletteOpen((open) => !open), []);
  useCommandPaletteShortcut(togglePalette);
  useGlobalMagnetPaste(
    useCallback(
      (magnet: string) => navigate(`/downloads?add=${encodeURIComponent(magnet)}`),
      [navigate],
    ),
  );
  const items = navItemsFor(principal);

  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r bg-card/30 px-3 py-4 backdrop-blur-xl md:flex">
        <Logo className="px-2 pb-6" />
        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          className="mb-4 flex h-8 items-center gap-2 rounded-lg border bg-background/50 px-2.5 text-xs text-muted-foreground transition hover:border-primary/40 hover:text-foreground"
        >
          <SearchIcon className="size-3.5" />
          <span className="flex-1 text-left">Search or jump to…</span>
          <Kbd>⌘K</Kbd>
        </button>
        <nav className="flex flex-col gap-0.5" aria-label="Main">
          {items.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "group flex h-9 items-center gap-3 rounded-lg px-2.5 text-sm text-muted-foreground transition hover:bg-accent/60 hover:text-foreground",
                  isActive &&
                    "bg-accent text-foreground shadow-[inset_2px_0_0_0_var(--color-primary)]",
                )
              }
            >
              <Icon className="size-4" />
              <span className="flex-1">{label}</span>
              <NavBadge to={to} />
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-3">
          <div className="px-2.5">
            <HealthIndicator />
          </div>
          <UserMenu className="w-full" />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b bg-background/70 px-4 backdrop-blur-xl md:hidden">
          <LogoMark className="size-7" />
          <div className="flex items-center gap-3">
            <HealthIndicator compact />
            <button
              type="button"
              aria-label="Search"
              onClick={() => setPaletteOpen(true)}
              className="rounded-lg p-2 text-muted-foreground hover:bg-accent"
            >
              <SearchIcon className="size-4" />
            </button>
            <UserMenu />
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 pt-6 pb-28 sm:px-8 md:pt-10 md:pb-16">
          <Outlet />
        </main>
      </div>

      <nav
        aria-label="Main mobile"
        className="fixed inset-x-0 bottom-0 z-30 flex border-t bg-background/80 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden"
      >
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] text-muted-foreground transition",
                isActive && "text-primary",
              )
            }
          >
            <span className="relative">
              <Icon className="size-5" />
              <NavBadge to={to} className="absolute -top-1.5 -right-3" />
            </span>
            {label}
          </NavLink>
        ))}
      </nav>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      {devTools}
    </div>
  );
}
