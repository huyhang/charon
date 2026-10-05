import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { ClientProvider } from "@/api/context";
import type { Principal } from "@/api/types";
import { AuthProvider, useAuth } from "@/auth/AuthProvider";
import { memoryStore } from "@/lib/storage";
import { ThemeProvider } from "@/theme/ThemeProvider";
import { createFakeClient, type FakeClient } from "./fakeClient";
import { ADMIN } from "./factories";

interface RenderOptions {
  client?: FakeClient;
  principal?: Principal;
  route?: string;
  /** Route pattern the element is mounted at, e.g. "/downloads/:jobId?". */
  path?: string;
}

/** Renders `ui` signed in, with every provider the app has, around an injected fake client. */
export async function renderWithApp(ui: ReactElement, options: RenderOptions = {}) {
  const client = options.client ?? createFakeClient();
  client.me.mockResolvedValue(options.principal ?? ADMIN);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const router = createMemoryRouter([{ path: options.path ?? "*", element: ui }], {
    initialEntries: [options.route ?? "/"],
  });
  const result = render(
    <ThemeProvider store={memoryStore()}>
      <ClientProvider client={client}>
        <AuthProvider client={client} keys={memoryStore("key")}>
          <QueryClientProvider client={queryClient}>
            <SignedIn>
              <RouterProvider router={router} />
            </SignedIn>
          </QueryClientProvider>
        </AuthProvider>
      </ClientProvider>
    </ThemeProvider>,
  );
  await screen.findByTestId("signed-in");
  return { ...result, client, router, queryClient };
}

function SignedIn({ children }: { children: ReactElement }) {
  const { state } = useAuth();
  return state.status === "signedIn" ? <div data-testid="signed-in">{children}</div> : null;
}
