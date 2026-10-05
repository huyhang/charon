import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { memoryStore } from "@/lib/storage";
import {
  parseTheme,
  resolveDark,
  ThemeProvider,
  THEMES,
  useTheme,
  type Theme,
} from "./ThemeProvider";

describe("parseTheme", () => {
  it.each<[string | null, Theme]>([
    ["light", "light"],
    ["dark", "dark"],
    ["system", "system"],
    ["neon", "system"],
    [null, "system"],
  ])("%s -> %s", (value, expected) => {
    expect(parseTheme(value)).toBe(expected);
  });
});

describe("resolveDark", () => {
  it.each<[Theme, boolean, boolean]>([
    ["dark", false, true],
    ["light", true, false],
    ["system", true, true],
    ["system", false, false],
  ])("%s (prefers dark %s) -> %s", (theme, prefersDark, expected) => {
    expect(resolveDark(theme, prefersDark)).toBe(expected);
  });
});

/** A prefers-color-scheme query whose answer the test can change, like an OS switching modes. */
function controllableDarkMode(initial: boolean) {
  const listeners = new Set<() => void>();
  const media = {
    matches: initial,
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
  };
  const original = window.matchMedia;
  window.matchMedia = (() => media) as unknown as typeof window.matchMedia;
  return {
    switchTo(dark: boolean) {
      media.matches = dark;
      act(() => listeners.forEach((listener) => listener()));
    },
    listening: () => listeners.size,
    restore: () => {
      window.matchMedia = original;
    },
  };
}

function ThemeSwitch() {
  const { theme, setTheme } = useTheme();
  return (
    <>
      <output aria-label="theme">{theme}</output>
      {THEMES.map((option) => (
        <button key={option} type="button" onClick={() => setTheme(option)}>
          {option}
        </button>
      ))}
    </>
  );
}

const isDark = () => document.documentElement.classList.contains("dark");

describe("ThemeProvider", () => {
  afterEach(() => document.documentElement.classList.remove("dark"));

  it.each<[string | null, boolean, boolean]>([
    ["dark", false, true],
    ["light", true, false],
    ["system", true, true],
    ["system", false, false],
    [null, true, true],
  ])("stored %s with the OS preferring dark=%s -> dark=%s", (stored, prefersDark, dark) => {
    const media = controllableDarkMode(prefersDark);
    render(
      <ThemeProvider store={memoryStore(stored)}>
        <ThemeSwitch />
      </ThemeProvider>,
    );
    expect(isDark()).toBe(dark);
    media.restore();
  });

  it("follows the OS while on system, and stops listening when unmounted", () => {
    const media = controllableDarkMode(false);
    const { unmount } = render(
      <ThemeProvider store={memoryStore("system")}>
        <ThemeSwitch />
      </ThemeProvider>,
    );
    media.switchTo(true);
    expect(isDark()).toBe(true);
    media.switchTo(false);
    expect(isDark()).toBe(false);
    unmount();
    expect(media.listening()).toBe(0);
    media.restore();
  });

  it.each<[Theme, boolean]>([
    ["dark", true],
    ["light", false],
    ["system", false],
  ])("switching to %s applies it and remembers it", async (theme, dark) => {
    const store = memoryStore("light");
    render(
      <ThemeProvider store={store}>
        <ThemeSwitch />
      </ThemeProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: theme }));
    expect(screen.getByLabelText("theme")).toHaveTextContent(theme);
    expect(isDark()).toBe(dark);
    expect(store.get()).toBe(theme);
  });

  it("says what's missing when used outside the provider", () => {
    const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<ThemeSwitch />)).toThrow("useTheme must be used inside <ThemeProvider>");
    quiet.mockRestore();
  });
});
