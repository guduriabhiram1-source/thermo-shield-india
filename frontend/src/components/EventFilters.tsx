import { useQuery } from '@tanstack/react-query';
import { Filter, X } from 'lucide-react';
import { Api } from '../services/api';
import { CLASSES, PERSISTENCE, RISKS, titleCase } from '../utils/format';

export interface FilterState { state: string; district: string; classification: string; risk_level: string; persistence: string; satellite: string; verified: string; data_status: string; industrial_km: string; min_population: string; q: string; sort: string }
export const EMPTY_FILTERS: FilterState = { state: '', district: '', classification: '', risk_level: '', persistence: '', satellite: '', verified: '', data_status: '', industrial_km: '', min_population: '', q: '', sort: 'priority' };

export function filtersToParams(f: FilterState) {
  const p: Record<string, string | number | undefined> = {};
  for (const [k, v] of Object.entries(f)) if (v) p[k] = k === 'industrial_km' || k === 'min_population' ? Number(v) : v;
  return p;
}

export function EventFilters({ value, onChange, compact = false }: { value: FilterState; onChange: (f: FilterState) => void; compact?: boolean }) {
  const states = useQuery({ queryKey: ['states'], queryFn: Api.states, staleTime: Infinity });
  const districts = useQuery({ queryKey: ['districts', value.state], queryFn: () => Api.districts(value.state), enabled: !!value.state, staleTime: Infinity });
  const set = (k: keyof FilterState, v: string) => onChange({ ...value, [k]: v, ...(k === 'state' ? { district: '' } : {}) });
  const districtOptions = [...(districts.data?.districts.map((d) => d.name) ?? []), ...(districts.data?.districts_in_events_not_in_osm_list ?? [])];
  return (
    <div className={`grid gap-2 ${compact ? 'grid-cols-2 md:grid-cols-3' : 'grid-cols-2 md:grid-cols-4 xl:grid-cols-6'}`} data-testid="event-filters">
      <label className="text-xs"><span className="label">State / UT</span>
        <select className="input" value={value.state} onChange={(e) => set('state', e.target.value)} aria-label="State filter"><option value="">All states ({states.data?.length ?? 36})</option>{states.data?.map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}</select></label>
      <label className="text-xs"><span className="label">District</span>
        <select className="input" value={value.district} onChange={(e) => set('district', e.target.value)} disabled={!value.state} aria-label="District filter"><option value="">{value.state ? `All districts (${districtOptions.length})` : 'Select a state first'}</option>{districtOptions.map((d) => <option key={d} value={d}>{d}</option>)}</select></label>
      <label className="text-xs"><span className="label">Data</span>
        <select className="input" value={value.data_status} onChange={(e) => set('data_status', e.target.value)} aria-label="Data status filter"><option value="">Live + historical</option><option value="LIVE">🟢 LIVE only</option><option value="HISTORICAL">🔵 HISTORICAL only</option></select></label>
      <label className="text-xs"><span className="label">Classification</span>
        <select className="input" value={value.classification} onChange={(e) => set('classification', e.target.value)} aria-label="Classification filter"><option value="">All</option>{CLASSES.map((c) => <option key={c} value={c}>{titleCase(c)}</option>)}</select></label>
      <label className="text-xs"><span className="label">Risk</span>
        <select className="input" value={value.risk_level} onChange={(e) => set('risk_level', e.target.value)} aria-label="Risk filter"><option value="">All</option>{RISKS.map((r) => <option key={r} value={r}>{r}</option>)}<option value="HIGH,CRITICAL">HIGH + CRITICAL</option></select></label>
      <label className="text-xs"><span className="label">Persistence</span>
        <select className="input" value={value.persistence} onChange={(e) => set('persistence', e.target.value)} aria-label="Persistence filter"><option value="">All</option>{PERSISTENCE.map((p) => <option key={p} value={p}>{titleCase(p)}</option>)}</select></label>
      <label className="text-xs"><span className="label">Satellite</span>
        <select className="input" value={value.satellite} onChange={(e) => set('satellite', e.target.value)} aria-label="Satellite filter"><option value="">All</option><option value="N">Suomi NPP (N)</option><option value="N20">NOAA-20 (N20)</option><option value="N21">NOAA-21 (N21)</option><option value="Aqua">Aqua (MODIS)</option><option value="Terra">Terra (MODIS)</option></select></label>
      <label className="text-xs"><span className="label">Verification</span>
        <select className="input" value={value.verified} onChange={(e) => set('verified', e.target.value)} aria-label="Verification filter"><option value="">All</option><option value="verified">Verified</option><option value="unverified">Unverified</option></select></label>
      <label className="text-xs"><span className="label">Industrial proximity ≤ km</span><input className="input" type="number" min={0} step={0.5} value={value.industrial_km} onChange={(e) => set('industrial_km', e.target.value)} placeholder="any" /></label>
      <label className="text-xs"><span className="label">Min. est. population exposure</span><input className="input" type="number" min={0} step={100} value={value.min_population} onChange={(e) => set('min_population', e.target.value)} placeholder="any" /></label>
      <label className="text-xs"><span className="label">Sort</span>
        <select className="input" value={value.sort} onChange={(e) => set('sort', e.target.value)} aria-label="Sort"><option value="priority">Priority</option><option value="risk">Risk</option><option value="recent">Most recent</option><option value="frp">Peak FRP</option><option value="population">Population exposure</option><option value="persistence">Persistence</option></select></label>
      <div className="flex items-end gap-1"><button className="btn-secondary text-xs" onClick={() => onChange({ ...EMPTY_FILTERS })}><X size={13} /> Clear</button><span className="text-[11px] text-ink-400 inline-flex items-center gap-1"><Filter size={11} /> filters</span></div>
    </div>
  );
}
