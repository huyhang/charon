import { ArrowRightIcon, KeyRoundIcon, Loader2Icon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useAuth } from "@/auth/AuthProvider";
import { LogoMark } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function SignInPage({ hint }: { hint?: string }) {
  const { state, signIn } = useAuth();
  const [key, setKey] = useState("");
  const [pending, setPending] = useState(false);
  const error = state.status === "signedOut" ? state.error : undefined;

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!key.trim()) return;
    setPending(true);
    await signIn(key);
    setPending(false);
  };

  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden px-4">
      <div
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-1/2 size-[40rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-river opacity-[0.07] blur-3xl"
      />
      <div className="relative w-full max-w-sm animate-in duration-500 fade-in slide-in-from-bottom-4">
        <div className="mb-8 flex flex-col items-center gap-4 text-center">
          <LogoMark className="size-12 drop-shadow-[0_8px_24px_rgb(139_124_246/0.35)]" />
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">Welcome to Charon</h1>
            <p className="text-sm text-muted-foreground">Downloads, renamed and filed for you.</p>
          </div>
        </div>
        <form
          onSubmit={onSubmit}
          className="space-y-4 rounded-2xl border bg-card/80 p-6 shadow-2xl backdrop-blur"
        >
          <div className="space-y-2">
            <Label htmlFor="api-key">API key</Label>
            <div className="relative">
              <KeyRoundIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="api-key"
                type="password"
                autoComplete="current-password"
                autoFocus
                placeholder="chk_…"
                value={key}
                onChange={(event) => setKey(event.target.value)}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? "api-key-error" : undefined}
                className="h-10 pl-9 font-mono"
              />
            </div>
            {error && (
              <p id="api-key-error" role="alert" className="text-xs text-destructive">
                {error}
              </p>
            )}
          </div>
          <Button type="submit" className="h-10 w-full" disabled={pending || !key.trim()}>
            {pending ? <Loader2Icon className="animate-spin" /> : <ArrowRightIcon />}
            Sign in
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            Use the admin key (<code className="font-mono">CHARON_ADMIN_API_KEY</code>) or a key
            issued to you. It stays in this browser.
          </p>
          {hint && <p className="text-center text-xs text-primary">{hint}</p>}
        </form>
      </div>
    </div>
  );
}
