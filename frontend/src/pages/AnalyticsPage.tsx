import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Api, errorMessage } from '../services/api';
import { ErrorBox, InfoBox, Loading, Section } from '../components/Common';
import { DateRangeSelector } from '../components/DateRangeSelector';
import { useDateRange } from '../hooks/useDateRange';
import { fmtNum } from '../utils/format';

export default function AnalyticsPage() {
  const { params, label } = useDateRange();
  const q = useQuery({ queryKey: ['india', params], queryFn: () => Api.india(params) });
  if (q.error) return <ErrorBox error={errorMessage(q.error)} />;
  if (!q.data) return <Loading text="Loading state analytics…" />;
  const n = q.data.national;
  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-extrabold tracking-tight">State &amp; UT Analytics</h1><p className="text-sm text-ink-500 dark:text-ink-400">All 36 states and union territories · range: {label}. Click a state for district-level analytics.</p></div>
      <DateRangeSelector />
      <InfoBox>{q.data.note}</InfoBox>
      <Section title={`National summary — ${n.total_events} events (${n.live_events} live, ${n.historical_events} historical), ${n.industrial_events} industrial, ${n.wildfires} wildfire, ${n.persistent_sources} persistent, ${n.high_risk} high, ${n.critical} critical, exposure ${n.estimated_exposure === null ? 'unavailable' : '≈ ' + fmtNum(n.estimated_exposure)}`}>
        <div className="overflow-x-auto"><table className="table">
          <thead><tr><th>State / UT</th><th>Observations</th><th>Total</th><th>Live</th><th>Industrial</th><th>Wildfires</th><th>Agricultural</th><th>Persistent</th><th>High</th><th>Critical</th><th>Verified</th><th>Est. exposure</th><th>Max risk</th></tr></thead>
          <tbody>{q.data.states.map((s) => (
            <tr key={s.state} className={s.observations === 'no_observations' ? 'opacity-60' : ''}>
              <td><Link className="font-semibold text-brand-700 dark:text-brand-300 hover:underline" to={`/analytics/state/${encodeURIComponent(s.state!)}`}>{s.state}</Link></td>
              <td className="text-xs">{s.observations === 'no_observations' ? 'no observations found' : 'found'}</td><td>{s.total_events}</td><td>{s.live_events}</td><td>{s.industrial_events}</td><td>{s.wildfires}</td><td>{s.agricultural}</td><td>{s.persistent_sources}</td><td>{s.high_risk}</td><td>{s.critical}</td><td>{s.verified}</td>
              <td>{s.estimated_exposure === null ? <span className="unavailable">Unavailable</span> : `≈ ${fmtNum(s.estimated_exposure)}`}</td><td>{s.total_events ? Math.round(s.max_risk) : '—'}</td>
            </tr>))}</tbody>
        </table></div>
      </Section>
    </div>
  );
}
