import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { ValueStore } from "@/lib/storage";

export type Theme = "light" | "dark" | "system";

export const THEMES: Theme[] = ["light", "dark", "system"];

interface ThemeContextValue {
  theme: Theme;
  setTheme(theme: Theme): void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function parseTheme(value: string | null): Theme {
  return THEMES.includes(value as Theme) ? (value as Theme) : "system";
}

export function resolveDark(theme: Theme, prefersDark: boolean): boolean {
  return theme === "dark" || (theme === "system" && prefersDark);
}

interface ThemeProviderProps {
  store: ValueStore;
  children: ReactNode;
}

export function ThemeProvider({ store, children }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(() => parseTheme(store.get()));

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () =>
      document.documentElement.classList.toggle("dark", resolveDark(theme, media.matches));
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);

  const setTheme = useCallback(
    (next: Theme) => {
      store.set(next);
      setThemeState(next);
    },
    [store],
  );

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside <ThemeProvider>");
  return value;
}
