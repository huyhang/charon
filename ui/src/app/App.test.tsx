import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { ApiError } from "@/api/errors";
import { SESSION_CHECK_MS } from "@/api/queries";
import type { Principal } from "@/api/types";
import { memoryStore } from "@/lib/storage";
import { createFakeClient, type FakeClient } from "@/test/fakeClient";
import { ADMIN, CLIENT } from "@/test/factories";
import { App } from "./App";

const ANONYMOUS: Principal = {
  name: "anonymous",
  role: "admin",
  key_id: null,
  auth_enabled: false,
};
const revoked = () => new ApiError(401, { code: "unauthorized", message: "invalid API key" });
const never = <T,>() => new Promise<T>(() => {});

interface Options {
  url?: string;
  client?: FakeClient;
  storedKey?: string | null;
  devTools?: ReactNode;
  signInHint?: string;
}

function renderApp({
  url = "/",
  client = createFakeClient(),
  storedKey = "dev-key",
  ...rest
}: Options = {}) {
  window.history.replaceState(null, "", url);
  const keys = memoryStore(storedKey);
  render(<App client={client} keys={keys} themeStore={memoryStore()} {...rest} />);
  return { client, keys };
}

const path = () => `${window.location.pathname}${window.location.search}`;

describe("App", () => {
  afterEach(() => vi.useRealTimers());

  it.each<[string, () => Promise<Principal>, string | null, () => HTMLElement]>([
    ["checking the saved key", never, "dev-key", () => screen.getByLabelText("Loading")],
    [
      "nobody signed in yet",
      async () => Promise.reject(revoked()),
      null,
      () => screen.getByRole("heading", { name: "Welcome to Charon" }),
    ],
    [
      "Charon unreachable",
      async () => Promise.reject(new TypeError("Failed to fetch")),
      "dev-key",
      () => screen.getByRole("heading", { name: "Can't reach Charon" }),
    ],
    [
      "a valid key",
      async () => ADMIN,
      "dev-key",
      () => screen.getByRole("heading", { name: "Downloads" }),
    ],
  ])("shows the right screen for %s", async (_label, me, storedKey, screenShown) => {
    renderApp({ client: createFakeClient({ me }), storedKey });
    await waitFor(() => expect(screenShown()).toBeInTheDocument());
  });

  it.each<[string | undefined, boolean]>([
    ["Dev stack: the admin key is dev-key", true],
    [undefined, false],
  ])("sign-in hint %j shown=%s", async (signInHint, shown) => {
    const client = createFakeClient({ me: async () => Promise.reject(revoked()) });
    renderApp({ client, storedKey: null, signInHint });
    await screen.findByRole("heading", { name: "Welcome to Charon" });
    expect(screen.queryByText("Dev stack: the admin key is dev-key") !== null).toBe(shown);
  });

  it.each<[string, Principal, string, string]>([
    ["/", ADMIN, "Downloads", "/downloads"],
    ["/downloads", CLIENT, "Downloads", "/downloads"],
    ["/rules", ADMIN, "Rules", "/rules"],
    ["/keys", ADMIN, "API keys", "/keys"],
    ["/keys", CLIENT, "Downloads", "/downloads"],
    ["/keys", ANONYMOUS, "Downloads", "/downloads"],
  ])("%s as %j shows %s at %s", async (url, principal, heading, landed) => {
    renderApp({ url, client: createFakeClient({ me: async () => principal }) });
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
    expect(path()).toBe(landed);
  });

  it("explains an unknown address and leads back to downloads", async () => {
    renderApp({ url: "/nowhere" });
    expect(await screen.findByText("Lost on the river")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Back to downloads" }));
    expect(await screen.findByRole("heading", { name: "Downloads" })).toBeInTheDocument();
    expect(path()).toBe("/downloads");
  });

  it("signs out with an explanation when a request finds the key revoked", async () => {
    const client = createFakeClient({ listDownloads: async () => Promise.reject(revoked()) });
    const { keys } = renderApp({ client });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your API key is no longer valid. Sign in again.",
    );
    expect(screen.getByLabelText("API key")).toBeInTheDocument();
    expect(keys.get()).toBeNull();
  });

  it("notices a revoked key even on a page that polls nothing", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const me = vi.fn<() => Promise<Principal>>().mockResolvedValueOnce(ADMIN);
    me.mockRejectedValue(revoked());
    renderApp({ url: "/rules", client: createFakeClient({ me }) });
    await screen.findByRole("heading", { name: "Rules" });
    await act(() => vi.advanceTimersByTimeAsync(SESSION_CHECK_MS));
    expect(await screen.findByRole("alert")).toHaveTextContent("no longer valid");
  });

  it("renders development tools inside the signed-in app", async () => {
    renderApp({ devTools: <p>simulator here</p> });
    expect(await screen.findByText("simulator here")).toBeInTheDocument();
  });
});
