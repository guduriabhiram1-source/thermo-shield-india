import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Activity, AlertOctagon, AlertTriangle, CheckCircle2, Database, Flame, Layers, UserX } from 'lucide-react';
import { Api, errorMessage } from '../services/api';
import { DataNotice, ErrorBox, Loading, Section, StatCard } from '../components/Common';
import { ClassificationPie, EventsByStateChart, EventsOverTimeChart, HorizontalBars, RiskDistributionChart } from '../charts/DashboardCharts';
import { IndiaMap, MapLegend } from '../maps/IndiaMap';
import { ClassBadge, DataStatusBadge, RiskBadge } from '../components/Badges';
import { DateRangeSelector } from '../components/DateRangeSelector';
import { useDateRange } from '../hooks/useDateRange';
import { fmtDate, fmtNum } from '../utils/format';
import type { EventSummary } from '../types';

function PriorityList({ items, empty }: { items: EventSummary[]; empty: string }) {
  if (!items.length) return <div className="text-sm text-ink-500">{empty}</div>;
  return (
    <ol className="space-y-2">
      {items.map((e, i) => (
        <li key={e.incident_id} className="flex gap-3 items-start">
          <div className="h-7 w-7 shrink-0 rounded-lg bg-ink-100 dark:bg-ink-800 grid place-items-center text-xs font-bold">{i + 1}</div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5"><Link to={`/incidents/${e.incident_id}`} className="font-mono text-xs font-semibold text-brand-700 dark:text-brand-300 hover:underline">{e.incident_id}</Link><RiskBadge level={e.risk_level} /><DataStatusBadge status={e.data_status} /></div>
            <div className="text-xs text-ink-600 dark:text-ink-300 truncate">{e.classification_label} · {e.district || 'District unavailable'}, {e.state}</div>
            <div className="text-[11px] text-ink-500">{e.priority_reason}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}

export default function DashboardPage() {
  const { params, label } = useDateRange();
  const dash = useQuery({ queryKey: ['dashboard', params], queryFn: () => Api.dashboard(params) });
  const events = useQuery({ queryKey: ['events-all', params], queryFn: () => Api.events({ ...params, limit: 2000 }) });
  if (dash.error) return <ErrorBox error={errorMessage(dash.error)} />;
  if (!dash.data) return <Loading text="Loading national dashboard…" />;
  const d = dash.data;
  const c = d.cards;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">National Thermal Incident Dashboard</h1>
          <p className="text-sm text-ink-500 dark:text-ink-400">India-wide detection, persistence, attribution, risk momentum, wind-aware exposure and human verification — real NASA FIRMS data only.</p>
        </div>
        <div className="text-xs text-ink-500">Range: <b>{label}</b> · generated {fmtDate(d.generated_at)}</div>
      </div>
      <DateRangeSelector />
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
        <StatCard label="Total observations" value={fmtNum(c.total_observations)} sub={`${fmtNum(c.live_observations)} live`} accent="blue" icon={<Database size={16} />} />
        <StatCard label="Total events" value={fmtNum(c.total_events)} sub={`${c.live_events} live · ${c.historical_events} historical`} accent="slate" icon={<Layers size={16} />} />
        <StatCard label="Active live events" value={fmtNum(c.live_events)} accent="brand" icon={<Activity size={16} />} />
        <StatCard label="High risk" value={fmtNum(c.high_risk)} accent="orange" icon={<AlertTriangle size={16} />} />
        <StatCard label="Critical" value={fmtNum(c.critical)} accent="red" icon={<AlertOctagon size={16} />} />
        <StatCard label="Persistent" value={fmtNum(c.persistent_sources)} accent="yellow" icon={<Flame size={16} />} />
        <StatCard label="Unverified" value={fmtNum(c.unverified)} accent="violet" icon={<UserX size={16} />} />
        <StatCard label="Verified" value={fmtNum(c.verified)} accent="green" icon={<CheckCircle2 size={16} />} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Section title="India-wide thermal event map" className="xl:col-span-2" right={<Link to="/map" className="btn-secondary text-xs">Open full map</Link>}>
          <div className="h-[460px]">{events.data ? <IndiaMap events={events.data.items} /> : <Loading />}</div>
          <div className="mt-2"><MapLegend /></div>
        </Section>
        <div className="space-y-4">
          <Section title="🟢 Top priority LIVE incidents" right={<Link to="/high-risk" className="btn-secondary text-xs">All alerts</Link>}><PriorityList items={d.top_priority_live} empty="No live incidents in the selected range." /></Section>
          <Section title="🔵 Top historical incidents (separately ranked)"><PriorityList items={d.top_priority_historical} empty="No historical incidents in the selected range." /></Section>
        </div>
      </div>
      <Section title="Data freshness">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 text-xs">
          {d.freshness.length === 0 && <div className="text-ink-500">No external dataset has been retrieved yet.</div>}
          {d.freshness.map((f) => (
            <div key={f.source} className="rounded-lg border border-ink-200 dark:border-ink-800 p-3">
              <div className="font-semibold uppercase tracking-wider text-ink-500">{f.source}</div>
              <div className="mt-1">{f.provider}</div>
              <div className={`mt-1 font-semibold ${f.status === 'ok' ? 'text-green-700 dark:text-green-400' : 'text-amber-700 dark:text-amber-400'}`}>{f.status}</div>
              <div className="text-ink-500">Source time: {fmtDate(f.source_timestamp)}</div>
              <div className="text-ink-500">Retrieved: {fmtDate(f.retrieved_at)}</div>
            </div>
          ))}
        </div>
      </Section>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section title="Events by state"><EventsByStateChart data={d.events_by_state} /></Section>
        <Section title="Events over time"><EventsOverTimeChart data={d.events_over_time} /></Section>
        <Section title="Classification distribution (AI inference)"><ClassificationPie data={d.classification_distribution} /></Section>
        <Section title="Risk distribution"><RiskDistributionChart data={d.risk_distribution} /></Section>
        <Section title="Top industrial regions (facility within 5 km)"><HorizontalBars data={d.top_industrial_areas} nameKey="name" valueKey="events" color="#7c3aed" valueName="Events" emptyText="No event within 5 km of a known facility in this range." /></Section>
        <Section title="Estimated population exposure by state"><HorizontalBars data={d.population_exposure_by_state} nameKey="state" valueKey="population" color="#f97316" valueName="Est. exposed population" emptyText="No population-exposure estimate available in this range." /></Section>
      </div>
      <Section title="🚨 High / critical incidents in range">
        {d.recent_alerts.length === 0 ? <div className="text-sm text-ink-500">No HIGH / CRITICAL incidents in the selected range.</div> : (
          <div className="overflow-x-auto"><table className="table">
            <thead><tr><th>Incident</th><th>Data</th><th>Classification</th><th>Risk</th><th>Confidence</th><th>Location</th><th>Est. exposure</th><th>Nearest facility</th></tr></thead>
            <tbody>{d.recent_alerts.map((e) => (
              <tr key={e.incident_id}>
                <td><Link className="font-mono text-brand-700 dark:text-brand-300 hover:underline" to={`/incidents/${e.incident_id}`}>{e.incident_id}</Link></td><td><DataStatusBadge status={e.data_status} /></td>
                <td><ClassBadge classification={e.classification} label={e.classification_label} /></td><td><RiskBadge level={e.risk_level} score={e.risk_score} /></td>
                <td>{Math.round(e.confidence * 100)}%</td><td>{e.locality || '—'}, {e.district || '—'}, {e.state}</td><td>{e.exposed_population === null ? 'Unavailable' : `≈ ${fmtNum(e.exposed_population)}`}</td><td className="text-xs">{e.nearest_facility?.name ?? 'None within radius'}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </Section>
      <DataNotice />
    </div>
  );
}
