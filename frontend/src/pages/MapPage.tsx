import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Crosshair, RefreshCw } from 'lucide-react';
import { Api, errorMessage } from '../services/api';
import { ErrorBox, Loading } from '../components/Common';
import { IndiaMap, MapLegend } from '../maps/IndiaMap';
import { DateRangeSelector } from '../components/DateRangeSelector';
import { EMPTY_FILTERS, EventFilters, filtersToParams, type FilterState } from '../components/EventFilters';
import { useDateRange } from '../hooks/useDateRange';
import { DataStatusBadge } from '../components/Badges';

export default function MapPage() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { params: range } = useDateRange();
  const [f, setF] = useState<FilterState>({ ...EMPTY_FILTERS, state: params.get('state') ?? '', classification: params.get('classification') ?? '', risk_level: params.get('risk') ?? '' });
  const [click, setClick] = useState<{ lat: number; lon: number } | null>(null);
  const q = useQuery({ queryKey: ['events-map', range, f], queryFn: () => Api.events({ ...range, ...filtersToParams(f), limit: 2000 }) });
  const boundaries = useQuery({ queryKey: ['states-geojson'], queryFn: Api.statesGeoJson, staleTime: Infinity });
  const focus = useMemo(() => q.data?.items.find((e) => e.incident_id === params.get('focus')) ?? null, [q.data, params]);
  if (q.error) return <ErrorBox error={errorMessage(q.error)} />;
  const items = q.data?.items ?? [];
  const live = items.filter((e) => e.data_status === 'LIVE').length;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-extrabold tracking-tight">India Thermal Event Map</h1><p className="text-sm text-ink-500 dark:text-ink-400">Click anywhere on the map to analyse that location. Filter by state, district (all 788 OSM districts), date range, classification, risk, persistence, satellite, verification, industrial proximity and population exposure.</p></div>
        <div className="flex items-center gap-2 text-xs"><DataStatusBadge status="LIVE" /> {live} · <DataStatusBadge status="HISTORICAL" /> {items.length - live} <button className="btn-secondary text-xs" onClick={() => q.refetch()}><RefreshCw size={13} /> Refresh</button></div>
      </div>
      <DateRangeSelector />
      <div className="card p-3"><EventFilters value={f} onChange={setF} /></div>
      <div className="card p-2 relative">
        <div className="h-[70vh] min-h-[480px]">
          {q.isLoading ? <Loading text="Loading events…" /> : (
            <IndiaMap events={items} focus={focus} boundaries={boundaries.data} onMapClick={(lat, lon) => setClick({ lat, lon })} />
          )}
        </div>
        {click && (
          <div className="absolute bottom-4 left-4 z-[500] card p-3 text-xs flex items-center gap-2 shadow-lg">
            <Crosshair size={14} /> {click.lat.toFixed(4)}, {click.lon.toFixed(4)}
            <button className="btn-primary !py-1 !px-2 text-xs" onClick={() => nav(`/location-analysis?lat=${click.lat.toFixed(5)}&lon=${click.lon.toFixed(5)}`)}>Analyze Location</button>
            <button className="btn-ghost !py-1 !px-2 text-xs" onClick={() => setClick(null)}>✕</button>
          </div>
        )}
      </div>
      <div className="card p-3 flex flex-wrap items-center justify-between gap-2"><MapLegend /><span className="text-xs text-ink-500">{items.length} events shown · state outlines © OpenStreetMap contributors</span></div>
    </div>
  );
}
