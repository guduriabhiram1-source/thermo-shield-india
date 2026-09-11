import { CalendarRange } from 'lucide-react';
import { RANGE_OPTIONS, useDateRange, type RangeKey } from '../hooks/useDateRange';

export function DateRangeSelector({ compact = false }: { compact?: boolean }) {
  const { range, from, to, setRange, setCustom } = useDateRange();
  const today = new Date().toISOString().slice(0, 10);
  const minDate = new Date(Date.now() - 366 * 86400000).toISOString().slice(0, 10);
  return (
    <div className={`flex flex-wrap items-center gap-2 ${compact ? '' : 'card p-3'}`} data-testid="date-range">
      <CalendarRange size={16} className="text-ink-400" />
      <select aria-label="Date range" className="input !w-auto" value={range} onChange={(e) => setRange(e.target.value as RangeKey)}>
        {RANGE_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
      </select>
      {range === 'custom' && (
        <>
          <input aria-label="From date" type="date" className="input !w-auto" min={minDate} max={today} value={from} onChange={(e) => setCustom(e.target.value, to)} />
          <span className="text-xs text-ink-500">to</span>
          <input aria-label="To date" type="date" className="input !w-auto" min={minDate} max={today} value={to} onChange={(e) => setCustom(from, e.target.value)} />
        </>
      )}
      <span className="text-[11px] text-ink-500">Historical data available: {minDate} → {today} (12-month limit)</span>
    </div>
  );
}
