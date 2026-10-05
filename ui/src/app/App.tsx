import { useMemo, type ReactNode } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";
import type { CharonClient } from "@/api/client";
import { ClientProvider } from "@/api/context";
import { QueryProvider, SESSION_EXPIRED } from "@/api/QueryProvider";
import { AuthProvider, useAuth } from "@/auth/AuthProvider";
import { Splash } from "@/components/Splash";
import { Toaster } from "@/components/ui/sonner";
import { SignInPage } from "@/features/auth/SignInPage";
import { UnreachablePage } from "@/features/auth/UnreachablePage";
import type { ValueStore } from "@/lib/storage";
import { ThemeProvider } from "@/theme/ThemeProvider";
import { routes } from "./routes";

export interface AppProps {
  client: CharonClient;
  keys: ValueStore;
  themeStore: ValueStore;
  /** Extra UI for development, e.g. the simulator panel. */
  devTools?: ReactNode;
  signInHint?: string;
}

function SignedInApp({ devTools }: { devTools?: ReactNode }) {
  const router = useMemo(() => createBrowserRouter(routes(devTools)), [devTools]);
  return <RouterProvider router={router} />;
}

function Gate({ devTools, signInHint }: Pick<AppProps, "devTools" | "signInHint">) {
  const { state, signOut, retry } = useAuth();
  if (state.status === "loading") return <Splash />;
  if (state.status === "unreachable")
    return <UnreachablePage error={state.error} onRetry={retry} />;
  if (state.status === "signedOut") return <SignInPage hint={signInHint} />;
  return (
    <QueryProvider
      key={state.principal.key_id ?? state.principal.name}
      onUnauthorized={() => signOut(SESSION_EXPIRED)}
    >
      <SignedInApp devTools={devTools} />
    </QueryProvider>
  );
}

export function App({ client, keys, themeStore, devTools, signInHint }: AppProps) {
  return (
    <ThemeProvider store={themeStore}>
      <ClientProvider client={client}>
        <AuthProvider client={client} keys={keys}>
          <Gate devTools={devTools} signInHint={signInHint} />
          <Toaster />
        </AuthProvider>
      </ClientProvider>
    </ThemeProvider>
  );
}
