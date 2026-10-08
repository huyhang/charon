import type { ProviderInfo } from "@/api/types";
import { cn } from "@/lib/cn";

/** Providers' own logos, bundled unmodified, as their terms require. */
const LOGOS: Record<string, string> = { tmdb: "/tmdb-logo.svg" };

/** Credits a metadata provider wherever its data is shown: its logo, linking to its site. */
export function ProviderCredit({
  provider,
  className,
}: {
  provider: ProviderInfo;
  className?: string;
}) {
  const logo = LOGOS[provider.id];
  return (
    <p className={cn("flex items-center gap-2 text-[11px] text-muted-foreground", className)}>
      Titles from
      <a
        href={provider.url}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center font-medium text-foreground hover:underline"
      >
        {logo ? <img src={logo} alt={provider.name} className="h-2.5 w-auto" /> : provider.name}
      </a>
    </p>
  );
}

/** The provider's required notice, with its logo, for an About or credits page. */
export function ProviderNotice({ provider }: { provider: ProviderInfo }) {
  const logo = LOGOS[provider.id];
  return (
    <div className="flex items-start gap-3 rounded-lg border p-3">
      {logo && (
        <a href={provider.url} target="_blank" rel="noreferrer" className="mt-0.5 shrink-0">
          <img src={logo} alt={provider.name} className="h-3 w-auto" />
        </a>
      )}
      <p className="text-xs text-muted-foreground">{provider.notice}</p>
    </div>
  );
}
