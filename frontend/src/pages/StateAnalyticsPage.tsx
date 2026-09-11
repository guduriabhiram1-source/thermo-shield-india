import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Api, errorMessage } from '../services/api';
import { ErrorBox, Loading, Section, StatCard } from '../components/Common';
import { ClassificationPie } from '../charts/DashboardCharts';
import { IndiaMap } from '../maps/IndiaMap';
import { IncidentCard } from '../components/IncidentCard';
import { DateRangeSelector } from '../components/DateRangeSelector';
import { useDateRange } from '../hooks/useDateRange';
import { fmtNum } from '../utils/format';

export default function StateAnalyticsPage() {
  const { state = '' } = useParams();
  const { params } = useDateRange();
  const q = useQuery({ queryKey: ['state', state, params], queryFn: () => Api.state(state, params) });
  if (q.error) return <ErrorBox error={errorMessage(q.error)} />;
  if (!q.data) return <Loading />;
  const d = q.data;
  const s = d.summary;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2"><div><Link to="/analytics" className="text-xs text-brand-600 hover:underline">← All states</Link><h1 className="text-2xl font-extrabold tracking-tight">{d.state} <span className="text-ink-400 font-mono text-base">{d.code}</span></h1><p className="text-sm text-ink-500">Population density {d.population_density ?? 'unavailable'} /km² (Census 2011) · {d.all_districts.length} OSM districts</p></div></div>
      <DateRangeSelector />
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
        <StatCard label="Events" value={s.total_events} sub={`${s.live_events} live`} accent="slate" /><StatCard label="Industrial" value={s.industrial_events} accent="violet" /><StatCard label="Wildfires" value={s.wildfires} accent="green" /><StatCard label="Persistent" value={s.persistent_sources} accent="yellow" /><StatCard label="High" value={s.high_risk} accent="orange" /><StatCard label="Critical" value={s.critical} accent="red" /><StatCard label="Est. exposure" value={s.estimated_exposure === null ? 'Unavailable' : `≈ ${fmtNum(s.estimated_exposure)}`} accent="blue" />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Section title="Events in state" className="xl:col-span-2"><div className="h-[420px]"><IndiaMap events={d.events} /></div></Section>
        <Section title="Classification distribution"><ClassificationPie data={d.classification_distribution} /></Section>
      </div>
      <Section title="District-level analytics">
        {d.districts.length === 0 ? <div className="text-sm text-ink-500">No observations found in this state for the selected range.</div> : (
          <div className="overflow-x-auto"><table className="table"><thead><tr><th>District</th><th>OSM district</th><th>Events</th><th>Live</th><th>Industrial</th><th>Wildfires</th><th>Persistent</th><th>High</th><th>Critical</th><th>Est. exposure</th></tr></thead>
            <tbody>{d.districts.map((x: any) => <tr key={x.district}><td><Link className="text-brand-700 dark:text-brand-300 hover:underline" to={`/incidents?state=${encodeURIComponent(d.state)}&district=${encodeURIComponent(x.district)}`}>{x.district}</Link></td><td className="text-xs">{x.known_osm_district ? 'yes' : 'name from geocoder'}</td><td>{x.total_events}</td><td>{x.live_events}</td><td>{x.industrial_events}</td><td>{x.wildfires}</td><td>{x.persistent_sources}</td><td>{x.high_risk}</td><td>{x.critical}</td><td>{x.estimated_exposure === null ? 'Unavailable' : `≈ ${fmtNum(x.estimated_exposure)}`}</td></tr>)}</tbody></table></div>
        )}
      </Section>
      <Section title="Incidents (by priority)"><div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-3">{d.events.slice(0, 30).map((e: any) => <IncidentCard key={e.incident_id} e={e} compact />)}</div></Section>
    </div>
  );
}
