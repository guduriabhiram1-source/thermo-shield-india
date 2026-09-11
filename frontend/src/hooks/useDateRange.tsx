import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type RangeKey = 'live' | '24h' | '3d' | '7d' | '30d' | '3m' | '6m' | '12m' | 'custom';
export const RANGE_OPTIONS: { key: RangeKey; label: string }[] = [
  { key: 'live', label: 'LIVE' }, { key: '24h', label: 'Last 24 hours' }, { key: '3d', label: 'Last 3 days' }, { key: '7d', label: 'Last 7 days' }, { key: '30d', label: 'Last 30 days' },
  { key: '3m', label: 'Last 3 months' }, { key: '6m', label: 'Last 6 months' }, { key: '12m', label: 'Last 12 months' }, { key: 'custom', label: 'Custom range' },
];

interface Ctx { range: RangeKey; from: string; to: string; setRange: (r: RangeKey) => void; setCustom: (from: string, to: string) => void; params: Record<string, string | undefined>; label: string }
const C = createContext<Ctx | null>(null);
const KEY = 'tsi-range';

export function DateRangeProvider({ children }: { children: ReactNode }) {
  const [range, setRangeState] = useState<RangeKey>(() => { try { return (localStorage.getItem(KEY) as RangeKey) || '7d'; } catch { return '7d'; } });
  const [from, setFrom] = useState(() => { try { return localStorage.getItem(KEY + '-from') || ''; } catch { return ''; } });
  const [to, setTo] = useState(() => { try { return localStorage.getItem(KEY + '-to') || ''; } catch { return ''; } });
  useEffect(() => { try { localStorage.setItem(KEY, range); localStorage.setItem(KEY + '-from', from); localStorage.setItem(KEY + '-to', to); } catch { /* ignore */ } }, [range, from, to]);
  const setRange = useCallback((r: RangeKey) => setRangeState(r), []);
  const setCustom = useCallback((f: string, t: string) => { setFrom(f); setTo(t); setRangeState('custom'); }, []);
  const params = useMemo(() => (range === 'custom' ? { range: undefined, date_from: from ? new Date(from).toISOString() : undefined, date_to: to ? new Date(to + 'T23:59:59').toISOString() : undefined } : { range }), [range, from, to]);
  const label = useMemo(() => (range === 'custom' ? `${from || '…'} → ${to || '…'}` : RANGE_OPTIONS.find((o) => o.key === range)?.label ?? range), [range, from, to]);
  const value = useMemo(() => ({ range, from, to, setRange, setCustom, params, label }), [range, from, to, setRange, setCustom, params, label]);
  return <C.Provider value={value}>{children}</C.Provider>;
}

export function useDateRange() {
  const v = useContext(C);
  if (!v) throw new Error('useDateRange outside DateRangeProvider');
  return v;
}
