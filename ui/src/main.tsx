import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { createHttpClient } from "@/api/httpClient";
import { App } from "@/app/App";
import { localStore } from "@/lib/storage";
import "./styles.css";

const keys = localStore("charon.apiKey");
const client = createHttpClient({ getKey: () => keys.get() });

// Compiled out of production builds: `import.meta.env.DEV` is false there.
const SimulatorPanel = import.meta.env.DEV
  ? lazy(() => import("@/features/dev/SimulatorPanel"))
  : null;
const devTools = SimulatorPanel && (
  <Suspense>
    <SimulatorPanel />
  </Suspense>
);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App
      client={client}
      keys={keys}
      themeStore={localStore("charon.theme")}
      devTools={devTools}
      signInHint={import.meta.env.DEV ? "Dev stack: the admin key is dev-key" : undefined}
    />
  </StrictMode>,
);
