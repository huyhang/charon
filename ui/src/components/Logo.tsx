import { useId } from "react";
import { cn } from "@/lib/cn";

/** Charon's ferry: a boat and oar over the river. */
export function LogoMark({ className }: { className?: string }) {
  const id = useId();
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden className={cn("size-8", className)}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#8b7cf6" />
          <stop offset="1" stopColor="#5ed3e6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${id})`} />
      <path d="M19.6 6.8 13.4 18" stroke="#0b0d14" strokeWidth="2.1" strokeLinecap="round" />
      <path
        d="M6.8 17.4h18.4l-2.5 3.9a3.2 3.2 0 0 1-2.7 1.5h-8a3.2 3.2 0 0 1-2.7-1.5z"
        fill="#0b0d14"
      />
      <path
        d="M6 26.2c2.4-1.2 4.6-1.2 7 0s4.6 1.2 7 0 4.4-1.2 6 0"
        stroke="#0b0d14"
        strokeOpacity=".55"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      <span className="text-[15px] font-semibold tracking-tight">Charon</span>
    </div>
  );
}
