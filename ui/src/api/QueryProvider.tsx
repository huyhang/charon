import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { isApiError } from "./errors";

export const SESSION_EXPIRED = "Your API key is no longer valid. Sign in again.";

export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (isApiError(error) && error.status < 500) return false;
  return failureCount < 2;
}

export function createQueryClient(onUnauthorized: () => void): QueryClient {
  const onError = (error: unknown) => {
    if (isApiError(error, 401)) onUnauthorized();
  };
  return new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: { queries: { retry: shouldRetry, staleTime: 1000 } },
  });
}

interface QueryProviderProps {
  onUnauthorized: () => void;
  children: ReactNode;
}

/** A revoked or rotated key signs the user out wherever it is first noticed. */
export function QueryProvider({ onUnauthorized, children }: QueryProviderProps) {
  const [client] = useState(() => createQueryClient(onUnauthorized));
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
