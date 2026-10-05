import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@/api/errors";
import { SignInPage } from "@/features/auth/SignInPage";
import { UnreachablePage } from "@/features/auth/UnreachablePage";
import { memoryStore } from "@/lib/storage";
import { createFakeClient } from "@/test/fakeClient";
import { ADMIN } from "@/test/factories";
import {
  AuthProvider,
  isUnreachable,
  stateOnOpen,
  stateOnSignIn,
  useAuth,
  type AuthState,
} from "./AuthProvider";

const unauthorized = () => new ApiError(401, { code: "unauthorized", message: "invalid API key" });
const offline = () => new TypeError("Failed to fetch");
const badGateway = () => new ApiError(502, { code: "http_error", message: "502 Bad Gateway" });

function Screen() {
  const { state, signOut, retry } = useAuth();
  if (state.status === "loading") return <p>loading</p>;
  if (state.status === "unreachable")
    return <UnreachablePage error={state.error} onRetry={retry} />;
  if (state.status === "signedOut") return <SignInPage />;
  return (
    <button type="button" onClick={() => signOut()}>
      signed in as {state.principal.name}
    </button>
  );
}

function setup(storedKey: string | null, me: () => Promise<typeof ADMIN>) {
  const keys = memoryStore(storedKey);
  const client = createFakeClient({ me });
  render(
    <AuthProvider client={client} keys={keys}>
      <Screen />
    </AuthProvider>,
  );
  return { keys, client };
}

describe("isUnreachable", () => {
  it.each<[string, unknown, boolean]>([
    ["network failure", offline(), true],
    ["proxy error", badGateway(), true],
    ["server error", new ApiError(500, { code: "internal_error", message: "boom" }), true],
    ["rejected key", unauthorized(), false],
    ["auth disabled", new ApiError(409, { code: "auth_disabled", message: "off" }), false],
  ])("%s -> %s", (_label, error, expected) => {
    expect(isUnreachable(error)).toBe(expected);
  });
});

describe("stateOnOpen", () => {
  it.each<[string, Parameters<typeof stateOnOpen>[0], boolean, AuthState]>([
    ["valid key", { principal: ADMIN }, true, { status: "signedIn", principal: ADMIN }],
    ["first visit", { error: unauthorized() }, false, { status: "signedOut", error: undefined }],
    [
      "saved key revoked",
      { error: unauthorized() },
      true,
      { status: "signedOut", error: "Your API key is no longer valid. Sign in again." },
    ],
    [
      "Charon down",
      { error: offline() },
      true,
      { status: "unreachable", error: "Failed to fetch" },
    ],
    [
      "Charon down, no key",
      { error: offline() },
      false,
      { status: "unreachable", error: "Failed to fetch" },
    ],
    [
      "proxy error",
      { error: badGateway() },
      true,
      { status: "unreachable", error: "502 Bad Gateway" },
    ],
  ])("%s", (_label, result, hadKey, expected) => {
    expect(stateOnOpen(result, hadKey)).toEqual(expected);
  });
});

describe("stateOnSignIn", () => {
  it.each<[string, Parameters<typeof stateOnSignIn>[0], AuthState]>([
    ["accepted", { principal: ADMIN }, { status: "signedIn", principal: ADMIN }],
    ["rejected", { error: unauthorized() }, { status: "signedOut", error: "invalid API key" }],
    [
      "Charon down",
      { error: offline() },
      { status: "signedOut", error: "Can't reach Charon: Failed to fetch" },
    ],
  ])("%s", (_label, result, expected) => {
    expect(stateOnSignIn(result)).toEqual(expected);
  });
});

describe("AuthProvider", () => {
  it.each([
    ["a valid stored key", "good", async () => ADMIN, /signed in as bootstrap-admin/],
    [
      "auth disabled and no key",
      null,
      async () => ({ ...ADMIN, name: "anonymous", auth_enabled: false }),
      /signed in as anonymous/,
    ],
  ])("signs in with %s", async (_, key, me, expected) => {
    setup(key, me);
    expect(await screen.findByRole("button", { name: expected })).toBeInTheDocument();
  });

  it("drops a stored key that is no longer valid, and says so", async () => {
    const { keys } = setup("revoked", async () => Promise.reject(unauthorized()));
    expect(await screen.findByLabelText("API key")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("no longer valid");
    expect(keys.get()).toBeNull();
  });

  it("explains that Charon is unreachable, keeps the key, and recovers on retry", async () => {
    const me = vi.fn<() => Promise<typeof ADMIN>>().mockRejectedValueOnce(offline());
    me.mockResolvedValue(ADMIN);
    const { keys } = setup("good", me);
    expect(await screen.findByRole("heading", { name: "Can't reach Charon" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Failed to fetch");
    expect(keys.get()).toBe("good");
    await userEvent.click(screen.getByRole("button", { name: /retry now/i }));
    expect(await screen.findByRole("button", { name: /signed in as/ })).toBeInTheDocument();
  });

  it("shows on the form that Charon is unreachable when signing in", async () => {
    const me = vi.fn<() => Promise<typeof ADMIN>>().mockRejectedValueOnce(unauthorized());
    me.mockRejectedValue(offline());
    setup(null, me);
    await userEvent.type(await screen.findByLabelText("API key"), "dev-key");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Can't reach Charon: Failed to fetch",
    );
  });

  it("signs in through the form and stores the key", async () => {
    const me = vi
      .fn<() => Promise<typeof ADMIN>>()
      .mockRejectedValueOnce(unauthorized())
      .mockResolvedValue(ADMIN);
    const { keys } = setup(null, me);
    await userEvent.type(await screen.findByLabelText("API key"), "  dev-key ");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("button", { name: /signed in as/ })).toBeInTheDocument();
    expect(keys.get()).toBe("dev-key");
  });

  it("shows why a key was rejected", async () => {
    setup(null, async () => Promise.reject(unauthorized()));
    await userEvent.type(await screen.findByLabelText("API key"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid API key");
  });

  it("signs out and forgets the key", async () => {
    const { keys } = setup("good", async () => ADMIN);
    await userEvent.click(await screen.findByRole("button", { name: /signed in as/ }));
    await waitFor(() => expect(screen.getByLabelText("API key")).toBeInTheDocument());
    expect(keys.get()).toBeNull();
  });
});
