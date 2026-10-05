import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { CharonClient } from "@/api/client";
import { errorMessage, isApiError } from "@/api/errors";
import { SESSION_EXPIRED } from "@/api/QueryProvider";
import type { Principal } from "@/api/types";
import type { ValueStore } from "@/lib/storage";

export type AuthState =
  | { status: "loading" }
  | { status: "unreachable"; error: string }
  | { status: "signedOut"; error?: string }
  | { status: "signedIn"; principal: Principal };

interface AuthContextValue {
  state: AuthState;
  signIn(key: string): Promise<boolean>;
  signOut(reason?: string): void;
  /** Checks the saved key again, e.g. after Charon was unreachable. */
  retry(): Promise<void>;
}

type CheckResult = { principal: Principal } | { error: unknown };

/** No verdict on the key: Charon is down or restarting, or a proxy in front of it failed. */
export function isUnreachable(error: unknown): boolean {
  return !isApiError(error) || error.status >= 500;
}

/** What to show after checking the saved key as the app opens. */
export function stateOnOpen(result: CheckResult, hadKey: boolean): AuthState {
  if ("principal" in result) return { status: "signedIn", principal: result.principal };
  if (isUnreachable(result.error)) {
    return { status: "unreachable", error: errorMessage(result.error) };
  }
  return { status: "signedOut", error: hadKey ? SESSION_EXPIRED : undefined };
}

/** What to show after someone submits a key on the sign-in page. */
export function stateOnSignIn(result: CheckResult): AuthState {
  if ("principal" in result) return { status: "signedIn", principal: result.principal };
  const message = errorMessage(result.error);
  const error = isUnreachable(result.error) ? `Can't reach Charon: ${message}` : message;
  return { status: "signedOut", error };
}

const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  client: CharonClient;
  keys: ValueStore;
  children: ReactNode;
}

/** Validates the stored key with `/auth/me`; with auth disabled, everyone is signed in. */
export function AuthProvider({ client, keys, children }: AuthProviderProps) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  const check = useCallback(async (): Promise<CheckResult> => {
    try {
      return { principal: await client.me() };
    } catch (error) {
      if (isApiError(error, 401)) keys.clear();
      return { error };
    }
  }, [client, keys]);

  const open = useCallback(async () => {
    const hadKey = keys.get() !== null;
    return stateOnOpen(await check(), hadKey);
  }, [check, keys]);

  useEffect(() => {
    let active = true;
    open().then((next) => {
      if (active) setState(next);
    });
    return () => {
      active = false;
    };
  }, [open]);

  const retry = useCallback(async () => setState(await open()), [open]);

  const signIn = useCallback(
    async (key: string) => {
      keys.set(key.trim());
      const next = stateOnSignIn(await check());
      setState(next);
      return next.status === "signedIn";
    },
    [check, keys],
  );

  const signOut = useCallback(
    (reason?: string) => {
      keys.clear();
      setState({ status: "signedOut", error: reason });
    },
    [keys],
  );

  const value = useMemo(() => ({ state, signIn, signOut, retry }), [state, signIn, signOut, retry]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth must be used inside <AuthProvider>");
  return auth;
}

export function usePrincipal(): Principal {
  const { state } = useAuth();
  if (state.status !== "signedIn") throw new Error("usePrincipal needs a signed-in user");
  return state.principal;
}
