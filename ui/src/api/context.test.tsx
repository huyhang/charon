import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { createFakeClient } from "@/test/fakeClient";
import { ClientProvider, useClient } from "./context";

describe("useClient", () => {
  it("returns the injected client", () => {
    const client = createFakeClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <ClientProvider client={client}>{children}</ClientProvider>
    );
    expect(renderHook(() => useClient(), { wrapper }).result.current).toBe(client);
  });

  it("says what's missing when used outside the provider", () => {
    const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useClient())).toThrow(
      "useClient must be used inside <ClientProvider>",
    );
    quiet.mockRestore();
  });
});
