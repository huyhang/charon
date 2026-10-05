import { Toaster as Sonner } from "sonner";
import { useTheme } from "@/theme/ThemeProvider";

export function Toaster() {
  const { theme } = useTheme();
  return (
    <Sonner
      theme={theme}
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast: "!rounded-xl !border-border !bg-popover !text-popover-foreground !shadow-2xl",
          description: "!text-muted-foreground",
        },
      }}
    />
  );
}
