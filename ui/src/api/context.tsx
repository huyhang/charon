import { createContext, useContext, type ReactNode } from "react";
import type { CharonClient } from "./client";

const ClientContext = createContext<CharonClient | null>(null);

export function ClientProvider({
  client,
  children,
}: {
  client: CharonClient;
  children: ReactNode;
}) {
  return <ClientContext.Provider value={client}>{children}</ClientContext.Provider>;
}

export function useClient(): CharonClient {
  const client = useContext(ClientContext);
  if (!client) throw new Error("useClient must be used inside <ClientProvider>");
  return client;
}
