import React from "react";

export type Theme = "light" | "dark" | "system";

type ThemeContextValue = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  resolvedTheme: "light" | "dark";
};

const ThemeContext = React.createContext<ThemeContextValue | undefined>(
  undefined
);

type ThemeProviderProps = {
  children: React.ReactNode;
  defaultTheme?: Theme;
  storageKey?: string;
};

export function ThemeProvider({
  children,
  defaultTheme = "system",
  storageKey = "theme"
}: ThemeProviderProps) {
  const [theme, setTheme] = React.useState<Theme>(() => {
    const stored = localStorage.getItem(storageKey) as Theme | null;
    return stored ?? defaultTheme;
  });

  const getSystemIsDark = () =>
    window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;

  const resolvedTheme = React.useMemo<"light" | "dark">(() => {
    if (theme === "system") return getSystemIsDark() ? "dark" : "light";
    return theme;
  }, [theme]);

  // Apply class to <html>
  React.useEffect(() => {
    const root = document.documentElement;
    if (resolvedTheme === "dark") root.classList.add("dark");
    else root.classList.remove("dark");
    localStorage.setItem(storageKey, theme);
  }, [resolvedTheme, storageKey, theme]);

  // Watch system preference changes when theme === 'system'
  React.useEffect(() => {
    if (theme !== "system") return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const root = document.documentElement;
      if (mql.matches) root.classList.add("dark");
      else root.classList.remove("dark");
    };
    if (mql.addEventListener) mql.addEventListener("change", onChange);
    else mql.addListener(onChange);
    return () => {
      if (mql.removeEventListener) mql.removeEventListener("change", onChange);
      else mql.removeListener(onChange);
    };
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
