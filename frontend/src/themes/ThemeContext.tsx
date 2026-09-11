import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

type Theme = 'light' | 'dark';
interface ThemeCtx { theme: Theme; toggle: () => void; setTheme: (t: Theme) => void; isDark: boolean }
const Ctx = createContext<ThemeCtx | null>(null);
const KEY = 'tsi-theme';

function initial(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch { /* ignore */ }
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(initial);
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    document.documentElement.style.colorScheme = theme;
    try { localStorage.setItem(KEY, theme); } catch { /* ignore */ }
  }, [theme]);
  const setTheme = useCallback((t: Theme) => setThemeState(t), []);
  const toggle = useCallback(() => setThemeState((t) => (t === 'dark' ? 'light' : 'dark')), []);
  const value = useMemo(() => ({ theme, toggle, setTheme, isDark: theme === 'dark' }), [theme, toggle, setTheme]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useTheme outside ThemeProvider');
  return v;
}

export function useChartColors() {
  const { isDark } = useTheme();
  return useMemo(() => ({
    grid: isDark ? '#1e293b' : '#e2e8f0', axis: isDark ? '#94a3b8' : '#64748b', text: isDark ? '#e2e8f0' : '#0f172a', tooltipBg: isDark ? '#0f172a' : '#ffffff', tooltipBorder: isDark ? '#334155' : '#e2e8f0',
    series: ['#f43f5e', '#f97316', '#eab308', '#22c55e', '#0ea5e9', '#8b5cf6', '#ec4899', '#14b8a6', '#64748b', '#a3e635'],
    risk: { LOW: '#22c55e', MODERATE: '#a3e635', MEDIUM: '#eab308', HIGH: '#f97316', CRITICAL: '#ef4444' } as Record<string, string>,
  }), [isDark]);
}
