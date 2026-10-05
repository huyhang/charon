import { LaptopIcon, LogOutIcon, MoonIcon, SunIcon } from "lucide-react";
import { useAuth, usePrincipal } from "@/auth/AuthProvider";
import { useTheme, type Theme } from "@/theme/ThemeProvider";
import { cn } from "@/lib/cn";
import { Badge } from "./ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";

const THEME_OPTIONS: { theme: Theme; label: string; icon: typeof SunIcon }[] = [
  { theme: "light", label: "Light", icon: SunIcon },
  { theme: "dark", label: "Dark", icon: MoonIcon },
  { theme: "system", label: "System", icon: LaptopIcon },
];

export function UserMenu({ className }: { className?: string }) {
  const principal = usePrincipal();
  const { signOut } = useAuth();
  const { theme, setTheme } = useTheme();
  const initial = principal.name.charAt(0).toUpperCase();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "flex items-center gap-2.5 rounded-lg p-1.5 text-left text-sm transition outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring",
          className,
        )}
        aria-label="Account and settings"
      >
        <span className="flex size-7 items-center justify-center rounded-full bg-river text-xs font-semibold text-background">
          {initial}
        </span>
        <span className="min-w-0 flex-1 max-md:hidden">
          <span className="block truncate font-medium">{principal.name}</span>
          <span className="block text-xs text-muted-foreground capitalize">{principal.role}</span>
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="flex items-center justify-between">
          <span className="truncate">{principal.name}</span>
          <Badge tone={principal.role === "admin" ? "progress" : "neutral"}>{principal.role}</Badge>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <div className="grid grid-cols-3 gap-1 p-1">
          {THEME_OPTIONS.map(({ theme: option, label, icon: Icon }) => (
            <button
              key={option}
              type="button"
              onClick={() => setTheme(option)}
              aria-pressed={theme === option}
              className={cn(
                "flex flex-col items-center gap-1 rounded-md py-2 text-xs text-muted-foreground transition hover:bg-accent",
                theme === option && "bg-accent text-foreground",
              )}
            >
              <Icon className="size-4" />
              {label}
            </button>
          ))}
        </div>
        {principal.auth_enabled && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => signOut()}>
              <LogOutIcon /> Sign out
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
