import { LogoMark } from "./Logo";

/** Full-screen placeholder while the session is checked or a page's code loads. */
export function Splash() {
  return (
    <div className="flex min-h-dvh items-center justify-center" aria-label="Loading">
      <LogoMark className="size-10 animate-pulse" />
    </div>
  );
}
