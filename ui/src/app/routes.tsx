import type { ReactNode } from "react";
import { Navigate, type RouteObject } from "react-router";
import type { Principal } from "@/api/types";
import { usePrincipal } from "@/auth/AuthProvider";
import { canChangeSettings, canManageKeys } from "@/auth/permissions";
import { EmptyState } from "@/components/EmptyState";
import { Splash } from "@/components/Splash";
import { Button } from "@/components/ui/button";
import { DownloadsPage } from "@/features/downloads/DownloadsPage";
import { CompassIcon } from "lucide-react";
import { Link } from "react-router";
import { AppShell } from "./AppShell";

function Allowed({ when, children }: { when(principal: Principal): boolean; children: ReactNode }) {
  return when(usePrincipal()) ? children : <Navigate to="/downloads" replace />;
}

function NotFound() {
  return (
    <EmptyState
      icon={CompassIcon}
      title="Lost on the river"
      description="There's nothing at this address."
      action={
        <Button asChild variant="outline">
          <Link to="/downloads">Back to downloads</Link>
        </Button>
      }
    />
  );
}

export function routes(devTools?: ReactNode): RouteObject[] {
  return [
    {
      element: <AppShell devTools={devTools} />,
      // Shown while a lazily loaded page's code arrives on a deep link, e.g. a reload on /rules.
      HydrateFallback: Splash,
      children: [
        { index: true, element: <Navigate to="/downloads" replace /> },
        { path: "downloads/:jobId?", element: <DownloadsPage /> },
        {
          path: "feeds",
          lazy: async () => ({ Component: (await import("@/features/feeds/FeedsPage")).FeedsPage }),
        },
        {
          path: "rules",
          lazy: async () => ({ Component: (await import("@/features/rules/RulesPage")).RulesPage }),
        },
        {
          path: "keys",
          lazy: async () => {
            const { KeysPage } = await import("@/features/keys/KeysPage");
            return {
              element: (
                <Allowed when={canManageKeys}>
                  <KeysPage />
                </Allowed>
              ),
            };
          },
        },
        {
          path: "settings",
          lazy: async () => {
            const { SettingsPage } = await import("@/features/settings/SettingsPage");
            return {
              element: (
                <Allowed when={canChangeSettings}>
                  <SettingsPage />
                </Allowed>
              ),
            };
          },
        },
        { path: "*", element: <NotFound /> },
      ],
    },
  ];
}
