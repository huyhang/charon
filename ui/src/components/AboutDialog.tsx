import { useMetadataProviders } from "@/api/queries";
import { LogoMark } from "./Logo";
import { ProviderNotice } from "./ProviderCredit";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "./ui/dialog";

/** What Charon is, and credit for the data it shows from metadata providers (e.g. TMDB). */
export function AboutDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
}) {
  const providers = useMetadataProviders();
  const credits = providers.data ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <LogoMark className="size-5" /> About Charon
          </DialogTitle>
          <DialogDescription>
            Downloads through Download Station, then renamed and filed by your rules.
          </DialogDescription>
        </DialogHeader>
        {credits.length > 0 && (
          <section className="space-y-2" aria-label="Data sources">
            <h3 className="text-sm font-medium">Data sources</h3>
            {credits.map((provider) => (
              <ProviderNotice key={provider.id} provider={provider} />
            ))}
          </section>
        )}
      </DialogContent>
    </Dialog>
  );
}
