import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Api, errorMessage } from '../services/api';
import { Empty, ErrorBox, Loading } from '../components/Common';
import { IncidentCard } from '../components/IncidentCard';
import { DateRangeSelector } from '../components/DateRangeSelector';
import { EMPTY_FILTERS, EventFilters, filtersToParams, type FilterState } from '../components/EventFilters';
import { useDateRange } from '../hooks/useDateRange';

export default function EventsPage({ preset, title = 'Thermal Events', subtitle }: { preset?: Partial<FilterState>; title?: string; subtitle?: string }) {
  const [params] = useSearchParams();
  const { params: range } = useDateRange();
  const [f, setF] = useState<FilterState>({ ...EMPTY_FILTERS, q: params.get('q') ?? '', state: params.get('state') ?? '', district: params.get('district') ?? '', classification: params.get('classification') ?? '', ...preset });
  const [page, setPage] = useState(0);
  const limit = 24;
  const q = useQuery({ queryKey: ['events', range, f, page], queryFn: () => Api.events({ ...range, ...filtersToParams(f), limit, offset: page * limit }) });
  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-extrabold tracking-tight">{title}</h1><p className="text-sm text-ink-500 dark:text-ink-400">{subtitle ?? 'Every incident is a spatio-temporal cluster of real NASA FIRMS detections (TSI-IND-YYYY-NNNNNN). Live and historical incidents are always labelled.'}</p></div>
      <DateRangeSelector />
      <div className="card p-3 space-y-2">
        <input className="input" placeholder="Search incident ID, state, district, locality, classification…" value={f.q} onChange={(e) => { setF({ ...f, q: e.target.value }); setPage(0); }} aria-label="Search events" />
        <EventFilters value={f} onChange={(v) => { setF(v); setPage(0); }} />
      </div>
      {q.error && <ErrorBox error={errorMessage(q.error)} />}
      {q.isLoading && <Loading text="Loading events…" />}
      {q.data && (
        <>
          <div className="text-xs text-ink-500">{q.data.total} incident(s) · showing {page * limit + 1}–{Math.min((page + 1) * limit, q.data.total)} · history window {new Date(q.data.history_window.from).toLocaleDateString('en-IN')} → {new Date(q.data.history_window.to).toLocaleDateString('en-IN')}</div>
          {q.data.items.length === 0 ? <Empty text="No thermal events match the selected range and filters. (No observations found — not a measurement of zero activity.)" /> : (
            <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-3">{q.data.items.map((e) => <IncidentCard key={e.incident_id} e={e} />)}</div>
          )}
          <div className="flex items-center gap-2"><button className="btn-secondary text-xs" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>← Previous</button><button className="btn-secondary text-xs" disabled={(page + 1) * limit >= q.data.total} onClick={() => setPage((p) => p + 1)}>Next →</button></div>
        </>
      )}
    </div>
  );
}
