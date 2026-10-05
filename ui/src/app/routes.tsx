import type { ReactNode } from "react";
import { Navigate, type RouteObject } from "react-router";
import { usePrincipal } from "@/auth/AuthProvider";
import { EmptyState } from "@/components/EmptyState";
import { Splash } from "@/components/Splash";
import { Button } from "@/components/ui/button";
import { DownloadsPage } from "@/features/downloads/DownloadsPage";
import { CompassIcon } from "lucide-react";
import { Link } from "react-router";
import { AppShell } from "./AppShell";
import { canManageKeys } from "./nav";

function AdminOnly({ children }: { children: ReactNode }) {
  return canManageKeys(usePrincipal()) ? children : <Navigate to="/downloads" replace />;
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
          path: "rules",
          lazy: async () => ({ Component: (await import("@/features/rules/RulesPage")).RulesPage }),
        },
        {
          path: "keys",
          lazy: async () => {
            const { KeysPage } = await import("@/features/keys/KeysPage");
            return {
              element: (
                <AdminOnly>
                  <KeysPage />
                </AdminOnly>
              ),
            };
          },
        },
        { path: "*", element: <NotFound /> },
      ],
    },
  ];
}
